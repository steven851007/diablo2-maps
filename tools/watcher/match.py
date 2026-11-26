"""Align automap wall segments with room templates and turn them into solver evidence."""
import json, math, os, re, subprocess, time
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
DIRS = {'W': (-1, 0), 'N': (0, -1), 'E': (1, 0), 'S': (0, 1)}
OPP = {'W': 'E', 'E': 'W', 'N': 'S', 'S': 'N'}
SCREEN = {'W': 'top left', 'N': 'top right', 'E': 'bottom right', 'S': 'bottom left'}
# the user's words for the Summoner's arm: one word each, clockwise from the upper left
SUMMONER = {'W': 'top', 'N': 'right', 'E': 'bottom', 'S': 'left'}
TITLES = {'jail level 1': 'jail1', 'catacombs level 2': 'catacombs2', 'sewers level 2': 'sewers2',
          'durance of hate level 2': 'durance2', 'halls of the dead level 2': 'halls'}
OTHERS = ['jail level 2', 'jail level 3', 'catacombs level 1', 'catacombs level 3', 'catacombs level 4', 'sewers level 1', 'sewers level 3',
          'durance of hate level 1', 'durance of hate level 3', 'halls of the dead level 1', 'halls of the dead level 3', 'rogue encampment', 'lut gholein']
LOOKS, VARIANTS = {'jail1', 'sewers2', 'catacombs2', 'durance2'}, {'sewers2', 'catacombs2'}


def canon(m): return ''.join(d for d in 'WNES' if d in m)


def level_from_text(lines):
    """(stop or None, difficulty or None, title) from the recognised corner text."""
    stop = diff = title = None; best = 0.0
    for i, raw in enumerate(lines):
        t = re.sub(r'[^a-z0-9 ]', '', raw.lower().replace('#', 'o').replace('|', 'j' if i == 0 else 'l')).strip()
        if 'diff' in t or 'hell' in t[-6:] and i:
            for d in ('nightmare', 'normal', 'hell'):
                if SequenceMatcher(None, d, t.split()[-1] if t.split() else '').ratio() > 0.6: diff = d; break
            continue
        if stop is None and i < 2:
            t = re.sub(r'\b(i|l|1)$', '1', t); t = re.sub(r'\bz$', '2', t)
            m = re.search(r'(\d)$', t)
            for name in list(TITLES) + OTHERS:
                if m and name[-1].isdigit() and name[-1] != m.group(1): continue
                r = SequenceMatcher(None, name, t).ratio()
                if r > best and r > 0.78: best, title = r, name
    return TITLES.get(title), diff, title


def town_exit(shot):
    """Exit side of the Rogue Encampment from its fence (30 x 23 pieces, 3 missing on the exit side), or None.
    Every layout is open towards the bottom right; with no other gap that is the exit."""
    q = {}
    for a, b, d, v, *_ in shot['segments']: q[(a, b, d)] = min(1.0, 1.6 * v)
    if len(q) < 40: return None, 'fence not visible'
    A = [e[0] for e in q]; B = [e[1] for e in q]; sh = (-1, 0, 1); get = q.get
    north = lambda u, v: max(([get((u + k, v + s, 0), 0) for k in range(30)] for s in sh), key=sum)
    south = lambda u, v: max(([get((u + k, v + 23 + s, 0), 0) for k in range(30)] for s in sh), key=sum)
    west = lambda u, v: max(([get((u + s, v + k, 1), 0) for k in range(23)] for s in sh), key=sum)
    best = max(((sum(north(u, v)) + sum(south(u, v)) + sum(west(u, v)), u, v) for u in range(min(A) - 1, max(A) + 1) for v in range(min(B) - 1, max(B) + 1)), key=lambda t: t[0])
    _, u, v = best; state = {}
    for side, line, g in (('N', north(u, v), (15, 16, 17)), ('S', south(u, v), (15, 16, 17)), ('W', west(u, v), (10, 11, 12))):
        on = [x > 0.3 for x in line]; best_g = None
        for o in sh:                                   # the gap may sit one piece off as well
            left = sum(line[k + o] for k in g); rest = [x for k, x in enumerate(on) if k - o not in g and 1 <= k < len(on) - 1]
            edge = [on[g[0] + o - 2], on[g[0] + o - 1], on[g[2] + o + 1], on[g[2] + o + 2]]
            # posts and things behind the gap can leave a little: 0 to 0.8 of 3 pieces = gap, up to 1.6 = unclear
            t = (2 if left <= 0.8 and sum(edge) >= 3 else 1 if left <= 1.6 else 0, sum(rest) / len(rest))
            if best_g is None or t[0] > best_g[0]: best_g = t
        state[side] = best_g
    if min(c for _, c in state.values()) < 0.6: return None, 'fence only partly visible'
    open_ = [s for s, (o, _) in state.items() if o == 2]
    if len(open_) == 1: return open_[0], 'ok'
    if open_: return None, 'more than one gap'
    return (None, 'fence partly hidden') if any(o for o, _ in state.values()) else ('E', 'ok')


class Templates:
    def __init__(self, path=None):
        d = json.load(open(path or os.path.join(HERE, 'templates.json')))
        self.version, self.levels = d['version'], {}; self.town = d.get('town')
        for name, l in d['levels'].items():
            Z, rooms = l['size'], []
            for r in l['rooms']:
                # a segment on the far border belongs to the neighbouring room's first row/column
                E = frozenset((x, y, o) for x, y, o, door in r['edges'] if x < Z and y < Z)
                rooms.append(dict(preset=r['preset'], file=r['file'], kind=r['kind'], exits=canon(r['exits']), edges=E))
            self.levels[name] = (Z, rooms)


def ends(e): return ((e[0], e[1]), (e[0] + 1, e[1])) if e[2] % 2 == 0 else ((e[0], e[1]), (e[0], e[1] + 1))   # 0/1 walls, 2/3 step lines


def weight(q, kept): return min(1.0, q * 1.5) if kept else 0.25 * q


def room_score(obs, t, missing=0.35, wrong=1.1):
    """obs: {(x,y,d): weight} inside one room. Log-like score, 0 for nothing seen."""
    s, nodes = 0.0, set()
    for e, w in obs.items():
        if e in t: s += w
        else: s -= wrong * w
        if w > 0.3: nodes.update(ends(e))
    for e in t:
        if e not in obs and any(n in nodes for n in ends(e)): s -= missing
    return s


def split(edges, Z):
    cells = {}
    for (a, b, d), w in edges.items(): cells.setdefault((a // Z, b // Z), {})[(a % Z, b % Z, d)] = w
    return cells


def anchor(edges, level, T, top=12):
    """Find the waypoint room. Returns list of (score, exit direction, tile offset) best first."""
    Z, rooms = T.levels[level]; wps = [r for r in rooms if r['kind'] == 'Waypoint']
    strong = {e: w for e, w in edges.items() if w > 0.3}
    if not strong: return []
    A = [e[0] for e in strong]; B = [e[1] for e in strong]; out = []
    for r in wps:
        E = r['edges']
        for u in range(min(A) - Z, max(A) + 1):
            for v in range(min(B) - Z, max(B) + 1):
                hit = sum(strong.get((x + u, y + v, d), 0) for x, y, d in E)
                if hit < 11: continue
                wrong = sum(w for (a, b, d), w in strong.items() if u <= a < u + Z and v <= b < v + Z and (a - u, b - v, d) not in E)
                out.append((hit - 1.2 * wrong - 0.15 * (len(E) - hit), r['exits'], (u, v)))
    out.sort(reverse=True); cand = []
    for s, ex, off in out[:top]:            # let the rest of the map vote as well
        moved = {(a - off[0], b - off[1], d): w for (a, b, d), w in edges.items()}; tot = 0.0
        for c, obs in split(moved, Z).items():
            if c == (0, 0) or sum(obs.values()) < 2.5: continue
            tot += max(0.0, max(room_score(obs, r['edges']) for r in rooms))
        cand.append((s + 0.5 * tot, ex, off, s))
    cand.sort(reverse=True); return cand


def in_view(shot, a, b):
    W, H = shot['width'], shot['height']
    x = (shot['ox'] + (a - b) * shot['tx']) / W; y = (shot['oy'] + (a + b) * shot['ty']) / H
    if not (0.01 < x < 0.99 and 0.01 < y < 0.89): return False
    if y > 0.80 and (x < 0.26 or x > 0.74): return False
    return not (y < 0.11 and x < 0.22 or y < 0.26 and x > 0.87)


class LevelMap:
    """All screenshots of one level, in tiles relative to the waypoint room."""
    def __init__(self, level): self.level, self.parts, self.wp, self._m = level, [], None, None

    @property
    def edges(self):
        """Merged walls. Explored walls stay on the automap, so a segment that a later shot should
        show but does not is probably background noise."""
        if self._m is None:
            out = {}
            for e in {e for p in self.parts for e in p['edges']}:
                seen = [i for i, p in enumerate(self.parts) if e in p['edges']]
                w = max(self.parts[i]['edges'][e] for i in seen); later = [p for p in self.parts[seen[-1] + 1:] if in_view(p['shot'], e[0] + p['off'][0], e[1] + p['off'][1])]
                strong = sum(self.parts[i]['edges'][e] > 0.3 for i in seen)
                if strong >= 2: w = min(1.0, w + 0.15)
                if later and strong < 2: w *= 0.4
                out[e] = w
            self._m = out
        return self._m

    def _merge(self, shot, edges, off):
        self._m = None; self.parts.append({'shot': {k: shot[k] for k in ('width', 'height', 'ox', 'oy', 'tx', 'ty')}, 'off': off, 'edges': {(a - off[0], b - off[1], d): w for (a, b, d), w in edges.items()}})

    def add(self, shot, T):
        edges = {(a, b, d): weight(q, k) for a, b, d, q, k, door in shot['segments'] if q >= 0.18}
        cand = anchor(edges, self.level, T)
        if self.wp:                         # prefer the direction we already know unless another is much better
            same = [c for c in cand if c[1] == self.wp]
            if same and same[0][0] > cand[0][0] - 4: cand = [same[0]] + [c for c in cand if c is not same[0]]
        good = bool(cand) and cand[0][3] >= 7 and not (len(cand) > 1 and cand[0][0] - cand[1][0] < 4)
        if not good:
            return self._join(shot, edges)
        s, ex, off, own = cand[0]
        if self.wp and ex != self.wp: return {'ok': False, 'conflict': ex, 'own': own}
        self.wp = ex; self._merge(shot, edges, off)
        return {'ok': True, 'waypoint': ex, 'score': round(s, 1), 'margin': round(s - cand[1][0], 1) if len(cand) > 1 else None}

    def _join(self, shot, edges):           # no clear waypoint room in view: overlap with the known map
        few = sum(w > 0.3 for w in edges.values()) < 60
        why = {'ok': False, 'reason': 'too little of the map is explored yet, walk into the next room' if few else 'waypoint room not recognised'}
        known = {e for e, w in self.edges.items() if w > 0.5}
        if len(known) < 25: return why
        votes = {}
        for a, b, d in (e for e, w in edges.items() if w > 0.5):
            for x, y, o in known:
                if o == d: votes[(a - x, b - y)] = votes.get((a - x, b - y), 0) + 1
        if not votes: return why
        off, n = max(votes.items(), key=lambda q: q[1]); second = max((v for k, v in votes.items() if k != off), default=0)
        if n < 18 or n < 1.35 * second: return why
        self._merge(shot, edges, off)
        return {'ok': True, 'waypoint': self.wp, 'joined': n}

    def evidence(self, T, min_seen=2.5):
        """{cell: (scores best first, score of 'no room here', share of seen walls explained)}"""
        Z, rooms = T.levels[self.level]; out = {}
        for c, obs in split(self.edges, Z).items():
            tot = sum(obs.values())
            if sum(w for w in obs.values() if w > 0.3) < min_seen or max(map(abs, c)) > 3: continue
            sc = sorted(((room_score(obs, r['edges']), r) for r in rooms), key=lambda q: -q[0])
            out[c] = (sc, room_score(obs, frozenset()), sum(w for e, w in obs.items() if e in sc[0][1]['edges']) / tot)
        return out


def clue_lines(maps, T, difficulty='hell', town=None, floor=-9.0):
    """Solver input from all levels seen so far, plus a readable summary."""
    L = [f'difficulty {difficulty}'] + ([f'town {town} soft'] if town else []); info = {}
    for level, m in maps.items():
        if not m.wp: continue
        L += [f'stop {level}', f'room 0,0 exits={m.wp}']; nxt = DIRS[m.wp]; rooms = []
        for c, (sc, none, share) in sorted(m.evidence(T).items()):
            if c == (0, 0): continue
            best = sc[0][0]; temp = min(1.0, max(0.15, (share - 0.35) / 0.35))   # trust cells that fit a room well
            val = lambda s: max(floor, (s - best) * temp)
            by = {}
            for s, r in sc: by.setdefault(r['exits'], s)
            if level in LOOKS:
                seen = {}
                for s, r in sc:
                    k = f"{r['preset']}.{r['file']}" if level in VARIANTS else str(r['preset'])
                    if k not in seen and val(s) > floor: seen[k] = val(s)
                body = ' '.join(f'{k}={v:.2f}' for k, v in seen.items())
            else:
                body = ' '.join(f'{ex}={val(s):.2f}' for ex, s in by.items())
            L.append(f'weigh {c[0]},{c[1]} {body} default={floor} absent={max(floor, (none - best) * temp):.2f}')
            if c == nxt and share > 0.6:                   # hard clue only when few readings are plausible
                ok = [ex for ex, s in by.items() if s > best - 5.0 and OPP[m.wp] in ex]
                if 0 < len(ok) <= 6: L.append(f'room {c[0]},{c[1]} exits=' + '|'.join(ok))
            alt = sorted(by.values(), reverse=True)
            rooms.append({'cell': c, 'exits': sc[0][1]['exits'], 'margin': round(alt[0] - alt[1], 1) if len(alt) > 1 else 0, 'fit': round(share, 2)})
        info[level] = rooms
    return '\n'.join(L) + '\n', info


def solve(text, exe=None, table=None, limit=5, stop=None, slow=None):
    """Run the solver. stop() -> True cancels it (returns None); slow() is called once if it takes over 3 seconds."""
    base = os.path.join(os.path.dirname(HERE), 'seedfinder'); t0 = time.time()
    cmd = [exe or os.path.join(base, 'seedfinder'), 'solve', table or os.path.join(base, 'data', 'seeds.idx'), '--limit', str(limit)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True); give = text
    try:
        while True:
            try: out, _ = p.communicate(give, timeout=0.3); return json.loads(out)
            except subprocess.TimeoutExpired: give = None
            if stop and stop(): return None
            if slow and time.time() - t0 > 3: slow(); slow = None
    finally:
        if p.poll() is None: p.kill(); p.communicate()


def facts(seed, exe=None):
    """{'summoner': 'W', 'tomb': 5, ...} for a seed (tomb counted from the left), or {}."""
    try: return json.loads(subprocess.run([exe or os.path.join(os.path.dirname(HERE), 'seedfinder', 'seedfinder'), 'facts', str(seed)], capture_output=True, text=True).stdout)
    except (OSError, ValueError): return {}
