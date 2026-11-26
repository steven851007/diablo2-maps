# seedfinder

Finds a Diablo II map seed (31 bit) from what is visible around a few waypoints.

    make                # compile
    make table          # build data/seeds.idx (8.6 GB, once; needs about 18 GB of memory)
    ./seedfinder verify data/seeds.idx
    ./seedfinder solve data/seeds.idx clues.txt
    make test

The table groups all 2^31 seeds by what Catacombs 2, Jail 1 and Sewers 2 look like next to the
waypoint. The solver reads only matching groups and checks every other clue by
generating the levels. If neither of those stops is given it scans all seeds instead.

## Clues

Plain text, from a file or stdin. Directions are the automap's:
`W` top left, `N` top right, `E` bottom right, `S` bottom left.
Rooms are counted from the waypoint room (0,0): x grows towards E, y grows towards S.

    difficulty hell                 # normal | nightmare | hell (only matters for durance2)
    town E                          # town exit to the Blood Moor; several letters = any of them
    town E soft                     # with weigh lines: counts against other exits instead of excluding them
    stop catacombs2
    room 0,0 exits=E                # complete list of exits
    room 1,0 open=ES closed=N       # only what you are sure about
    room 1,0 exits=WES preset=264 variant=2
    room 2,0 theme=0                # 1 = themed room
    room 0,1 absent                 # there is no room here

    room 1,0 exits=WES|WE           # one of several
    weigh 1,1 NES=0 NE=-2.5 default=-6 absent=-8      # soft evidence per exits
    weigh 1,0 264.2=0 264.1=-3 279=-4 default=-6      # or per preset[.variant]

With any `weigh` line the solver ranks seeds that satisfy the `room` lines by total score
(natural log units) and prints `ranked` plus the confidence of the best one.

Stops: catacombs2, sewers2, jail1, durance2, halls, crystalline, glacial, ancients, wsk2.
`preset` (LvlPrest.txt id) and `theme` work at catacombs2, sewers2, jail1 and durance2.
`variant` (DS1 file number, from 0) works at catacombs2 and sewers2 only.

Options: `--limit N` seeds to list, `--tolerate 1` accept seeds with one wrong clue line.

Output is one line of JSON:

    {"matches":1,"exact":1,"seeds":[895537341],"wrongClues":[0],"mode":"table","tested":...,"ms":...}

`facts <seed>` prints JSON with the town exit, the Summoner's and Nihlathak's arms, Duriel's tomb and the other big tomb (counted from the left in the Canyon of the Magi).
`describe <seed>` prints the clues a player would see, in the same format.

## Accuracy

`test/golden.txt` holds layouts from the real 1.13c game. The generator follows the
MIT-licensed D2MOO reconstruction of D2Common. Confirmed once against live D2R 3.4 (Hell).
