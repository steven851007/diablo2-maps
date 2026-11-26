#!/usr/bin/env python3
"""Matcher + solver on games it has never seen: rooms are drawn from the generator and templates,
only a walked area is visible, some walls are missing and noise is added. (The image step is not tested here.)"""
import os, random, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import match as M
T = M.Templates(); EXE = os.path.join(HERE, '..', 'seedfinder', 'seedfinder'); N = int(sys.argv[1]) if len(sys.argv) > 1 else 40; rnd = random.Random(3)
BITS = {1: 'W', 8: 'N', 2: 'E', 4: 'S'}
def game_level(seed, stop):
    rows = [tuple(map(int, l.split(','))) for l in subprocess.run([EXE, 'dump', str(seed), {'jail1': '29', 'catacombs2': '35', 'sewers2': '48', 'durance2': '101', 'halls': '57'}[stop], '2'], capture_output=True, text=True).stdout.split()]
    w = next(r for r in rows if r[3] == 3); return {(r[0] - w[0], r[1] - w[1]): r for r in rows}
def look(stop, r):
    ex = ''.join(v for b, v in BITS.items() if r[2] & b); kind = {1: 'Prev', 2: 'Next', 3: 'Waypoint'}.get(r[3])
    c = [t for t in T.levels[stop][1] if (t['preset'] == r[4] if r[4] else (t['kind'] == kind if kind else t['kind'] in ('Normal', 'Theme')) and t['exits'] == M.canon(ex))]
    v = [t for t in c if t['file'] == r[5]] if stop in M.VARIANTS else c
    return rnd.choice(v or c) if c else None
def shot(stop, rooms, steps, miss, noise):
    Z = T.levels[stop][0]; wp = M.canon(''.join(v for b, v in BITS.items() if rooms[(0, 0)][2] & b)); path = [(0.0, 0.0)]; cur = (0, 0); came = None
    nxt = M.DIRS[wp]; path.append(nxt)
    if steps > 1:                                   # walk on into one neighbour
        ex = [d for d in M.canon(''.join(v for b, v in BITS.items() if rooms[nxt][2] & b)) if d != M.OPP[wp]]
        if ex: d = M.DIRS[rnd.choice(ex)]; path.append((nxt[0] + d[0] * .55, nxt[1] + d[1] * .55))
    pts = []
    for (x0, y0), (x1, y1) in zip(path, path[1:]): pts += [((x0 + (x1 - x0) * k / 12 + .5) * Z, (y0 + (y1 - y0) * k / 12 + .5) * Z) for k in range(13)]
    vis = lambda a, b: any(abs((a - x) - (b - y)) < 7.2 and abs((a - x) + (b - y)) < 10 for x, y in pts)   # automap reveal, as measured
    u, v = rnd.randrange(-20, 20), rnd.randrange(-20, 20); seg = {}
    for (cx, cy), r in rooms.items():
        t = look(stop, r)
        if t is None: continue
        for x, y, d in t['edges']:
            a, b = cx * Z + x, cy * Z + y
            if vis(a + .5, b + .5) and rnd.random() > miss: seg[(a, b, d)] = (rnd.uniform(.45, .9), 1)
    real = len(seg)
    for _ in range(int(noise * real)):
        x, y = rnd.choice(pts); a, b, d = int(x + rnd.gauss(0, 9)), int(y + rnd.gauss(0, 9)), rnd.randrange(2)
        for k in range(rnd.choice((1, 2, 4))): seg.setdefault((a + k * (d == 0), b + k * (d == 1), d), (rnd.uniform(.2, .6), rnd.random() < .5))
    return {'segments': [(a + u, b + v, d, q, int(k), 0) for (a, b, d), (q, k) in seg.items()], 'width': 3024, 'height': 1986, 'ox': 1512.0, 'oy': 975.0, 'tx': 32.4, 'ty': 16.2}
for title, stops, steps, miss, noise in (('4 stops, next room + a neighbour, light noise', ['catacombs2', 'sewers2', 'jail1', 'durance2'], 2, .06, .10), ('4 stops, heavy noise', ['catacombs2', 'sewers2', 'jail1', 'durance2'], 2, .15, .40),
                                         ('3 stops, light noise', ['catacombs2', 'sewers2', 'jail1'], 2, .06, .10), ('4 stops, next room only', ['catacombs2', 'sewers2', 'jail1', 'durance2'], 1, .06, .10)):
    first = top5 = sure = wrongsure = anch = tot = 0; t0 = time.time()
    for _ in range(N):
        seed = rnd.randrange(1 << 31); maps = {}
        for s in stops:
            m = maps[s] = M.LevelMap(s); rooms = game_level(seed, s); r = m.add(shot(s, rooms, steps, miss, noise), T); tot += 1
            anch += bool(r['ok'] and m.wp == ''.join(v for b, v in BITS.items() if rooms[(0, 0)][2] & b))
        j = M.solve(M.clue_lines(maps, T)[0], limit=5); rk = [x[0] for x in j.get('ranked', [])]; n = sum(1 for m in maps.values() if m.wp)
        first += bool(rk) and rk[0] == seed; top5 += seed in rk
        if rk and n >= 3 and j['confidence'] >= .97: sure += rk[0] == seed; wrongsure += rk[0] != seed
    print(f'{title:48s} waypoint right {anch}/{tot}  seed first {first}/{N}  top 5 {top5}/{N}  declared found: {sure} right, {wrongsure} wrong   {(time.time()-t0)/N:.1f}s each', flush=True)
