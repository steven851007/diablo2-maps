"""Read-only page for a phone on the same Wi-Fi: seed facts and maps. Serves three fixed things, no files."""
import json, subprocess, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = '''<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<meta name=apple-mobile-web-app-capable content=yes><title>D2 maps</title><style>
*{box-sizing:border-box}body{margin:0;background:#0e1014;color:#e8e3d8;font:17px/1.35 -apple-system,system-ui,sans-serif}
header{position:sticky;top:0;z-index:1;padding:10px 14px;background:#191c22;border-bottom:1px solid #2f343d}
#seed{font-size:14px;color:#a9a59b}#facts{display:flex;gap:18px;flex-wrap:wrap}#facts b{color:#f0c674}
#tombs{letter-spacing:3px;color:#6b7078}#tombs i{font-style:normal;color:#f0c674}
nav{display:flex;gap:8px;overflow-x:auto;margin-top:8px}nav a{flex:none;padding:7px 12px;border-radius:16px;background:#2a2e37;color:#e8e3d8;text-decoration:none;font-size:15px}
nav a.on{background:#e8e3d8;color:#14161b}nav a.tz{box-shadow:inset 0 0 0 2px #b07cff}
#tabs{display:flex;gap:6px;margin-top:8px}#tabs a{flex:1;text-align:center;padding:8px;border-radius:8px;background:#23272f;color:#a9a59b;text-decoration:none;font-weight:600}#tabs a.on{background:#f0c674;color:#14161b}
.info{margin:0 4px 6px;color:#a9a59b;font-size:14px}
section{padding:12px 10px 6px;scroll-margin-top:240px}h2{margin:0 4px 6px;font-size:18px;display:flex;justify-content:space-between;gap:10px}h2 small{color:#a9a59b;font-weight:400}h2 span{color:#3cdc78;white-space:nowrap}
img{display:block;width:100%;max-height:78vh;object-fit:contain;background:#0e1014;border:1px solid #22262e;border-radius:8px}
#wait{padding:60px 24px;text-align:center;color:#a9a59b}footer{padding:14px;color:#6f747c;font-size:13px}
</style><header><div id=facts></div><div id=seed></div><div id=tabs><a data-t=boss href="#">Bosses</a><a data-t=herald href="#">Heralds</a></div><nav id=nav></nav></header><div id=wait>Waiting for a seed</div><main id=main></main>
<footer id=foot></footer><script>
let S=null,tab='boss',zone=null,shown='',$=i=>document.getElementById(i),arrow={'top left':'\u2196','top right':'\u2197','bottom right':'\u2198','bottom left':'\u2199',top:'\u2191',bottom:'\u2193',left:'\u2190',right:'\u2192'};
function el(t,txt){let e=document.createElement(t);if(txt)e.textContent=txt;return e}
function facts(s){$('seed').textContent=s.status||'';let f=$('facts');f.replaceChildren();
 if(s.summoner){for(const [n,k] of [['Summoner','summoner'],['Nihlathak','nihlathak']]){let d=el('div',n+' ');d.append(el('b',arrow[s[k+'Arrow']]+' '+s[k]));f.append(d)}
  let t=el('div','Duriel ');t.append(el('b',s.tombText));let q=el('span');q.id='tombs';q.append(' ');for(let i=1;i<8;i++)q.append(i==s.tomb?el('i','\u25cf'):'\u25cb');t.append(q);f.append(t)}}
function maps(group,list,v){let m=$('main');for(const a of list){let c=el('section');c.id='m'+a.level;let h=el('h2',a.title+' ');if(a.note)h.append(el('small',a.note));if(a.start)h.append(el('span','start '+arrow[a.start]+' '+a.start));c.append(h);
  if(a.info){let p=el('div',a.info);p.className='info';c.append(p)}
  let i=el('img'),full=false,src=()=>i.src='/map/'+group+'/'+a.level+(full?'/full':'/route')+'?v='+v;i.alt=a.title;src();i.onclick=()=>{full=!full;src()};c.append(i);m.append(c)}}
function draw(){let s=S,n=$('nav');if(!s)return;facts(s);for(const t of document.querySelectorAll('#tabs a'))t.className=t.dataset.t==tab?'on':'';
 let zs=s.zones||[],act=zs.find(z=>z.active);if(!zone&&act)zone=act.key;let z=zs.find(z=>z.key==zone),sig=JSON.stringify([tab,zone,s.seed,s.note,s.mapsVersion,tab=='boss'?s.maps:[z,zs.map(q=>[q.key,q.active,q.state])]]);
 if(sig==shown)return;shown=sig;$('main').replaceChildren();n.replaceChildren();let note=s.note||'';
 if(tab=='boss'){for(const a of s.maps){let k=el('a',a.title);k.href='#m'+a.level;n.append(k)}maps('boss',s.maps,s.mapsVersion);
  $('foot').textContent='Blue: where you arrive. Red: exit or boss. Purple: shrine that can give Experience or another boost. White: Cairn Stones, Tree. Gold box: super chest (large = within 30 steps of the route). Tap a map for the whole level.'}
 else{note=s.seed?'':'Waiting for a seed';let here=null;
  for(const q of zs){let k=el('a',(q.active?'\u2605 ':'')+q.title);k.href='#';k.className=(q.key==zone?'on ':'')+(q.active?'tz':'');if(q.key==zone)here=k;k.onclick=e=>{e.preventDefault();zone=q.key;scrollTo(0,0);if(s.seed&&q.state!='ready')fetch('/zone/'+q.key);draw()};if(q.active)n.prepend(k);else n.append(k)}
  if(here)here.scrollIntoView({block:'nearest',inline:'nearest'});
  if(z&&s.seed){if(z.state=='ready')maps(z.key,z.maps,s.mapsVersion);else{note=z.state=='failed'?'The map site did not answer. Tap the zone to try again.':'Loading '+z.title}}
  else if(s.seed)note='Choose a zone';
  $('foot').textContent='Start at blue, follow 1 to 10, green to red. Purple: shrine that can give Experience or another boost. White: Cairn Stones, Tree. Gold box: super chest. \u2605: active terror zone in your last screenshot. The percentage is the floor you pass within 24 steps.'}
 $('wait').textContent=note;$('wait').hidden=!note}
for(const t of document.querySelectorAll('#tabs a'))t.onclick=e=>{e.preventDefault();tab=t.dataset.t;scrollTo(0,0);let z=(S&&S.zones||[]).find(z=>z.key==zone)||(S&&S.zones||[]).find(z=>z.active);if(tab=='herald'&&z&&S.seed&&z.state=='idle'){zone=z.key;fetch('/zone/'+z.key)}draw()};
async function tick(){try{let r=await fetch('/state',{cache:'no-store'});S=await r.json();document.body.style.opacity=1;for(const i of document.images)if(i.complete&&!i.naturalWidth)i.src=i.src.replace(/(&r=.*)?$/,'&r='+Date.now());draw()}catch(e){document.body.style.opacity=.45;$('seed').textContent='The watcher is not running'}setTimeout(tick,2000)}tick()
</script></html>'''

ORDINAL = ['', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh']


def tomb_text(n): return f'{ORDINAL[n]} tomb from the left'


def lan_address():
    """This Mac's own address in the local network, or None."""
    run = lambda *a: subprocess.run(a, capture_output=True, text=True).stdout
    dev = [l.split()[1] for l in run('route', '-n', 'get', 'default').splitlines() if l.strip().startswith('interface:')]
    for d in dev + ['en0', 'en1', 'en2', 'en3', 'en4', 'en5']:
        ip = run('ipconfig', 'getifaddr', d).strip()
        if ip.startswith(('192.168.', '10.')) or ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31: return ip
    return None


class Phone:
    """Holds what the page shows. Methods may be called from any thread. on_zone(key) is called when a zone is tapped."""
    def __init__(self, zones=()):
        self.lock = threading.RLock(); self.n = 0; self.maps = {}; self.url = None; self.on_zone = None
        self.names = list(zones); self.active = []; self.zones = {}; self.base = {}; self.clear()

    def clear(self, status='New game'): self._base({'status': status, 'note': 'Waiting for a seed', 'maps': []})
    def status(self, text): self._base({'status': text, 'note': 'Waiting for a seed', 'maps': []})

    def found(self, seed, facts, side, areas=None, note=''):
        s = {'status': f'Seed {seed}', 'seed': seed, 'note': '' if areas else note, 'maps': [self.entry(a) for a in areas or []]}
        if facts: s.update(summoner=side['summoner'][0], summonerArrow=side['summoner'][1], nihlathak=side['nihlathak'][0], nihlathakArrow=side['nihlathak'][1], tomb=facts['tomb'], tombText=tomb_text(facts['tomb']))
        with self.lock:
            if self.base.get('seed') != seed: self.zones = {}; self.maps = {}
            self._base(s); self._add('boss', areas or [])

    def set_active(self, keys):
        with self.lock: self.active = list(keys); self.n += 1

    def set_zone(self, seed, key, state, areas=None):
        with self.lock:
            if self.base.get('seed') != seed: return
            self.zones[key] = {'state': state, 'maps': [self.entry(a) for a in areas or []]}; self._add(key, areas or []); self.n += 1

    @staticmethod
    def entry(a): return {k: a.get(k, '') for k in ('title', 'note', 'level', 'start', 'info')}

    def _add(self, group, areas): self.maps = {**self.maps, **{(group, a['level'], k): a[k] for a in areas for k in ('route', 'full')}}

    def _base(self, s):
        with self.lock:
            self.n += 1; self.base = s
            if 'seed' not in s: self.zones = {}; self.maps = {}

    def view(self):
        with self.lock:
            z = [{'key': k, 'title': t, 'active': k in self.active, **self.zones.get(k, {'state': 'idle', 'maps': []})} for k, t in self.names]
            return {**self.base, 'zones': z, 'version': self.n, 'mapsVersion': self.base.get('seed', 0)}, self.maps

    def start(self, host=None, port=8420):
        host = host or lan_address()
        if not host: return None
        phone = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                p = urllib.parse.urlsplit(self.path).path.strip('/').split('/')
                state, maps = phone.view()
                if p == ['']: return self.out('text/html; charset=utf-8', PAGE)
                if p == ['state']: return self.out('application/json', json.dumps(state))
                if len(p) == 4 and p[0] == 'map' and p[2].isdigit() and (p[1], int(p[2]), p[3]) in maps: return self.out('image/svg+xml', maps[p[1], int(p[2]), p[3]])
                if len(p) == 2 and p[0] == 'zone' and p[1] in dict(phone.names):
                    if phone.on_zone: phone.on_zone(p[1])
                    return self.out('text/plain', 'ok')
                self.send_error(404)

            def out(self, kind, text):
                b = text.encode(); self.send_response(200); self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(b))); self.send_header('Cache-Control', 'max-age=86400' if 'svg' in kind else 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff'); self.end_headers()
                try: self.wfile.write(b)
                except OSError: pass

            def log_message(self, *a): pass
            timeout = 15

        for k in range(5):                                        # next port if this one is taken
            try: srv = ThreadingHTTPServer((host, port + k), H)
            except OSError: continue
            srv.daemon_threads = True; threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.url = f'http://{host}:{port + k}/'; return self.url
        return None


# --- small QR code (version 3, level L, byte mode, up to 53 characters) ---
def qr(text):
    data = text.encode(); assert len(data) <= 53
    bits = '0100' + f'{len(data):08b}' + ''.join(f'{b:08b}' for b in data); bits += '0' * min(4, 440 - len(bits)); bits += '0' * (-len(bits) % 8)
    cw = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
    for k in range(55 - len(cw)): cw.append((0xEC, 0x11)[k & 1])
    exp, log, x = [0] * 512, [0] * 256, 1
    for i in range(255):
        exp[i], log[x] = x, i; x <<= 1
        if x & 256: x ^= 0x11D
    for i in range(255, 512): exp[i] = exp[i - 255]
    mul = lambda a, b: exp[log[a] + log[b]] if a and b else 0
    g = [1]
    for i in range(15): g = [(g[j] if j < len(g) else 0) ^ (mul(g[j - 1], exp[i]) if j else 0) for j in range(len(g) + 1)]
    rem = cw + [0] * 15
    for i in range(55):
        c = rem[i]
        for j in range(16): rem[i + j] ^= mul(g[j], c)
    allbits = ''.join(f'{b:08b}' for b in cw + rem[55:]) + '0' * 7
    N = 29; M = [[None] * N for _ in range(N)]
    for oy, ox in ((0, 0), (0, N - 7), (N - 7, 0)):
        for y in range(-1, 8):
            for x in range(-1, 8):
                if 0 <= oy + y < N and 0 <= ox + x < N: M[oy + y][ox + x] = int(0 <= x < 7 and 0 <= y < 7 and (x in (0, 6) or y in (0, 6) or 2 <= x <= 4 and 2 <= y <= 4))
    for y in range(-2, 3):
        for x in range(-2, 3): M[22 + y][22 + x] = int(max(abs(x), abs(y)) != 1)
    for i in range(8, N - 8): M[6][i] = M[i][6] = int(i % 2 == 0)
    M[N - 8][8] = 1; fmt = '111011111000100'                        # level L, mask 0
    for i in range(15):
        b = int(fmt[i])
        if i < 6: M[8][i] = b
        elif i < 8: M[8][i + 1] = b
        elif i == 8: M[7][8] = b
        else: M[14 - i][8] = b
        if i < 7: M[N - 1 - i][8] = b
        else: M[8][N - 15 + i] = b
    k, up, c = 0, True, N - 1
    while c > 0:
        if c == 6: c -= 1
        for y in (range(N - 1, -1, -1) if up else range(N)):
            for x in (c, c - 1):
                if M[y][x] is None: M[y][x] = int(allbits[k]) ^ ((x + y) % 2 == 0); k += 1
        up = not up; c -= 2
    return M


def qr_text(text):
    M = qr(text); n = len(M) + 8; on = lambda y, x: 4 <= y < n - 4 and 4 <= x < n - 4 and M[y - 4][x - 4]
    return '\n'.join('\x1b[30;107m' + ''.join(' ▄▀█'[2 * on(y, x) + on(y + 1, x)] for x in range(n)) + '\x1b[0m' for y in range(0, n, 2))
