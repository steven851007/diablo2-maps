// Diablo II maze layout generator for the waypoint levels used as clues.
// Logic follows the MIT-licensed D2MOO reconstruction of D2Common (DrlgMaze, DrlgOutPlace).
// Directions: W = top left, N = top right, E = bottom right, S = bottom left on the automap.
#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "files.h"

typedef struct { uint32_t lo, hi; } Rng;
static inline uint32_t roll(Rng *s) { uint64_t v = s->hi + 0x6AC690C5ull * s->lo; s->lo = (uint32_t)v; s->hi = (uint32_t)(v >> 32); return s->lo; }
static inline Rng rng(uint32_t x) { Rng s = { x, 666 }; return s; }
static inline int limited(Rng *s, int n) { uint32_t r = roll(s); return (n & (n - 1)) ? (int)(r % (uint32_t)n) : (int)(r & (n - 1)); }
static inline uint32_t startSeed(uint32_t seed) { Rng g = rng(seed); return roll(&g); }

enum { MW = 1, ME = 2, MS = 4, MN = 8 };                      // exit bits
enum { K_NONE, K_PREV, K_NEXT, K_WAYPOINT, K_OTHER };         // special rooms
static const int DX[4] = { -1, 0, 1, 0 }, DY[4] = { 0, -1, 0, 1 };   // W N E S
static const uint8_t BIT[4] = { MW, MN, ME, MS };
#define MAXR 72
typedef struct { int8_t x, y; uint8_t mask, kind; Rng s; } Room;
typedef struct { int16_t preset; int8_t file; } Look;

static inline int roomAt(const Room *r, int n, int x, int y) { for (int i = 0; i < n; i++) if (r[i].x == x && r[i].y == y) return i; return -1; }
static inline Rng allocRoom(Rng *L) { Rng s = rng(roll(L)); roll(&s); return s; }

// Which room is where, for the layout being built (a layout never spans 128 rooms). The stamp saves clearing it.
static _Thread_local uint32_t gridStamp, grid[128][128];
static inline void gridReset(void) { gridStamp += 256; if (!gridStamp) { memset(grid, 0, sizeof grid); gridStamp = 256; } }
static inline int gridAt(int x, int y) { uint32_t v = grid[y & 127][x & 127]; return (v & ~255u) == gridStamp ? (int)(v & 255) : -1; }
static inline void gridPut(int x, int y, int i) { grid[y & 127][x & 127] = gridStamp | (uint32_t)i; }

static int addRoom(Rng *L, Room *r, int *n, int k, int d, int merge) {
    Room nr = { (int8_t)(r[k].x + DX[d]), (int8_t)(r[k].y + DY[d]), 0, 0, allocRoom(L) };
    if (gridAt(nr.x, nr.y) >= 0) return -1;
    r[k].mask |= BIT[d]; nr.mask |= BIT[(d + 2) & 3];
    if (merge) for (int e = 0; e < 4; e++) {                  // every neighbour rolls on its own seed, so the order does not matter
        int i = gridAt(nr.x + DX[e], nr.y + DY[e]);
        if (i < 0 || i == k || r[i].kind) continue;
        if (roll(&r[i].s) % 1000 < 500) { r[i].mask |= BIT[(e + 2) & 3]; nr.mask |= BIT[e]; }
    }
    gridPut(nr.x, nr.y, *n); r[*n] = nr; return (*n)++;
}
static void addSpecial(Rng *L, Room *r, int *n, int *dir, int kind) {   // order N,E,S,W, advancing each call
    static const uint8_t M[4] = { MN, ME, MS, MW }; static const int D[4] = { 3, 0, 1, 2 };
    int q = *dir; *dir = (q + 1) & 3;
    for (int i = *n - 1; i >= 0; i--) if (!r[i].kind && r[i].mask == M[q]) { r[i].kind = kind; return; }
    for (int i = *n - 1; i >= 0; i--) { if (r[i].kind) continue; int k = addRoom(L, r, n, i, D[q], 0); if (k >= 0) { r[k].kind = kind; return; } }
}
static void grow(Rng *L, Room *r, int *n, int target) {
    while (*n < target) { int k = *n - 1 - limited(L, *n); int d = roll(&r[k].s) & 3; if (!r[k].kind) addRoom(L, r, n, k, d, 1); }
}
static void ring4(Rng *L, Room *r, int *n) { int k = 0; static const int o[3] = { 1, 0, 3 }; for (int i = 0; i < 3; i++) k = addRoom(L, r, n, k, o[i], 1); r[k].mask |= ME; r[0].mask |= MW; }
static int star3(Rng *L, Room *r, int *n) { int d = roll(L) & 3; for (int i = 0; i < 3; i++) { addRoom(L, r, n, 0, d, 1); d = (d + 1) & 3; } r[0].kind = K_PREV; return d; }

enum { JAIL1 = 29, CATA2 = 35, SEWERS2 = 48, HALLSDEAD2 = 57, DURANCE2 = 101, CRYSTALLINE = 113, GLACIAL = 115, ANCIENTS = 118, WSK2 = 129 };

// Layout. Returns room count; rooms are in creation order (the game's list order is the reverse).
static int genLayout(uint32_t start, int lv, int diff, Room *r, Rng *Lout, int *cataNS) {
    Rng L = rng(start + lv); int n = 1, q; r[0] = (Room){ 0, 0, 0, 0, allocRoom(&L) }; gridReset(); gridPut(0, 0, 0);
    switch (lv) {
    case JAIL1: ring4(&L, r, &n); grow(&L, r, &n, 12); q = roll(&L) & 3; addSpecial(&L, r, &n, &q, K_PREV); addSpecial(&L, r, &n, &q, K_WAYPOINT); addSpecial(&L, r, &n, &q, K_NEXT); break;
    case CATA2: { int ew = roll(&L) & 1; addRoom(&L, r, &n, 0, ew ? 0 : 1, 1); addRoom(&L, r, &n, 0, ew ? 2 : 3, 1); r[0].kind = K_PREV; if (cataNS) *cataNS = !ew;
        grow(&L, r, &n, 14); q = roll(&L) & 3; addSpecial(&L, r, &n, &q, K_NEXT); addSpecial(&L, r, &n, &q, K_WAYPOINT); break; }
    case SEWERS2: ring4(&L, r, &n); grow(&L, r, &n, 12); roll(&L); q = roll(&L) & 3; addSpecial(&L, r, &n, &q, K_PREV); addSpecial(&L, r, &n, &q, K_WAYPOINT); addSpecial(&L, r, &n, &q, K_NEXT); break;
    case HALLSDEAD2: { static const int Q[4] = { 2, 3, 0, 1 }; int d = star3(&L, r, &n); grow(&L, r, &n, 6); q = Q[d]; addSpecial(&L, r, &n, &q, K_NEXT); addSpecial(&L, r, &n, &q, K_WAYPOINT); break; }
    case DURANCE2: ring4(&L, r, &n); grow(&L, r, &n, diff ? 48 : 12); q = roll(&L) & 3; addSpecial(&L, r, &n, &q, K_PREV); addSpecial(&L, r, &n, &q, K_WAYPOINT); addSpecial(&L, r, &n, &q, K_NEXT); break;
    case CRYSTALLINE: case GLACIAL: case ANCIENTS: ring4(&L, r, &n); grow(&L, r, &n, lv == ANCIENTS ? 15 : 10); q = roll(&L) & 3;
        addSpecial(&L, r, &n, &q, K_PREV); addSpecial(&L, r, &n, &q, K_NEXT); addSpecial(&L, r, &n, &q, K_OTHER); if (lv == GLACIAL) addSpecial(&L, r, &n, &q, K_OTHER); addSpecial(&L, r, &n, &q, K_WAYPOINT); break;
    case WSK2: star3(&L, r, &n); grow(&L, r, &n, 9); q = roll(&L) & 3; addSpecial(&L, r, &n, &q, K_NEXT); addSpecial(&L, r, &n, &q, K_WAYPOINT); break;
    default: return 0;
    }
    if (Lout) *Lout = L;
    return n;
}
// Preset id ranges: base+1..15 normal room (exits), base+16..30 themed, above that special rooms.
static inline int presetBase(int lv) { return lv == JAIL1 ? 205 : lv == CATA2 ? 257 : lv == SEWERS2 ? 301 : lv == DURANCE2 ? 753 : 0; }
static inline int hasLooks(int lv) { return presetBase(lv) != 0; }                    // preset ids validated
static inline int hasVariants(int lv) { return lv == CATA2 || lv == SEWERS2; }        // file index validated
static inline int fileCount(int lv, int p) { int b = presetBase(lv), k = p - b; const unsigned char *t = lv == JAIL1 ? FILES_JAIL : lv == CATA2 ? FILES_CATA : lv == SEWERS2 ? FILES_SEWER : FILES_DURANCE; return t[k]; }
static int specialPreset(int lv, const Room *q, int cataNS) {
    int d = q->mask == MW ? 0 : q->mask == ME ? 1 : q->mask == MS ? 2 : 3, k = q->kind;
    switch (lv) {
    case JAIL1: return (k == K_PREV ? 236 : k == K_NEXT ? 240 : 248) + d;
    case CATA2: return k == K_PREV ? (cataNS ? 289 : 288) : (k == K_NEXT ? 291 : 295) + d;
    case SEWERS2: return (k == K_PREV ? 332 : k == K_NEXT ? 337 : 345) + d;
    default: return (k == K_PREV ? 784 : k == K_NEXT ? 788 : 792) + d;
    }
}
// Layout plus preset id and variant of every room.
static int genLooks(uint32_t start, int lv, int diff, Room *r, Look *v) {
    Rng L; int ns = 0, n = genLayout(start, lv, diff, r, &L, &ns), base = presetBase(lv);
    for (int i = 0; i < n; i++) v[i] = (Look){ (int16_t)(r[i].kind ? specialPreset(lv, &r[i], ns) : base + r[i].mask), 0 };
    int off[15]; for (int i = 0; i < 15; i++) off[i] = i;
    int ix = roll(&L) % 15;
    for (int i = 0; i < 15; i++) { int b = roll(&L) % 15, a = roll(&L) % 15, t = off[a]; off[a] = off[b]; off[b] = t; }
    int left = n / 5 + 1; if (left <= 2) left = 2;
    uint8_t themed[MAXR] = { 0 };
    for (int tries = 2 * n; left && tries; tries--) {
        int p = off[ix] + base;
        for (int i = n - 1; i >= 0; i--) if (!r[i].kind && !themed[i] && v[i].preset == p) { v[i].preset = (int16_t)(p + 15); themed[i] = 1; left--; break; }
        ix = (ix + 1) % 15;
    }
    int next[16]; for (int i = 0; i < 16; i++) next[i] = -1;
    for (int i = n - 1; i >= 0; i--) {
        int f = fileCount(lv, v[i].preset), pick = f > 0 ? limited(&L, f) : 0, k = v[i].preset - base;
        if (k > 0 && k < 16) { if (next[k] < 0) next[k] = limited(&L, f); next[k] = (next[k] + 1) % f; pick = next[k]; }
        v[i].file = (int8_t)pick; roll(&L);
    }
    return n;
}

// Act 1: which side of the Rogue Encampment leads to the Blood Moor. Returns a BIT value, 0 if unplaced.
typedef struct { int x, y, w, h; } Box;
static inline int overlaps(Box a, Box b) { return !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y); }
static Box boxPlains(int e, Box t, int w, int h) { Box s = { 0, 0, w, h }; switch (e) { case 0: s.x = t.x - 16; s.y = t.y + t.h; break; case 1: s.x = t.x - w; s.y = t.y - 16; break; case 2: s.x = t.x + t.w - w + 16; s.y = t.y - h; break; case 3: s.x = t.x + t.w; s.y = t.y + t.h - h + 16; } return s; }
static Box boxMoor(int e, int a, Box n, int w, int h) { Box r = { 0, 0, w, h };
    if (!a) switch (e) { case 0: r.x = n.x + n.w - w + 16; r.y = n.y + n.h; break; case 1: r.x = n.x - w; r.y = n.y + n.h - h + 16; break; case 2: r.x = n.x - 16; r.y = n.y - h; break; case 3: r.x = n.x + n.w; r.y = n.y - 16; }
    else switch (e) { case 0: r.x = n.x - 16; r.y = n.y + n.h; break; case 1: r.x = n.x - w; r.y = n.y - 16; break; case 2: r.x = n.x + n.w - w + 16; r.y = n.y - h; break; case 3: r.x = n.x + n.w; r.y = n.y + n.h - h + 16; } return r; }
static Box boxTown(int e, int a, Box n, int w, int h) { Box r = { 0, 0, w, h };
    if (!a) switch (e) { case 0: r.x = n.x + n.w - w; r.y = n.y + n.h; break; case 1: r.x = n.x - w; r.y = n.y + n.h - h - 8; break; case 2: r.x = n.x; r.y = n.y - h; break; case 3: r.x = n.x + n.w; r.y = n.y + 8; }
    else switch (e) { case 0: r.x = n.x; r.y = n.y + n.h; break; case 1: r.x = n.x - w; r.y = n.y + 8; break; case 2: r.x = n.x + n.w - w; r.y = n.y - h; break; case 3: r.x = n.x + n.w; r.y = n.y + n.h - h - 8; } return r; }
static int townExit(uint32_t seed) {
    static const uint8_t ALLOW[64] = { 1,1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,1,0,1,0,0,1,0,0,0,0,0,1,1,0,1,0,0,0,0,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,1,1,0,1,0,0,0,0,0,1,1 };
    static const uint8_t SIDE[4] = { MN, ME, MS, MW };
    Rng e = rng(seed); roll(&e); Box b[4] = { { 1000, 1000, 80, 80 } }; int side[4] = { -1 }, sub[4] = { -1 };
    for (int o = 1; o < 4; o++) {
        int i = roll(&e) & 3, a = o > 1 ? (int)(roll(&e) & 1) : -1, i0 = i, a0 = a;
        for (;;) {
            Box h = o == 1 ? boxPlains(i, b[0], 80, 80) : o == 2 ? boxMoor(i, a, b[1], i & 1 ? 96 : 56, i & 1 ? 56 : 96) : boxTown(i, a, b[2], 56, 40);
            int ok = 1; for (int p = 0; p < o - 1; p++) if (overlaps(h, b[p])) ok = 0;
            if (ok && o == 3 && !ALLOW[i + a * 4 + side[2] * 8 + sub[2] * 32]) ok = 0;
            if (ok) { b[o] = h; side[o] = i; sub[o] = a; break; }
            if (o > 1) { int p = (i + a) & 3, w = a ^ 1; if (p == i0 && w == a0) return 0; i = p; a = w; } else { i = (i + 1) & 3; if (i == i0) return 0; }
        }
    }
    return SIDE[side[3]];
}

// Arcane Sanctuary: 1 start room, 1 roll, 60 rooms, then this roll picks the arm of the Summoner (checked: 10 of 10 real maps).
static int summonerArm(uint32_t seed) {
    static const uint8_t ARM[4] = { MS, MW, MN, ME };
    Rng g = rng(startSeed(seed) + 74); for (int i = 0; i < 62; i++) roll(&g);
    return ARM[roll(&g) & 3];
}
// Level ids of the tomb with the orifice (Duriel, three times the rooms) and the other big tomb (twice the rooms), 66-72.
static int tombLevels(uint32_t seed, int *big) {
    Rng g = rng(seed); roll(&g); uint32_t a, b;
    do { a = roll(&g) % 7; b = roll(&g) % 7; } while (a == b);
    if (big) *big = 66 + (int)b;
    return 66 + (int)a;
}
static int durielTomb(uint32_t seed) { return tombLevels(seed, 0); }
// The Canyon of the Magi is always the same: entrances on screen from left to right are tombs 4 3 2 1 5 6 7.
static int tombFromLeft(int lv) { static const int8_t P[7] = { 4, 3, 2, 1, 5, 6, 7 }; return P[lv - 66]; }
// Halls of Vaught: the first roll of the level picks Nihlathak's arm. He stands at the "Nihlathak Start" marker
// (object 462); checked on 19 real maps and confirmed in a live game.
static int nihlathakArm(uint32_t seed) { static const uint8_t ARM[4] = { ME, MN, MS, MW }; Rng g = rng(startSeed(seed) + 124); return ARM[roll(&g) & 3]; }
