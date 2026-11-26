# Diablo 2 Seed Finder & Map Renderer

Diablo 2 only uses a 31-bit seed for map generation, so the seed can be brute-forced and reversed.
Once you know the seed, you know every map in the game.

This is a fork of [emmericp/diablo2-maps](https://github.com/emmericp/diablo2-maps). The original finds the seed
from Tower level 4 on Normal (see [the original tools](#original-tools-113c) below). This fork adds a **seed finder
for D2R online games in Hell** that works from ordinary automap screenshots, plus a phone page with the maps and routes you need.

## D2R seed finder from screenshots (macOS)

Take a screenshot (Cmd+Shift+3) at a few waypoints while the automap is open. The watcher reads the walls around the
waypoint room, finds the seed in a few seconds and tells you:

- **Summoner**: which arm of the Arcane Sanctuary he is on (top, right, bottom or left).
- **Nihlathak**: which arm of the Halls of Vaught he is on (same words).
- **Duriel**: which tomb in the Canyon of the Magi is his, counted from the left.
- A map page for the seed, and a page for your phone with:
  - **Bosses**: the way to the exit in Durance 2, Worldstone 2 and 3, Catacombs 2 and 3, and Halls of Pain to the Halls of Vaught.
  - **Heralds**: clearing routes for the Act 1 and Act 2 terror zones where Heralds spawn most often.
    The active terror zone is read from the screenshot and shown first.
  - Large chests, shrines that can be any boost, the Cairn Stones and the Tree of Inifuss marked on the maps.

### Requirements

- A Mac with Xcode command-line tools (Swift, C compiler) and Python 3.
- D2R installed locally. The room shapes are read from your own game files; by default from the CrossOver bottle
  (`build_templates.py` takes another folder as an argument).
- About 9 GB of disk and, once, about 18 GB of memory to build the seed table.

### Quick start

```bash
cd tools/seedfinder && make && make table      # once: build data/seeds.idx (8.6 GB)
cd ../watcher && make                          # once: compile, read room shapes from your D2R files
python3 watch.py --voice                       # then play
```

In each new game, take a screenshot at three or four of these waypoints, with the waypoint room and its
neighbours visible on the full-screen automap at the default zoom:

1. Jail 1 and Catacombs 2 (Act 1)
2. Durance 2 (Act 3)
3. Sewers 2 (Act 2); you usually don't need it, so leave it for last.

A screenshot in the Rogue Encampment with the whole fence visible adds the town exit. Type `n` + Enter at the start of each new game.
Scan the QR code printed at the start to open the phone page (same Wi-Fi).

The details are in [tools/watcher/README.md](tools/watcher/README.md) and [tools/seedfinder/README.md](tools/seedfinder/README.md).

### What it does and does not do

- Purely visual: it reads screenshots that macOS saves. It does not read game memory, inject anything or send anything to the game.
- Text recognition (macOS Vision) and the search run locally. The only network use is the
  [map site](https://maps.diablo.deadlybossmods.com), which gets the seed, level and difficulty.
- The phone page is read-only, plain http on your local network.
- The map seed decides layouts, the Summoner, Nihlathak, Duriel's tomb, chest and shrine positions.
  It does **not** decide monsters, shrine types or drops; those come from a separate game seed.

### Layout

| Folder | What it is |
|---|---|
| `tools/seedfinder` | Level generator in C (follows the MIT-licensed D2MOO reconstruction), the 8.6 GB seed table and the solver |
| `tools/watcher` | Screenshot reader (`shotread.swift`), matcher, watcher loop, phone page, map views and clearing routes |
| `tools/automap` | Early tool that isolates the automap from a screenshot |
| `renderer`, `mapserver`, `seedgen` | The original map renderer, server and 1.13c seed generator |

### Accuracy

`tools/seedfinder/test/golden.txt` checks the generator against layouts from the real game (`make test`).
Seeds found in live D2R 3.4 Hell games matched the game in every case checked.

---

## Original tools (1.13c)

See it in action: [map renderer](https://maps.diablo.deadlybossmods.com) and [seed finder](https://seeds.diablo.deadlybossmods.com).

**Requirements**: Diablo 2 version 1.13c, cmake, and node.

From the original author: the code is 99% AI-generated, some parts are not great, and there is little documentation.

### Using the Tower seed finder

Due to compute requirements the seed finder currently requires a full reconstruction of tower level 4 on Normal.
With some compute it could be simplified into a 20-questions-style thing asking for more obviously visible things like exit directions, sprites used for various objects, etc.

Why tower specifically? The graves!
Take a look at this screenshot: [img/graves.png](img/graves.png).
See the 4 closed and 2 open graves?
This particular dead end room will always have exactly 6 of these in the exact same positions. But whether they are open or closed is random and yields about a bit of information about the RNG seed.

To use it you'll need to understand how random maps are generated: they are built from a few pre-defined "rooms" that are all the same size. You'll need to learn to spot and identify these in the game (which is rather easy with a bit of practice).

The flow is roughly:

1. Which directions does it connect in? There are corridors, corners, intersections and dead ends. The *connection points are never doors, always wide open areas*.
2. Which variant of a room is it? Most rooms have 3 variants; two are mostly empty/have no special elements and one has a few special elements. For example, the bottom corner piece can have a burning dead rogue inside for the special variant, and the two empty variants differ by which side the door is on.
3. Identify the positions the graves are in; the tool shows this on a map. These always refer to non-interactable graves on the floor that can be walked over when closed or are non-walkable when open. Graves that can be clicked on or are caskets that are above the ground are not relevant for the tool and must be ignored.
4. Once you've placed enough rooms in the given order to narrow it down to fewer than 200 (configurable) possible seeds, the web app will offer the option to brute-force the remaining seeds. Takes a few seconds of compute on the original author's server, which might be overloaded.

Internally it's just a large trie storing the level in BFS order followed by some ad-hoc brute-forcing.
