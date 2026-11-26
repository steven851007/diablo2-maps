"""Minimal read-only reader for the local D2R archive (CASC). Nothing is written to the game folder."""
import glob, os, struct, zlib

class Casc:
    def __init__(self, game):
        self.data = os.path.join(game, 'Data')
        rows = [l.rstrip('\n').split('|') for l in open(os.path.join(game, '.build.info'))]
        head = [h.split('!')[0] for h in rows[0]]
        key = rows[1][head.index('Build Key')]
        self.version = rows[1][head.index('Version')]
        cfg = {}
        for l in open(f'{self.data}/config/{key[:2]}/{key[2:4]}/{key}'):
            if '=' in l:
                k, v = l.split('=', 1); cfg[k.strip()] = v.split()
        self.idx, latest = {}, {}
        for f in glob.glob(self.data + '/data/*.idx'):
            b = os.path.basename(f); latest[b[:2]] = max(latest.get(b[:2], ''), b)
        for b in latest.values():
            d = open(f'{self.data}/data/{b}', 'rb').read(); n = struct.unpack_from('<I', d, 0x20)[0]
            for o in range(0x28, 0x28 + n, 18):
                off = int.from_bytes(d[o + 9:o + 14], 'big')
                self.idx.setdefault(d[o:o + 9], (off >> 30, off & 0x3fffffff, struct.unpack_from('<I', d, o + 14)[0]))
        self.nested = {bytes.fromhex(v[1])[:9] for k, v in cfg.items() if k.startswith('vfs-') and len(v) == 2 and not k.endswith('size')}
        self.files = {}
        self._tvfs(self._read(bytes.fromhex(cfg['vfs-root'][1])), '', 0)
        self.lower = {k.split(':')[-1].lower(): k for k in self.files}

    def _read(self, ekey):
        a, o, s = self.idx[ekey[:9]]
        with open(f'{self.data}/data/data.{a:03d}', 'rb') as f:
            f.seek(o + 30); return self._blte(f.read(s - 30))

    @staticmethod
    def _blte(b):
        if b[:4] != b'BLTE': raise ValueError('not BLTE')
        hs = struct.unpack_from('>I', b, 4)[0]
        if hs == 0: chunks = [(8, len(b) - 8)]
        else:
            n = int.from_bytes(b[9:12], 'big'); o, p, chunks = 12, hs, []
            for _ in range(n):
                c = struct.unpack_from('>I', b, o)[0]; chunks.append((p, c)); p += c; o += 24
        out = b''
        for p, c in chunks:
            m, x = b[p:p + 1], b[p + 1:p + c]
            if m == b'N': out += x
            elif m == b'Z': out += zlib.decompress(x)
            else: raise ValueError('unsupported block')
        return out

    def _tvfs(self, b, prefix, depth):
        if b[:4] != b'TVFS': raise ValueError('not TVFS')
        eks = b[6]; _, po, ps, vo, _, co, cs = struct.unpack_from('>7I', b, 8)
        cw = 4 if cs > 0xffffff else 3 if cs > 0xffff else 2 if cs > 0xff else 1
        def spans(v):
            o = vo + v; n = b[o]; o += 1; sp = []
            for _ in range(n):
                o += 8; c = int.from_bytes(b[o:o + cw], 'big'); o += cw; sp.append(b[co + c:co + c + eks])
            return sp
        def walk(o, end, base):
            path = base
            while o < end:
                p = path
                if b[o] == 0: p += '/'; o += 1
                if o < end and b[o] != 0xff:
                    n = b[o]; p += b[o + 1:o + 1 + n].decode('latin1'); o += 1 + n
                if o < end and b[o] == 0: p += '/'; o += 1
                if o < end and b[o] == 0xff:
                    v = struct.unpack_from('>I', b, o + 1)[0]; o += 5
                    if v & 0x80000000:
                        e = o + (v & 0x7fffffff) - 4; walk(o, e, p); o = e
                    else:
                        sp = spans(v)
                        if len(sp) == 1 and sp[0][:9] in self.nested and depth < 3:
                            try: self._tvfs(self._read(sp[0]), p + ':', depth + 1); path = base; continue
                            except (KeyError, ValueError): pass
                        self.files[p] = sp
                    path = base
                else: path = p
        s, e = po, po + ps
        if b[s] == 0xff: s += 5
        walk(s, e, prefix)

    def get(self, path):
        k = self.lower.get(path.lower())
        return None if k is None else b''.join(self._read(x) for x in self.files[k])
