#!/usr/bin/env python3
"""Build templates.json (wall segments of every room variant) from your own D2R installation.
usage: build_templates.py "<Diablo II Resurrected folder>" """
import csv, io, json, os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from casc import Casc

LEVELS = {  # name: (level id, first preset of the group, last, tiles per room)
    'jail1': (29, 206, 251, 12), 'catacombs2': (35, 258, 298, 12), 'sewers2': (48, 302, 348, 12),
    'durance2': (101, 754, 795, 12), 'halls': (57, 414, 490, 16)}

def ds1(d):
    o = 0
    def i():
        nonlocal o; v = struct.unpack_from('<i', d, o)[0]; o += 4; return v
    ver = i(); w = i() + 1; h = i() + 1
    if ver >= 8: i()
    if ver >= 10: i()
    if ver >= 3:
        for _ in range(i()): o = d.index(b'\0', o) + 1
    if 9 <= ver <= 13: o += 8
    nw = i(); nf = i() if ver >= 16 else 1
    walls = []
    for _ in range(nw):
        a = struct.unpack_from(f'<{w*h}I', d, o); o += 4 * w * h
        b = struct.unpack_from(f'<{w*h}I', d, o); o += 4 * w * h
        walls.append((a, b))
    floors = []
    for _ in range(nf):
        floors.append(struct.unpack_from(f'<{w*h}I', d, o)); o += 4 * w * h
    ds1.floors = floors
    return w, h, walls

# Automap cells of the white step lines (read off the game's own automap art): segments relative to the tile
STEPS = {640: [(0, 0, 0)], 695: [(0, 0, 0)], 642: [(0, 0, 0)], 641: [(0, 0, 1)], 696: [(0, 0, 1)], 643: [(0, 0, 1)],
         644: [(0, 0, 0), (0, 0, 1)], 645: [], 647: [(0, 0, 1), (0, -1, 1)]}

def steps(d, rules):
    """White step lines of a Durance room, stored with direction 2 (along +x) and 3 (along +y)."""
    w, h, walls = ds1(d); floors = ds1.floors; E = set()
    def put(k, cel):
        for dx, dy, o in STEPS.get(cel, []):
            if k // w + dy >= 0: E.add((k % w + dx, k // w + dy, o + 2))
    for f in floors:
        for k, v in enumerate(f):
            if v and not v >> 31: put(k, rules.get((v >> 20 & 0x3f, v >> 8 & 0xff)))
    for a, b in walls:
        for k, (p, q) in enumerate(zip(a, b)):
            if p and not p >> 31 and p >> 20 & 0x3f == 47:
                put(k, {1: 641, 2: 640, 3: 644, 4: 644, 5: 643, 6: 642}.get(q & 0xff))
    return E

def edges(d, skip=()):
    """Automap segments: (x, y, dir) with dir 0 along +x (north side of tile), 1 along +y (west side)."""
    w, h, walls = ds1(d); E = {}
    for a, b in walls:
        for k, (p, q) in enumerate(zip(a, b)):
            if not p & 0xff and not p >> 8 & 0xff and not p: continue
            if p >> 31 or p >> 20 & 0x3f in skip: continue
            x, y, o = k % w, k // w, q & 0xff
            if o in (1, 5, 8, 3, 4): E[(x, y, 1)] = max(E.get((x, y, 1), 0), o == 8)
            if o in (2, 6, 9, 3, 4): E[(x, y, 0)] = max(E.get((x, y, 0), 0), o == 9)
    return w, h, E

def town(c):
    """Outer fence of the four Rogue Encampment layouts: rectangle size and the gap on the exit side."""
    out = {}
    for side in 'NESW':
        w, h, walls = ds1(c.get(f'data/global/tiles/act1/town/town{side.lower()}1.ds1')); E = set()
        for a, b in walls:
            for k, (p, q) in enumerate(zip(a, b)):
                if not p & 0xffff or p >> 31 or p >> 20 & 0x3f: continue          # style 0 = fence
                x, y, o = k % w, k // w, q & 0xff
                if o in (1, 5, 8, 3, 4): E.add((x, y, 1))
                if o in (2, 6, 9, 3, 4): E.add((x, y, 0))
        rows = {}; cols = {}
        for x, y, d in E: (rows if d == 0 else cols).setdefault(y if d == 0 else x, []).append(x if d == 0 else y)
        y0, y1 = sorted(y for y, v in rows.items() if len(v) >= 20); x0 = next(x for x, v in cols.items() if len(v) >= 18); x1 = x0 + 30
        rect = {(x, y, 0) for x in range(x0, x1) for y in (y0, y1)} | {(x0, y, 1) for y in range(y0, y1)} | {e for e in E if e[0] == x1 and e[2] == 1 and y0 <= e[1] < y1}
        out[side] = {'size': [x1 - x0, y1 - y0], 'fence': sorted([x - x0, y - y0, d] for x, y, d in rect & E), 'gap': sorted([x - x0, y - y0, d] for x, y, d in rect - E)}
        print(f"town {side}: fence {x1-x0}x{y1-y0}, {len(out[side]['fence'])} pieces, missing {len(out[side]['gap'])}: {out[side]['gap'][:6]}")
    return out

def main(game):
    c = Casc(game)
    rows = {int(r['Def']): r for r in csv.DictReader(io.StringIO(c.get('data/global/excel/lvlprest.txt').decode('latin1')), delimiter='\t') if (r.get('Def') or '').isdigit()}
    out = {'version': c.version, 'levels': {}}; rules = {}
    for r in csv.DictReader(io.StringIO(c.get('data/global/excel/automap.txt').decode('latin1')), delimiter='\t'):
        if r['LevelName'] == '3 Kurast' and r['TileName'] == 'fl':
            for q in range(int(r['StartSequence']), int(r['EndSequence']) + 1): rules[int(r['Style']), q] = int(r['Cel1'])
    for name, (lv, a, b, size) in LEVELS.items():
        T = []
        for d in range(a, b + 1):
            r = rows.get(d)
            if not r or 'Tal' in r['Name'] or 'Kaa' in r['Name'] or name == 'halls' and 'Tomb' not in r['Name']: continue
            n = r['Name'].split(' - ')[-1]; m = re.search(r'\b([NSEW]{1,4})$', n.strip())
            if not m: continue
            kind = next((k for k in ('Waypoint', 'Prev', 'Next', 'Theme') if k in n), 'Normal' if d - a < 15 else 'Other')
            for f in range(int(r['Files'] or 0)):
                fn = r.get(f'File{f+1}')
                if not fn or fn == '0': continue
                raw = c.get('data/global/tiles/' + fn.replace('\\', '/')); w, h, E = edges(raw, (47,) if name == 'durance2' else ())
                if name == 'durance2': E.update(dict.fromkeys(steps(raw, rules), False))
                T.append({'preset': d, 'file': f, 'kind': kind, 'exits': m.group(1), 'name': n, 'w': w, 'h': h, 'edges': [[*k, int(v)] for k, v in sorted(E.items())]})
        out['levels'][name] = {'id': lv, 'size': size, 'rooms': T}
        print(f"{name}: {len(T)} room shapes, {sum(t['kind'] == 'Waypoint' for t in T)} waypoint rooms")
    out['town'] = town(c)
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates.json'), 'w'))

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/Library/Application Support/CrossOver/Bottles/Battle.net Desktop App/drive_c/Program Files (x86)/Diablo II Resurrected'))
