# watcher

Watches the screenshot folder and finds the seed of the current D2R game.

    cd tools/watcher && make        # once: compile, read room shapes from your D2R files
    python3 watch.py                # then play; add --voice to hear the results

0. Optional: one screenshot in the Rogue Encampment (stand near the middle, whole fence visible) gives the town exit.
1. Use a waypoint: Jail 1, Catacombs 2, Sewers 2 (Act 2), Durance 2; Halls of the Dead 2 as an extra.
2. Walk into the next room and look into its neighbours, automap full screen, default zoom.
3. Press Cmd+Shift+3 while the waypoint room is still visible on the automap.
4. From the third stop on it searches (a new screenshot interrupts a search) and prints the seed, the Summoner arm and Duriel's tomb (1-7 from the left in the Canyon of the Magi)
   and opens the map page in the background. With --voice it reads them out; `s` repeats them.

Type `n` + Enter for each new game (a town screenshot with a different exit does it by itself).
`s` status, `seed 123` shows the maps of a known seed without a game, `town E` sets the town exit by hand, `q` quits.
`python3 watch.py folder --replay` analyses existing screenshots.

Phone: scan the QR code printed at the start (same Wi-Fi). Two tabs, updated by themselves:
- Bosses: way to the exit in Durance 2, Worldstone 2 and 3, Catacombs 2 and 3, and Halls of Pain to the Halls of Vaught (`AREAS` in `mapview.py`).
- Purple dots: shrines that can be any boost (`ANY_SHRINES`); health and mana spots are left out. White marks: Cairn Stones, Tree of Inifuss.
- Gold boxes on every map: large chests (`SUPER_CHESTS`); the game files have no super chest flag.
- Heralds: clearing routes for the terror zones in `ZONES`, loaded when tapped. The active terror zone is read from the
  corner text of any screenshot taken outside it, marked with a star and loaded first. `REACH` is how far you clear.
Read-only and plain http on the local address, so anybody in the same network can look at it. `--no-phone` turns it off.

Turn off the floating preview (Cmd+Shift+5, Options, Show Floating Thumbnail), otherwise macOS saves late.
Sounds: Tink = recognised, Pop = need more, Basso = not recognised, Hero = seed found.

Only new images in the folder are opened. Text recognition (macOS Vision) and everything else run
locally; the network is only used for opening the map page (`--no-open`) and, for asking the same site for
the phone maps (once per seed, and once per zone you open) (`--no-phone`). Both send the seed, level and difficulty, nothing else. Nothing is sent to the game.
`sessions/` keeps what was recognised (file names and clues, no images) for debugging.

Files: `shotread.swift` image to wall segments, `match.py` segments to room evidence, `watch.py` the loop,
`mapview.py` maps and routes, `clearroute.c` clearing routes, `phone.py` page and QR code,
`build_templates.py` + `casc.py` read room shapes (and the white step lines of the Durance) from the local game, `test_synthetic.py` checks the matcher.
