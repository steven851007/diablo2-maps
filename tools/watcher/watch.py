#!/usr/bin/env python3
"""Watch a folder for new D2R screenshots and find the map seed.

    python3 watch.py [folder] [--voice] [--no-sound] [--no-open] [--no-phone] [--replay]

folder    where screenshots are saved (default: the macOS screenshot location)
--voice   speak short results          --no-sound  stay silent
--no-phone no page for the phone
--no-open do not open the map page     --replay    analyse the images already in the folder and stop

While running, type and press Enter:  n = new game   s = status   town E = town exit   seed 123 = show a known seed   q = quit
Only new images are opened and read on this Mac, nothing is sent to the game. The map site gets the seed only."""
import argparse, json, os, queue, select, subprocess, sys, threading, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import match as M
import mapview, phone

MAP = 'https://maps.diablo.deadlybossmods.com/?seed={seed}&level={level}&difficulty={diff}'
DIFF = {'normal': 0, 'nightmare': 1, 'hell': 2}
NAMES = {'jail1': 'Jail 1', 'catacombs2': 'Catacombs 2', 'sewers2': 'Sewers 2', 'durance2': 'Durance 2', 'halls': 'Halls of the Dead 2'}
SOUND = {'ok': 'Tink', 'bad': 'Basso', 'more': 'Pop', 'found': 'Hero', 'new': 'Submarine'}
IMAGES = ('.png', '.jpg', '.jpeg', '.heic', '.tiff')


class Session:
    def __init__(self, opt): self.opt = opt; self.T = M.Templates(); self.phone = None; self.areas = {}; self.loading = set(); self.dirty = False; self.waiting = lambda: False; self.terror = []; self.jobs = None; self.reset(first=True)

    def reset(self, first=False):
        self.dirty = False; self.maps, self.diff, self.town, self.found, self.town_typed = {}, 'hell', None, None, False
        d = os.path.join(HERE, 'sessions'); os.makedirs(d, exist_ok=True)
        self.log = os.path.join(d, time.strftime('%Y%m%d-%H%M%S') + '.jsonl')
        if self.phone: self.phone.clear()
        if not first: self.say('\n--- new game ---', 'new', 'New game')

    def say(self, text, sound=None, voice=None):
        print(text, flush=True)
        if sound and not self.opt.no_sound and not self.opt.replay:
            subprocess.Popen(['afplay', f'/System/Library/Sounds/{SOUND[sound]}.aiff'], stderr=subprocess.DEVNULL)
        if voice and self.opt.voice and not self.opt.replay: subprocess.Popen(['say', voice], stderr=subprocess.DEVNULL)

    def record(self, **k):
        if self.opt.replay: return
        with open(self.log, 'a') as f: f.write(json.dumps({'time': time.strftime('%H:%M:%S'), **k}) + '\n')

    def image(self, path):
        t0 = time.time(); name = os.path.basename(path)
        r = subprocess.run([os.path.join(HERE, 'shotread'), path, '--text-only'], capture_output=True, text=True)
        try: text = json.loads(r.stdout).get('text', [])
        except ValueError: return self.say(f'{name}: cannot read this image')
        stop, diff, title = M.level_from_text(text); self.see_terror(text)
        if not title: return self.say(f'{name}: no known level name, ignored')
        if title == 'rogue encampment': return self.read_town(path, name, diff)
        if not stop: return self.say(f'{name}: {title} is not one of the clue levels, ignored')
        if diff and diff != self.diff:
            if self.maps: self.reset()
            self.diff = diff
        shot = json.loads(subprocess.run([os.path.join(HERE, 'shotread'), path], capture_output=True, text=True).stdout)
        res = self.maps.setdefault(stop, M.LevelMap(stop)).add(shot, self.T)
        if res.get('conflict') and res['own'] > 18:         # clearly another waypoint room: a different game
            self.say(f"{name}: the {NAMES[stop]} waypoint room changed"); self.reset(); self.diff = diff or 'hell'
            res = self.maps.setdefault(stop, M.LevelMap(stop)).add(shot, self.T)
        self.record(file=name, stop=stop, result=res)
        if not res['ok']:
            why = 'it does not fit the earlier screenshots' if res.get('conflict') else res['reason']
            return self.say(f'{name}: {NAMES[stop]} - {why}. Keep the waypoint room visible on the automap.', 'bad', 'Not recognised')
        self.say(f"{name}: {NAMES[stop]}, waypoint room opens {M.SCREEN[res['waypoint']]}   ({time.time()-t0:.1f}s)", 'ok')
        self.dirty = True

    def read_town(self, path, name, diff):
        if diff and diff != self.diff:
            if self.maps: self.reset()
            self.diff = diff
        shot = json.loads(subprocess.run([os.path.join(HERE, 'shotread'), path], capture_output=True, text=True).stdout)
        side, why = M.town_exit(shot); self.record(file=name, town=side, why=why)
        if not side: return self.say(f'{name}: Rogue Encampment - {why}, open the full automap in the middle of the camp', 'bad', 'Town not recognised')
        if self.town and side != self.town and not self.town_typed:
            self.say(f'{name}: the town exit changed'); self.reset(); self.diff = diff or 'hell'
        known = self.town == side; self.town, self.town_typed = side, False
        self.say(f'{name}: Rogue Encampment, exit {M.SCREEN[side]}' + ('' if not self.maps or not known else '   (new game? type n)'), 'ok', 'Town exit ' + M.SCREEN[side])
        if sum(1 for m in self.maps.values() if m.wp) >= 2: self.dirty = True

    def flush(self):
        """Search once after all waiting screenshots are read."""
        if self.dirty and not self.waiting(): self.dirty = False; self.solve()

    def solve(self, again=False):
        text, info = M.clue_lines(self.maps, self.T, self.diff, self.town)
        for lv, rooms in info.items():
            sure = [q for q in rooms if q['margin'] >= 3 and q['fit'] >= 0.45]
            print(f"   {NAMES[lv]:20s} {len(sure)} of {len(rooms)} rooms read clearly: " + ', '.join(f"({q['cell'][0]},{q['cell'][1]}) {q['exits']}" for q in sure))
        if len(info) < (2 if again else 3):                 # two stops never settle it and are the slowest search
            if self.phone: self.phone.status(f"{len(info)} stop{'s' * (len(info) > 1)} so far")
            return self.say(f"   {len(info)} stop{'s' * (len(info) > 1)} so far, go on to the next waypoint", 'more', 'Next waypoint')
        r = M.solve(text, stop=self.waiting, slow=lambda: print('   searching ...', flush=True))
        if r is None: self.dirty = True; return print('   search stopped, a new screenshot is there', flush=True)
        self.record(clues=text, result=r)
        if 'error' in r: return self.say('   solver: ' + r['error'], 'bad')
        if not r['ranked']: return self.say('   no seed fits. New game? Type n. Otherwise one room was misread.', 'bad', 'No seed fits')
        best, score = r['ranked'][0]; c = r['confidence']; lead = score - r['ranked'][1][1] if len(r['ranked']) > 1 else 99
        if c >= 0.97 and len(info) >= 3 or c >= 0.995 and lead > 8:
            first = self.found != best; self.found = best
            url = MAP.format(seed=best, level=1, diff=DIFF[self.diff])
            f = M.facts(best); text = voice = ''
            if f:
                text = f"\n   Summoner: {M.SUMMONER[f['summoner']]}   Nihlathak: {M.SUMMONER[f['nihlathak']]}   Duriel: {phone.tomb_text(f['tomb'])}"
                voice = f". Summoner {M.SUMMONER[f['summoner']]}. Nihlathak {M.SUMMONER[f['nihlathak']]}. Duriel, {phone.tomb_text(f['tomb'])}"
            self.say(f'   SEED {best}   confidence {100*c:.1f}%   ({r["ms"]:.0f} ms){text}\n   {url}', 'found' if first else 'ok', 'Seed found' + voice if first or again else None)
            self.show_maps(best, f)
            if first and not self.opt.no_open and not self.opt.replay: subprocess.run(['open', '-g', url])
        else:
            self.found = None
            if self.phone: self.phone.status(f'{100*c:.0f}% sure after {len(info)} stops')
            self.say(f'   not certain yet: best guess {best} at {100*c:.0f}% from {len(info)} stops. One more screenshot or stop.', 'more', f'{int(100*c)} percent')

    @staticmethod
    def side(facts): return {k: (M.SUMMONER[facts[k]], M.SCREEN[facts[k]]) for k in ('summoner', 'nihlathak')} if facts else {}

    def show_maps(self, seed, facts):
        """Put facts on the phone page at once, the maps as soon as they are there."""
        if not self.phone: return
        key = (seed, DIFF[self.diff]); side = self.side(facts)
        self.facts = facts; self.phone.found(seed, facts, side, self.areas.get(key), 'Loading the maps')
        if key not in self.areas: self.later('boss')
        for k in self.terror: self.later(k)

    def see_terror(self, lines):
        """The corner text names the active terror zone (not while you stand in it)."""
        if len(lines) < 4 or any('TERRORI' in l.upper() for l in lines): return
        z = mapview.terror_zones(lines)
        if z == self.terror: return
        self.terror = z
        if self.phone: self.phone.set_active(z)
        for k in z:
            if self.found: self.later(k)

    def later(self, what):
        """Load maps one after another in the background: 'boss' or a zone key."""
        if not self.phone or not self.found: return
        if self.jobs is None: self.jobs = queue.Queue(); threading.Thread(target=self.work, daemon=True).start()
        key = (self.found, DIFF[self.diff], what)
        if key in self.loading: return
        if what != 'boss':
            if key in self.areas: return self.phone.set_zone(key[0], what, 'ready', self.areas[key])
            self.phone.set_zone(key[0], what, 'loading')
        self.loading.add(key); self.jobs.put(key)

    def work(self):
        while True:
            key = self.jobs.get(); seed, diff, what = key
            try:
                if self.found != seed or DIFF[self.diff] != diff: continue
                if what == 'boss': areas = mapview.build(mapview.fetch(seed, diff))
                else:
                    areas = mapview.build_zone(mapview.fetch(seed, diff, levels=mapview.zone_levels(what, self.facts)), what, self.facts)
                if not areas: raise ValueError('nothing drawn')
                self.areas[(seed, diff) if what == 'boss' else key] = areas
                if what != 'boss': self.phone.set_zone(seed, what, 'ready', areas)
                elif self.found == seed: self.phone.found(seed, self.facts, self.side(self.facts), areas)
            except Exception as e:                            # the watcher must keep running without maps
                print(f'   no maps for the phone ({what}): {type(e).__name__}', flush=True)
                if what != 'boss': self.phone.set_zone(seed, what, 'failed')
                elif self.found == seed: self.phone.found(seed, self.facts, self.side(self.facts), None, 'The map site did not answer. Type s in the watcher to try again.')
            finally: self.loading.discard(key)

    def command(self, line):
        w = line.split()
        if not w: return True
        if w[0] == 'q': return False
        if w[0] == 'n': self.reset()
        elif w[0] == 's': self.solve(again=True) if any(m.wp for m in self.maps.values()) else print('   nothing recognised yet')
        elif w[0] == 'seed' and len(w) > 1 and w[1].isdigit() and int(w[1]) < 1 << 31:      # look at a known seed without screenshots
            self.reset(); self.found = int(w[1]); f = M.facts(self.found)
            print(f"   seed {self.found}" + (f"   Summoner: {M.SUMMONER[f['summoner']]}   Nihlathak: {M.SUMMONER[f['nihlathak']]}   Duriel: {phone.tomb_text(f['tomb'])}" if f else '')); self.show_maps(self.found, f)
        elif w[0] == 'town' and len(w) > 1 and set(w[1].upper()) <= set('WNES'): self.town, self.town_typed = w[1].upper(), True; print('   town exit', ' or '.join(M.SCREEN[x] for x in self.town))
        else: print('   n = new game, s = status, town E, seed 123 = show a known seed, q = quit')
        return True


def default_folder():
    r = subprocess.run(['defaults', 'read', 'com.apple.screencapture', 'location'], capture_output=True, text=True).stdout.strip()
    return os.path.expanduser(r) if r and os.path.isdir(os.path.expanduser(r)) else os.path.expanduser('~/Desktop')


def stable(path):
    try: a = os.path.getsize(path); time.sleep(0.25); return a > 0 and a == os.path.getsize(path)
    except OSError: return False


def main():
    p = argparse.ArgumentParser(usage=__doc__); p.add_argument('folder', nargs='?'); [p.add_argument(x, action='store_true') for x in ('--voice', '--no-sound', '--no-open', '--no-phone', '--replay')]
    o = p.parse_args(); folder = os.path.abspath(os.path.expanduser(o.folder)) if o.folder else default_folder()
    for need, how in ((os.path.join(HERE, 'shotread'), 'run make in tools/watcher'), (os.path.join(HERE, 'templates.json'), 'run make in tools/watcher'), (os.path.join(HERE, 'clearroute'), 'run make in tools/watcher'), (os.path.join(HERE, '..', 'seedfinder', 'data', 'seeds.idx'), 'run make table in tools/seedfinder')):
        if not os.path.exists(need): sys.exit(f'missing {os.path.relpath(need)}: {how}')
    try: names = {n for n in os.listdir(folder) if n.lower().endswith(IMAGES) and not n.startswith('.')}
    except OSError as e: sys.exit(f'cannot read {folder}: {e}')
    s = Session(o)
    if o.replay:
        for n in sorted(names, key=lambda n: os.path.getmtime(os.path.join(folder, n))): s.image(os.path.join(folder, n)); s.flush()
        return
    if not o.no_phone:
        ph = phone.Phone([(z[0], z[1]) for z in mapview.ZONES]); ph.on_zone = s.later; url = ph.start()
        if url: s.phone = ph; print(phone.qr_text(url) + f'\nPhone on the same Wi-Fi: scan the code or open {url}')
        else: print('No local network address found, so no page for the phone.')
    print(f'Watching {folder}\nOpen the automap and press Cmd+Shift+3. Type n for a new game, q to quit.', flush=True); tty, buf = True, ''
    fresh = lambda: {n for n in os.listdir(folder) if n.lower().endswith(IMAGES) and not n.startswith('.')} - names
    s.waiting = lambda: any(os.path.exists(q) and os.path.getsize(q) for q in (os.path.join(folder, n) for n in fresh()))
    try:
        while True:
            now = {n for n in os.listdir(folder) if n.lower().endswith(IMAGES) and not n.startswith('.')}
            for n in sorted(now - names, key=lambda n: os.path.getmtime(os.path.join(folder, n))):
                if stable(os.path.join(folder, n)): print(f'{n}: reading ...', flush=True); s.image(os.path.join(folder, n)); names.add(n)
            names &= now; s.flush()
            if tty and select.select([0], [], [], 0.3)[0]:
                got = os.read(0, 4096).decode(errors='ignore')
                if not got: tty = False
                buf += got; *lines, buf = buf.split('\n')
                if not all(s.command(l.strip()) for l in lines): break
            elif not tty: time.sleep(0.3)
    except KeyboardInterrupt: pass


if __name__ == '__main__': main()
