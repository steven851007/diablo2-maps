"""Maps with a walking route for the phone page. Asks the public map site once per seed (only the seed,
level numbers and difficulty are sent) and draws the answer as SVG, turned like the in-game automap."""
import base64, colorsys, gzip, heapq, json, math, os, re, subprocess, urllib.request, zlib
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))

API = 'https://maps.diablo.deadlybossmods.com/api/render?seed={seed}&levels={levels}&difficulty={diff}'
# title, level id, where you arrive ('wp' or the level you come from), level to reach
AREAS = [('Durance 2 → Mephisto', '', 101, 'wp', 102), ('Worldstone 2 → 3', '', 129, 'wp', 130), ('Worldstone 3 → Baal', '', 130, 129, 131),
         ('Catacombs 2 → 3', '', 35, 'wp', 36), ('Catacombs 3 → Andariel', '', 36, 35, 37), ('Halls of Pain → Vaught', 'Nihlathak', 123, 'wp', 124)]
# Herald zones: key, title, names the game shows when the zone is terrorized, and per level:
# title, level id, where you start, where to end (None = anywhere). Starts: 'wp', a level id (its stairs or border), 'any'.
ZONES = [
    ('tombs', 'Tombs + Canyon', ["Tal Rasha's Tombs", "Tal Rasha's Tomb", 'Canyon of the Magi'],
     [('Canyon of the Magi', 46, 'wp', None)] + [(f'Tomb {k} from the left', lv, 46, None) for k, lv in enumerate((69, 68, 67, 66, 70, 71, 72), 1)]),
    ('tunnels', 'Ancient Tunnels', ['Ancient Tunnels'], [('Lost City: to the Tunnels', 44, 'wp', 65), ('Ancient Tunnels', 65, 44, None)]),
    ('sewers', 'Sewers Act 2', ['Lut Gholein Sewers'], [('Sewers 2', 48, 'wp', 49), ('Sewers 3', 49, 48, None), ('Sewers 1', 47, 48, None)]),
    ('tamoe', 'Tamoe + Pit', ['Tamoe Highland', 'The Pit', 'Pit'], [('Tamoe Highland', 7, 26, 12), ('Pit 1', 12, 7, 16), ('Pit 2', 16, 12, None)]),
    ('marsh', 'Black Marsh', ['Black Marsh', 'The Hole'], [('Black Marsh', 6, 'wp', None)]),
    ('darkwood', 'Dark Wood + Underground', ['Dark Wood', 'Underground Passage'], [('Dark Wood', 5, 'wp', 10), ('Underground Passage 1', 10, 5, 14), ('Underground Passage 2', 14, 10, None)]),
    ('stony', 'Stony Field + Tristram', ['Stony Field', 'Tristram'], [('Stony Field', 4, 'wp', 'cairn'), ('Tristram', 38, 'any', None)]),
    ('cold', 'Cold Plains', ['Cold Plains', 'The Cave'], [('Cold Plains', 3, 'wp', None)]),
    ('burial', 'Burial Grounds', ['Burial Grounds', 'Crypt', 'The Crypt', 'Mausoleum', 'The Mausoleum'], [('Burial Grounds', 17, 3, 18), ('Crypt', 18, 17, None), ('Mausoleum', 19, 17, None)]),
    ('moor', 'Blood Moor', ['Blood Moor', 'Den of Evil'], [('Blood Moor', 2, 1, None)]),
]
PASS_ONLY = {44}
# The game files have no "super chest" flag; these are the large chests (big chests in Act 1 dungeons, large tomb chests).
SUPER_CHESTS = {5, 6, 88, 147, 148}
ON_THE_WAY = 30                  # steps from your route
# Shrines whose type is drawn from all boosts (Experience, Skill, ...) or, about 1 in 10, from the magic ones.
# Health and mana spots are left out. Object ids with InitFn 1 and Parm0 3 in objects.txt of D2R 3.4.
ANY_SHRINES = {2, 81, 83, 86, 97, 116, 123, 124, 133, 134, 135, 136, 150, 151, 184, 190, 191, 197, 199, 200, 201, 226, 231, 232, 260, 262,
               263, 277, 279, 282, 299, 300, 303, 325, 361, 414, 415, 421, 427, 428, 472, 479, 488, 495, 497, 499, 503, 509, 512, 520}
LANDMARKS = [('Cairn', {17, 18, 19, 20, 21, 22}), ('Tree', {30})]     # Cairn Stones (one mark in their middle), Tree of Inifuss


def shrines(l): return [iso(int(p['x']), int(p['y'])) for p in l['presets'] if p.get('type') == 'obj' and p.get('txtFileNo') in ANY_SHRINES]


def landmark_marks(l, r):
    out = []
    for name, ids in LANDMARKS:
        c = [(int(p['x']), int(p['y'])) for p in l['presets'] if p.get('type') == 'obj' and p.get('txtFileNo') in ids]
        if not c: continue
        u, v = iso(sum(x for x, _ in c) / len(c), sum(y for _, y in c) / len(c))
        out.append(f'<path d="M{u:.0f} {v - .9*r:.0f}L{u + .9*r:.0f} {v:.0f}L{u:.0f} {v + .9*r:.0f}L{u - .9*r:.0f} {v:.0f}Z" fill="#fff" stroke="#111" stroke-width="{.2*r:.1f}"/>'
                   f'<text x="{u:.0f}" y="{v - 1.3*r:.0f}" font-size="{1.3*r:.1f}" text-anchor="middle" fill="#fff" stroke="#111" stroke-width="{.35*r:.1f}" paint-order="stroke" font-family="sans-serif" font-weight="700">{name}</text>')
    return ''.join(out)


def super_chests(l): return [(int(p['x']), int(p['y'])) for p in l['presets'] if p.get('type') == 'obj' and p.get('txtFileNo') in SUPER_CHESTS]


def chest_marks(l, path, r):
    """SVG for the large chests: big gold ones near the route, small dim ones elsewhere; and how many are near."""
    out, n = [], 0
    for c in super_chests(l):
        near = any((c[0] - x) ** 2 + (c[1] - y) ** 2 <= ON_THE_WAY ** 2 for x, y in path[::2] + path[-1:])
        u, v = iso(*c); k = .75 if near else .45; n += near
        out.append(f'<rect x="{u - k*r:.0f}" y="{v - k*r*.7:.0f}" width="{2*k*r:.0f}" height="{1.4*k*r:.0f}" rx="{.25*k*r:.0f}" fill="{"#ffc83a" if near else "#8a7330"}" stroke="#111" stroke-width="{.18*r:.1f}"/>')
    return ''.join(out), n


def chest_text(n): return f'{n} super chest{"s" * (n != 1)} on the way' if n else ''
                 # shown with the way to the exit, not cleared
REACH = 24                       # steps around your path that count as cleared
DIRS8 = ['right', 'top right', 'top', 'top left', 'left', 'bottom left', 'bottom', 'bottom right']
MAX = 30_000_000


def fetch(seed, diff=2, timeout=20, levels=None):
    url = API.format(seed=int(seed), diff=int(diff), levels=','.join(str(int(x)) for x in levels or [a[2] for a in AREAS]))
    q = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 generic-client', 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(q, timeout=timeout) as r:
        b = r.read(MAX)
        if r.headers.get('Content-Encoding') == 'gzip': b = gzip.decompress(b)
    return {int(l['levelNo']): l for l in json.loads(b.decode('utf-8', 'replace'))['levels']}


def walkable(l):
    """bytearray of w*h cells: 1 = can walk."""
    w, h = int(l['collisionWidth']), int(l['collisionHeight'])
    if not 0 < w <= 4000 or not 0 < h <= 4000: raise ValueError('map size')
    raw = base64.b64decode(l['collisionDeflateB64'])
    try: b = zlib.decompressobj().decompress(raw, MAX)
    except zlib.error: b = zlib.decompressobj(-15).decompress(raw, MAX)
    if len(b) < 2 * w * h: raise ValueError('map data too short')
    lo, hi = b[0:2 * w * h:2], b[1:2 * w * h:2]          # 0xFFFF = nothing there; bits 1 and 4 = blocked
    return bytearray(0 if (x & 5 or (x == 255 and y == 255)) else 1 for x, y in zip(lo, hi)), w, h


def outline(F, w, h):
    """Closed border loops (corner points) of the walkable area, walkable side always on the same hand."""
    nxt = {}
    def put(a, b): nxt.setdefault(a, []).append(b)
    for y in range(1, h - 1):
        row = F[y * w:(y + 1) * w]
        if 1 not in row: continue
        up, dn = F[(y - 1) * w:y * w], F[(y + 1) * w:(y + 2) * w]
        x = row.find(1)
        while x >= 0:
            if not up[x]: put((x, y), (x + 1, y))
            if not dn[x]: put((x + 1, y + 1), (x, y + 1))
            if x == 0 or not row[x - 1]: put((x, y + 1), (x, y))
            if x == w - 1 or not row[x + 1]: put((x + 1, y), (x + 1, y + 1))
            x = row.find(1, x + 1)
    loops = []
    while nxt:
        a = next(iter(nxt)); p = [a]; cur = a
        while True:
            opts = nxt[cur]; b = opts.pop()
            if not opts: del nxt[cur]
            if len(p) > 1 and (p[-1][0] - p[-2][0], p[-1][1] - p[-2][1]) != (0, 0):
                dx, dy = p[-1][0] - p[-2][0], p[-1][1] - p[-2][1]
                if dx * (b[1] - p[-1][1]) == dy * (b[0] - p[-1][0]) and dx * (b[0] - p[-1][0]) + dy * (b[1] - p[-1][1]) > 0: p.pop()   # straight on
            p.append(b); cur = b
            if b == a or b not in nxt: break
        loops.append(p)
    return loops


def route(F, w, h, a, b):
    """Shortest walk from a to b that keeps a little distance from walls: list of cells, or []."""
    def near(p):
        c = [((x - p[0]) ** 2 + (y - p[1]) ** 2, x, y) for x in range(max(1, p[0] - 16), min(w - 1, p[0] + 17)) for y in range(max(1, p[1] - 16), min(h - 1, p[1] + 17)) if F[y * w + x]]
        return min(c)[1:] if c else None
    s, t = near(a), near(b)
    if not s or not t: return []
    S, G = s[1] * w + s[0], t[1] * w + t[0]; D = {S: 0.0}; prev = {}; Q = [(0.0, S)]; n = w * h; d2 = math.sqrt(2)
    get = lambda i: F[i] if 0 <= i < n else 0
    cost = {}
    def price(i):
        if i not in cost: cost[i] = 1.0 if get(i + 2) and get(i - 2) and get(i + 2 * w) and get(i - 2 * w) else 2.5
        return cost[i]
    H = lambda i: math.hypot(i % w - t[0], i // w - t[1])
    done = set(); Q = [(H(S), S)]
    while Q:
        _, q = heapq.heappop(Q)
        if q == G: break
        if q in done: continue
        done.add(q); d = D[q]
        l, r, u, v = get(q - 1), get(q + 1), get(q - w), get(q + w)
        for ok, i, f in ((l, q - 1, 1), (r, q + 1, 1), (u, q - w, 1), (v, q + w, 1), (l and u, q - w - 1, d2), (r and u, q - w + 1, d2), (l and v, q + w - 1, d2), (r and v, q + w + 1, d2)):
            if ok and get(i) and i not in done:
                e = d + f * price(i)
                if e < D.get(i, 1e18): D[i] = e; prev[i] = q; heapq.heappush(Q, (e + H(i), i))
    if G not in prev and G != S: return []
    path = [G]
    while path[-1] != S: path.append(prev[path[-1]])
    return [(i % w, i // w) for i in reversed(path)]


def iso(x, y): return 2 * (x - y), x + y


def first_direction(path, steps=60):
    if len(path) < 2: return None
    a, m = path[0], path[min(steps, len(path) - 1)]; u, v = iso(m[0] - a[0], m[1] - a[1])
    return DIRS8[int((math.degrees(math.atan2(-v, u)) % 360 + 22.5) // 45) % 8]


def draw(l, frm, to):
    """{'route': svg, 'full': svg, 'start': direction} for one level."""
    F, w, h = walkable(l)
    exits = {int(p['destLevelNo']): (int(p['x']), int(p['y'])) for p in l['presets'] if p.get('type') == 'exit' and 'destLevelNo' in p}
    wp = next(((int(p['x']), int(p['y'])) for p in l['presets'] if p.get('kind') == 'Waypoint'), None)
    a, b = wp if frm == 'wp' else exits.get(frm), exits.get(to)
    if to == 'nihlathak': b = next(((int(p['x']), int(p['y'])) for p in l['presets'] if p.get('type') == 'obj' and p.get('txtFileNo') == 462), None)   # "Nihlathak Start"
    if not a or not b: raise ValueError('start or exit missing')
    path = route(F, w, h, a, b); pts = [iso(*p) for p in path]
    body = []; allp = []
    for p in outline(F, w, h):
        q = [iso(*c) for c in p]; allp += q; body.append('M' + 'L'.join(f'{x} {y}' for x, y in q) + 'Z')
    shr = shrines(l)
    A, B = iso(*a), iso(*b); marks = lambda r: chest_marks(l, path, r)[0]; near = chest_marks(l, path, 1)[1]
    def svg(box):
        x0, y0, x1, y1 = box; W, H = x1 - x0, y1 - y0; r = max(W, H * 1.2) / 46
        dot = lambda p, c, k: f'<circle cx="{p[0]}" cy="{p[1]}" r="{k*r:.1f}" fill="{c}" stroke="#fff" stroke-width="{0.28*r*k:.1f}"/>'
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {W} {H}" width="{W}" height="{H}">'
                f'<path d="{"".join(body)}" fill="#2c303a" fill-rule="evenodd" stroke="#cdb482" stroke-width="0.9" vector-effect="non-scaling-stroke"/>'
                + ''.join(f'<circle cx="{p[0]}" cy="{p[1]}" r="{0.6*r:.1f}" fill="#be78ff"/>' for p in shr)
                + (f'<polyline points="{" ".join(f"{x},{y}" for x, y in pts)}" fill="none" stroke="#3cdc78" stroke-width="3.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>' if pts else '')
                + marks(r) + landmark_marks(l, r) + dot(A, '#3c8cff', 1) + dot(B, '#eb3c3c', 1) + '</svg>')
    bb = lambda P, pad: (min(p[0] for p in P) - pad, min(p[1] for p in P) - pad, max(p[0] for p in P) + pad, max(p[1] for p in P) + pad)
    full = bb(allp, 14); x0, y0, x1, y1 = bb(pts + [A, B], 90)
    gx, gy = max(0, 640 - (x1 - x0)) // 2, max(0, 380 - (y1 - y0)) // 2; x0, x1, y0, y1 = x0 - gx, x1 + gx, y0 - gy, y1 + gy   # not too close
    x0, y0, x1, y1 = max(x0, full[0]), max(y0, full[1]), min(x1, full[2]), min(y1, full[3])
    return {'route': svg((x0, y0, x1, y1)), 'full': svg(full), 'start': first_direction(path) or '', 'steps': len(path), 'info': chest_text(near)}


def clear_route(F, w, h, a, b, ms=400):
    """Walk that clears the level: (path, share of the floor, steps)."""
    head = f'{w} {h} {REACH} {ms} {a[0]} {a[1]} {b[0] if b else -1} {b[1] if b else -1}\n'
    r = subprocess.run([os.path.join(HERE, 'clearroute')], input=head.encode() + bytes(F), capture_output=True, timeout=60)
    L = r.stdout.decode().split('\n')
    if r.returncode or len(L) < 3: raise ValueError('no route')
    share, steps, _ = L[0].split()
    return [tuple(map(int, q.split())) for q in L[1:] if q], float(share), int(float(steps))


def border(l, F, w, h, other):
    """Middle of the opening towards a neighbouring outdoor level."""
    for t in l.get('tells', []):            # the site marks some of them
        if t['name'] in (('BloodMoorCampExit',) if other == 1 else ('TamoeHighlandExit',) if other == 26 else ()) and t['locations']:
            return int(t['locations'][0]['x']), int(t['locations'][0]['y'])
    adj = [(int(a['bridgeX']), int(a['bridgeY'])) for a in l['adjacents'] if a.get('levelNo') == other and 'bridgeX' in a]
    if not adj: return None
    side = max((('L', sum(x <= 20 for x, y in adj)), ('R', sum(x >= w - 20 for x, y in adj)), ('T', sum(y <= 20 for x, y in adj)), ('B', sum(y >= h - 20 for x, y in adj))), key=lambda t: t[1])[0]
    line = [(0, y) for y in range(h)] if side == 'L' else [(w - 1, y) for y in range(h)] if side == 'R' else [(x, 0) for x in range(w)] if side == 'T' else [(x, h - 1) for x in range(w)]
    runs, cur = [], []
    for p in line + [None]:
        if p and F[p[1] * w + p[0]]: cur.append(p)
        elif cur: runs.append(cur); cur = []
    runs = [r for r in runs if len(r) >= 8]
    if not runs: return min(adj, key=lambda p: abs(p[0] - w / 2) + abs(p[1] - h / 2))
    near = lambda r: min(abs(r[len(r) // 2][0] - x) + abs(r[len(r) // 2][1] - y) for x, y in adj)
    r = min(runs, key=lambda r: (len(r) > 70, near(r))); return r[len(r) // 2]


def place(l, F, w, h, spec):
    if spec is None: return None
    if spec == 'wp': return next(((int(p['x']), int(p['y'])) for p in l['presets'] if p.get('kind') == 'Waypoint'), None)
    if spec == 'cairn':
        c = [(int(p['x']), int(p['y'])) for p in l['presets'] if str(p.get('name', '')).startswith('Stone') and p.get('displayName') == 'Cairn Stone' or str(p.get('name', '')) in ('StoneAlpha', 'StoneBeta', 'StoneGamma', 'StoneDelta', 'StoneLambda', 'StoneTheta')]
        return (sum(x for x, _ in c) // len(c), sum(y for _, y in c) // len(c)) if c else None
    if spec == 'any': i = F.find(1, len(F) // 2); return (i % w, i // w) if i >= 0 else None
    ex = next(((int(p['x']), int(p['y'])) for p in l['presets'] if p.get('type') == 'exit' and p.get('destLevelNo') == spec), None)
    return ex or border(l, F, w, h, spec)


def draw_clear(l, frm, to, free_start=False):
    F, w, h = walkable(l); a, b = place(l, F, w, h, frm), place(l, F, w, h, to)
    if not a: raise ValueError('start missing')
    if frm == 'any':                        # start unknown: take the end of a route as the start of the final one
        p, _, _ = clear_route(F, w, h, a, None, 150); a = p[-1]
    path, share, steps = clear_route(F, w, h, a, b); P = [iso(*p) for p in path]; n = len(P)
    P = [tuple(sum(q[k] for q in P[max(0, i - 1):i + 2]) / len(P[max(0, i - 1):i + 2]) for k in (0, 1)) for i in range(n)]
    body, allp = [], []
    for p in outline(F, w, h): q = [iso(*c) for c in p]; allp += q; body.append('M' + 'L'.join(f'{x} {y}' for x, y in q) + 'Z')
    x0, y0 = min(p[0] for p in allp) - 14, min(p[1] for p in allp) - 14; W, H = max(p[0] for p in allp) + 14 - x0, max(p[1] for p in allp) + 14 - y0
    r = max(W, H * 1.2) / 44; out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {W} {H}" width="{W}" height="{H}"><path d="{"".join(body)}" fill="#2c303a" fill-rule="evenodd" stroke="#8d7f60" stroke-width="0.7" vector-effect="non-scaling-stroke"/>']
    K = 36
    for k in range(K):
        c = colorsys.hsv_to_rgb(.38 - .38 * k / K, .78, .95); seg = P[k * n // K:(k + 1) * n // K + 1]
        out.append(f'<polyline points="{" ".join(f"{x:.0f},{y:.0f}" for x, y in seg)}" fill="none" stroke="#{int(c[0]*255):02x}{int(c[1]*255):02x}{int(c[2]*255):02x}" stroke-width="2.6" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>')
    for u, v in shrines(l): out.append(f'<circle cx="{u}" cy="{v}" r="{.5*r:.1f}" fill="#be78ff"/>')
    marks = max(3, min(10, n // 45))
    for k in range(1, marks + 1):
        x, y = P[min(n - 1, k * n // marks)]; out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.1f}" fill="#111"/><text x="{x:.0f}" y="{y+.4*r:.0f}" font-size="{1.25*r:.1f}" text-anchor="middle" fill="#fff" font-family="sans-serif">{k}</text>')
    cm, near = chest_marks(l, path, r); out.insert(1 + K, cm); out.append(landmark_marks(l, r))
    x, y = P[0]; out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.1f}" fill="#3c8cff" stroke="#fff" stroke-width="{.25*r:.1f}"/></svg>')
    info = ', '.join(x for x in (f'{steps} steps, {100*share:.0f}%', chest_text(near), 'start unknown' if frm == 'any' else '') if x)
    return {'route': ''.join(out), 'full': ''.join(out), 'start': first_direction(path, 15) or '', 'info': info, 'steps': steps}


def build_zone(levels, zone):
    out = []
    for title, lv, frm, to in next(z for z in ZONES if z[0] == zone)[3]:
        try: d = draw(levels[lv], frm, to) if lv in PASS_ONLY else draw_clear(levels[lv], frm, to)
        except (KeyError, ValueError, TypeError, zlib.error, OSError, subprocess.SubprocessError): continue
        out.append({'title': title, 'note': '', 'level': lv, **d})
    return out


def zone_levels(zone): return [x[1] for x in next(z for z in ZONES if z[0] == zone)[3]]


def terror_zones(lines):
    """Zone keys named in the corner text of a screenshot (the active terror zone)."""
    norm = lambda t: re.sub(r'[^a-z ]', '', t.lower().replace('ø', 'o').replace('#', 'o').replace('0', 'o')).strip(); found = []
    for raw in lines[2:]:
        for key, _, names, _ in ZONES:
            if key not in found and max(SequenceMatcher(None, norm(n), norm(raw)).ratio() for n in names) > 0.8: found.append(key)
    return found


def build(levels):
    """[{title, note, level, start, route, full}] - a level that cannot be drawn is left out."""
    out = []
    for title, note, lv, frm, to in AREAS:
        try: out.append({'title': title, 'note': note, 'level': lv, **draw(levels[lv], frm, to)})
        except (KeyError, ValueError, TypeError, zlib.error): continue
    return out
