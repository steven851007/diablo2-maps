#!/usr/bin/env python3
"""Generator check against real map data, then (if the table exists) solver round trips."""
import json, os, subprocess, sys, tempfile, random, time
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); EXE = os.path.join(D, 'seedfinder'); TABLE = os.path.join(D, 'data', 'seeds.idx')
run = lambda *a, **k: subprocess.run([EXE, *map(str, a)], capture_output=True, text=True, **k).stdout
maps = rooms = town = facts = 0; bad = []
for line in open(os.path.join(D, 'test', 'golden.txt')):
    p = line.split()
    if not p or p[0] == '#': continue
    if p[0] == 'town':
        got = run('describe', p[1]).split('town ')[1].split()[0]; town += 1
        if got != p[2]: bad.append(line.strip())
    elif p[0] in ('summoner', 'tomb', 'nihlathak', 'bigtomb'):
        got = json.loads(run('facts', p[1])); facts += 1
        if str(got[{'summoner': 'summoner', 'tomb': 'tombLevel', 'nihlathak': 'nihlathak', 'bigtomb': 'bigTombLevel'}[p[0]]]) != p[2]: bad.append(line.strip())
    elif p[0] == 'map':
        got = [tuple(map(int, x.split(','))) for x in run('dump', p[1], p[2], 2).split()]; want = sorted(tuple(map(int, x.split(','))) for x in p[4:])
        wp = [f'{g[0]},{g[1]}' for g in got if g[3] == 3]; maps += 1; rooms += len(want)
        if sorted((g[0], g[1], g[4]) for g in got) != want or wp != [p[3]]: bad.append(' '.join(p[:4]))
print(f'generator: {maps} maps, {rooms} rooms, {town} towns, {facts} Summoner/Nihlathak/tomb facts, {len(bad)} wrong', bad[:5])
if os.path.exists(TABLE):
    rnd = random.Random(7); N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    def solve(text, *o):
        j = json.loads(run('solve', TABLE, '--limit', 5000, *o, input=text)); return j
    ONLY = sys.argv[2] if len(sys.argv) > 2 else ''
    for name, stops, opts, edit in (('town + 3 stops', ['catacombs2', 'sewers2', 'jail1'], [], None), ('+ Durance 2', ['catacombs2', 'sewers2', 'jail1', 'durance2'], [], None),
                                    ('normal difficulty', ['catacombs2', 'sewers2', 'jail1', 'durance2'], [], 'normal'),
                                    ('no variants known', ['catacombs2', 'sewers2', 'jail1', 'durance2'], [], 'plain'), ('no Sewers', ['catacombs2', 'jail1', 'durance2'], [], None), ('no Catacombs', ['sewers2', 'jail1', 'durance2'], [], None),
                                    ('one wrong clue, tolerate 1', ['catacombs2', 'sewers2', 'jail1', 'durance2'], ['--tolerate', 1], 'wrong')):
        if ONLY not in name: continue
        ok = uniq = first = 0; ms = []; n = []; M = N if edit != 'wrong' else max(8, N // 4)
        for _ in range(M):
            s = rnd.randrange(1 << 31); t = run('describe', s, 'normal' if edit == 'normal' else 'hell', *stops)
            L = t.splitlines()
            if edit == 'plain': L = [' '.join(w for w in l.split() if not w.startswith(('preset', 'variant'))) for l in L]
            if edit == 'wrong':
                k = rnd.choice([i for i, l in enumerate(L) if l.startswith('room')]); w = L[k].split(); e = set(w[2][6:]); e ^= {rnd.choice('WNES')}; e = e or {'W', 'E'}
                L[k] = f'{w[0]} {w[1]} exits={"".join(e)}'
            j = solve('\n'.join(L) + '\n', *opts); ok += s in j['seeds']; uniq += j['matches'] == 1; first += bool(j['seeds']) and j['seeds'][0] == s; ms.append(j['ms']); n.append(j['matches'])
        ms.sort(); n.sort(); print(f'{name:28s} found {ok}/{M}  unique {uniq}/{M}  most left {n[-1]}  time median {ms[len(ms)//2]:.0f} ms, worst {ms[-1]:.0f} ms', flush=True)
sys.exit(bool(bad))
