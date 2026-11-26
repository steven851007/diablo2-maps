// seedfinder: lookup table and solver for Diablo II map seeds (31 bit).
//   seedfinder build    <table>                 build the table (about 8.6 GB)
//   seedfinder verify   <table>                 check it is complete and matches this generator
//   seedfinder solve    <table> [file] [--limit N] [--tolerate 0|1]   clues from file or stdin, JSON out
//   seedfinder describe <seed> [normal|nightmare|hell] [stop ...]     clues a player would see
//   seedfinder facts    <seed>                                        Summoner and Nihlathak arms, Duriel's tomb counted from the left, town exit
//   seedfinder dump     <seed> <levelId> [difficulty 0-2]             rooms: x,y,exits,kind,preset,file
#include "gen.h"
#include <fcntl.h>
#include <math.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define NSEEDS 2147483648ull
#define NBUCKETS (1 << 21)
#define DATA_OFFSET (1u << 25)
typedef struct { char magic[8]; uint32_t version, genHash; uint64_t count; uint64_t off[NBUCKETS + 1]; } Header;
_Static_assert(sizeof(Header) <= DATA_OFFSET, "header too large");

static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec / 1e9; }
static int nThreads(void) { const char *e = getenv("SEEDFINDER_THREADS"); if (e && atoi(e) > 0 && atoi(e) <= 64) return atoi(e); long n = sysconf(_SC_NPROCESSORS_ONLN); return n < 1 ? 1 : n > 64 ? 64 : (int)n; }

// ---- table key: what you see at the Catacombs 2 (9 bits), Jail 1 (5 bits) and Sewers 2 (7 bits) waypoints ----
// Sewers last, so a search without it still reads one block per Catacombs and Jail combination
// direction the waypoint room opens, exits of the next room, its type (normal/themed/special) and variant
typedef struct { int ok, dir, mask, type, file; } Near;
static int typeOf(int lv, int preset) { int k = preset - presetBase(lv); return k >= 1 && k <= 15 ? 0 : k >= 16 && k <= 30 ? 1 : 2; }
static Near nearWaypoint(uint32_t start, int lv) {
    Room r[MAXR]; Look v[MAXR]; int n = genLooks(start, lv, 2, r, v), w = -1; Near q = { 0 };
    for (int i = 0; i < n; i++) if (r[i].kind == K_WAYPOINT) { w = i; break; }
    if (w < 0) return q;
    while (!(r[w].mask & BIT[q.dir])) q.dir++;
    int p = roomAt(r, n, r[w].x + DX[q.dir], r[w].y + DY[q.dir]); if (p < 0) return q;
    q.ok = 1; q.mask = r[p].mask; q.type = typeOf(lv, v[p].preset); q.file = v[p].file; return q;
}
static int others(int dir, int mask) { int b = (dir + 2) & 3, e = 0; for (int o = 1; o <= 3; o++) if (mask & BIT[(b + o) & 3]) e |= 1 << (o - 1); return e; }
static int maskOf(int dir, int e) { int b = (dir + 2) & 3, m = BIT[b]; for (int o = 1; o <= 3; o++) if (e >> (o - 1) & 1) m |= BIT[(b + o) & 3]; return m; }
static int cataId(Near q) { return q.ok ? q.dir << 7 | others(q.dir, q.mask) << 4 | q.type << 2 | (q.file & 3) : 0; }
static int sewId(Near q) { return q.ok ? q.dir << 5 | others(q.dir, q.mask) << 2 | (q.type ? 1 : 0) << 1 | (q.file & 1) : 0; }
static int jailId(uint32_t start) {          // direction and next room's exits only; room type and variant are not used
    Room r[MAXR]; int n = genLayout(start, JAIL1, 2, r, 0, 0), w = -1, d = 0;
    for (int i = 0; i < n; i++) if (r[i].kind == K_WAYPOINT) { w = i; break; }
    if (w < 0) return 0;
    while (!(r[w].mask & BIT[d])) d++;
    int p = roomAt(r, n, r[w].x + DX[d], r[w].y + DY[d]); return p < 0 ? 0 : d << 3 | others(d, r[p].mask);
}
static uint32_t keyOf(uint32_t seed) { uint32_t s = startSeed(seed); return (uint32_t)cataId(nearWaypoint(s, CATA2)) << 12 | (uint32_t)jailId(s) << 7 | (uint32_t)sewId(nearWaypoint(s, SEWERS2)); }
static uint32_t generatorHash(void) { uint32_t h = 2166136261u; for (uint32_t i = 0; i < 4000; i++) { uint32_t s = i * 2654435761u >> 1; h = (h ^ keyOf(s)) * 16777619u; h = (h ^ (uint32_t)townExit(s)) * 16777619u; } return h; }

// ---- build ----
static uint32_t *gKeys; static uint32_t *gOut; static uint64_t (*gCnt)[NBUCKETS]; static int gT; static atomic_ullong gDone;
typedef struct { int id; } Arg;
static uint64_t lo(int i) { return NSEEDS * i / gT; }
static void *keyWorker(void *p) { int id = ((Arg *)p)->id; for (uint64_t s = lo(id); s < lo(id + 1); s++) { gKeys[s] = keyOf((uint32_t)s); gCnt[id][gKeys[s]]++; if ((s & 0xFFFFF) == 0xFFFFF) atomic_fetch_add(&gDone, 1 << 20); } return 0; }
static void *scatterWorker(void *p) { int id = ((Arg *)p)->id; for (uint64_t s = lo(id); s < lo(id + 1); s++) gOut[gCnt[id][gKeys[s]]++] = (uint32_t)s; return 0; }
static void runAll(void *(*f)(void *), int progress) {
    pthread_t t[64]; Arg a[64]; double t0 = now();
    for (int i = 0; i < gT; i++) { a[i].id = i; pthread_create(&t[i], 0, f, &a[i]); }
    if (progress) while (atomic_load(&gDone) < NSEEDS - (uint64_t)gT * (1 << 20)) { sleep(15); fprintf(stderr, "  %.0f%%  %.0fs\n", 100.0 * atomic_load(&gDone) / NSEEDS, now() - t0); }
    for (int i = 0; i < gT; i++) pthread_join(t[i], 0);
}
static int build(const char *path) {
    char tmp[4096]; snprintf(tmp, sizeof tmp, "%s.tmp", path); gT = nThreads(); double t0 = now();
    int fd = open(tmp, O_CREAT | O_TRUNC | O_RDWR, 0644); uint64_t size = DATA_OFFSET + 4 * NSEEDS;
    if (fd < 0 || ftruncate(fd, size)) { perror(tmp); return 1; }
    char *m = mmap(0, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0); gKeys = malloc(4 * NSEEDS); gCnt = calloc(gT, sizeof *gCnt);
    if (m == MAP_FAILED || !gKeys || !gCnt) { perror("memory"); return 1; }
    fprintf(stderr, "computing keys with %d threads\n", gT); runAll(keyWorker, 1); double t1 = now();
    Header *h = (Header *)m; uint64_t pos = 0;
    for (int b = 0; b < NBUCKETS; b++) { h->off[b] = pos; for (int i = 0; i < gT; i++) { uint64_t c = gCnt[i][b]; gCnt[i][b] = pos; pos += c; } }
    h->off[NBUCKETS] = pos; h->count = pos; h->version = 2; h->genHash = generatorHash();
    gOut = (uint32_t *)(m + DATA_OFFSET); runAll(scatterWorker, 0);
    memcpy(h->magic, "D2SEEDX2", 8); msync(m, size, MS_SYNC); munmap(m, size); fsync(fd); close(fd);
    if (rename(tmp, path)) { perror(path); return 1; }
    fprintf(stderr, "done: %llu seeds, keys %.0fs, write %.0fs\n", (unsigned long long)pos, t1 - t0, now() - t1); return 0;
}
typedef struct { const Header *h; const uint32_t *d; } Table;
static int openTable(const char *path, Table *t) {
    int fd = open(path, O_RDONLY); struct stat st; if (fd < 0) return 0;
    if (fstat(fd, &st) || (uint64_t)st.st_size != DATA_OFFSET + 4 * NSEEDS) { close(fd); return 0; }
    char *m = mmap(0, st.st_size, PROT_READ, MAP_SHARED, fd, 0); close(fd); if (m == MAP_FAILED) return 0;
    t->h = (Header *)m; t->d = (uint32_t *)(m + DATA_OFFSET);
    if (memcmp(t->h->magic, "D2SEEDX2", 8) || t->h->count != NSEEDS || t->h->genHash != generatorHash()) { fprintf(stderr, "table does not match this generator, rebuild it\n"); return 0; }
    return 1;
}
static int verify(const char *path) {
    Table t; if (!openTable(path, &t)) { fprintf(stderr, "cannot use table\n"); return 1; }
    uint8_t *bm = calloc(NSEEDS / 8, 1); uint64_t dup = 0, unsorted = 0, bad = 0, checked = 0, used = 0, big = 0;
    for (int b = 0; b < NBUCKETS; b++) {
        uint64_t a = t.h->off[b], e = t.h->off[b + 1]; used += e > a; if (e - a > big) big = e - a;
        for (uint64_t i = a; i < e; i++) { uint32_t s = t.d[i]; if (s >> 31 || bm[s >> 3] >> (s & 7) & 1) { dup++; continue; } bm[s >> 3] |= 1 << (s & 7); if (i > a && s <= t.d[i - 1]) unsorted++; if ((i * 2654435761ull >> 8) % 20011 == 0) { checked++; bad += keyOf(s) != (uint32_t)b; } }
    }
    uint64_t have = 0; for (uint64_t i = 0; i < NSEEDS / 8; i++) have += __builtin_popcount(bm[i]);
    printf("distinct seeds %llu of %llu, duplicates %llu, unsorted %llu, sampled keys %llu wrong %llu, buckets used %llu, largest %llu\n", (unsigned long long)have, NSEEDS, (unsigned long long)dup, (unsigned long long)unsorted, (unsigned long long)checked, (unsigned long long)bad, (unsigned long long)used, (unsigned long long)big);
    return !(have == NSEEDS && !dup && !unsorted && !bad);
}

// ---- clues ----
typedef struct { int lv, dx, dy, open, closed, theme, preset, file, exists, allow; } Fact;   // -1 = unknown, allow = bit set of permitted exit masks
// soft evidence for one room: a score per exit mask, or per preset and variant (0 = best, negative = worse)
typedef struct { int lv, dx, dy, np; float dflt, absent, mask[16]; struct { int16_t preset; int8_t file; float s; } p[160]; int byPreset; } Weigh;
#define MAXW 64
static Weigh WG[MAXW]; static int NW;
#define MAXF 128
typedef struct { int diff, town, townSoft, nf; Fact f[MAXF]; } Clues;
static const struct { const char *name; int lv, cost; } STOPS[] = { { "halls", HALLSDEAD2, 1 }, { "wsk2", WSK2, 2 }, { "crystalline", CRYSTALLINE, 3 }, { "glacial", GLACIAL, 3 }, { "ancients", ANCIENTS, 4 }, { "jail1", JAIL1, 5 }, { "sewers2", SEWERS2, 6 }, { "catacombs2", CATA2, 7 }, { "durance2", DURANCE2, 9 } };
#define NSTOPS ((int)(sizeof STOPS / sizeof *STOPS))
static int dirMask(const char *s) { int m = 0; for (; *s; s++) { int c = *s & ~32; m |= c == 'W' ? MW : c == 'E' ? ME : c == 'S' ? MS : c == 'N' ? MN : 0x100; } return m; }
static void fail(int line, const char *msg, const char *tok) { printf("{\"error\":\"line %d: %s: %s\"}\n", line, msg, tok); exit(2); }
static void parse(FILE *f, Clues *c) {
    static char ln[16384]; int no = 0, lv = 0; *c = (Clues){ .diff = 2, .town = 0 };
    while (fgets(ln, sizeof ln, f)) {
        no++; ln[strcspn(ln, "#\r\n")] = 0; char *save, *t = strtok_r(ln, " \t", &save); if (!t) continue;
        char *a = strtok_r(0, " \t", &save);
        if (!strcmp(t, "difficulty")) { if (!a) fail(no, "missing value", t); if (!strcmp(a, "normal")) c->diff = 0; else if (!strcmp(a, "nightmare")) c->diff = 1; else if (!strcmp(a, "hell")) c->diff = 2; else fail(no, "bad difficulty", a); }
        else if (!strcmp(t, "town")) { c->town = a ? dirMask(a) : 0; if (c->town < 1 || c->town > 15) fail(no, "town needs W, N, E or S", a ? a : ""); char *k = strtok_r(0, " \t", &save); if (k && !strcmp(k, "soft")) { c->townSoft = c->town; c->town = 0; } }
        else if (!strcmp(t, "stop")) { lv = 0; for (int i = 0; a && i < NSTOPS; i++) if (!strcmp(a, STOPS[i].name)) lv = STOPS[i].lv; if (!lv) fail(no, "unknown stop", a ? a : ""); }
        else if (!strcmp(t, "room")) {
            Fact q = { lv, 0, 0, 0, 0, -1, -1, -1, -1, 0xFFFF }; if (!lv) fail(no, "room before stop", ""); if (!a || sscanf(a, "%d,%d", &q.dx, &q.dy) != 2) fail(no, "room needs dx,dy", a ? a : "");
            if (c->nf == MAXF) fail(no, "too many rooms", "");
            q.exists = 1;
            for (char *k = strtok_r(0, " \t", &save); k; k = strtok_r(0, " \t", &save)) {
                if (!strncmp(k, "open=", 5)) q.open |= dirMask(k + 5); else if (!strncmp(k, "closed=", 7)) q.closed |= dirMask(k + 7);
                else if (!strncmp(k, "exits=", 6)) {
                    if (!strchr(k, '|')) { q.open = dirMask(k + 6); q.closed = 15 & ~q.open; }
                    else { char *sv, *e = strtok_r(k + 6, "|", &sv); for (q.allow = 0; e; e = strtok_r(0, "|", &sv)) { int m = dirMask(e); if (m > 15) fail(no, "bad directions", e); q.allow |= 1 << m; } }
                }
                else if (!strncmp(k, "theme=", 6)) q.theme = atoi(k + 6); else if (!strncmp(k, "preset=", 7)) q.preset = atoi(k + 7); else if (!strncmp(k, "variant=", 8)) q.file = atoi(k + 8);
                else if (!strcmp(k, "absent")) q.exists = 0; else fail(no, "unknown word", k);
            }
            if ((q.open | q.closed) > 15 || (q.open & q.closed)) fail(no, "bad directions", "");
            if ((q.theme >= 0 || q.preset >= 0) && !hasLooks(lv)) fail(no, "theme and preset are not supported at this stop", "");
            if (q.file >= 0 && !hasVariants(lv)) fail(no, "variant is only supported at catacombs2 and sewers2", "");
            c->f[c->nf++] = q;
        } else if (!strcmp(t, "weigh")) {
            if (!lv || NW == MAXW) fail(no, "weigh before stop, or too many", ""); Weigh *g = &WG[NW]; memset(g, 0, sizeof *g); g->lv = lv; g->dflt = g->absent = -6;
            if (!a || sscanf(a, "%d,%d", &g->dx, &g->dy) != 2) fail(no, "weigh needs dx,dy", a ? a : ""); for (int i = 0; i < 16; i++) g->mask[i] = NAN;
            for (char *k = strtok_r(0, " \t", &save); k; k = strtok_r(0, " \t", &save)) {
                char *e = strchr(k, '='); if (!e) fail(no, "weigh needs name=score", k);
                *e = 0; float v = strtof(e + 1, 0);
                if (!strcmp(k, "default")) g->dflt = v; else if (!strcmp(k, "absent")) g->absent = v;
                else if (k[0] >= '0' && k[0] <= '9') { if (!hasLooks(lv)) fail(no, "presets are not supported at this stop", k); if (g->np < 160) { char *d = strchr(k, '.'); g->p[g->np].preset = (int16_t)atoi(k); g->p[g->np].file = d && hasVariants(lv) ? (int8_t)atoi(d + 1) : -1; g->p[g->np++].s = v; g->byPreset = 1; } }
                else { int m = dirMask(k); if (m > 15) fail(no, "bad directions", k); g->mask[m] = v; }
            }
            NW++;
        } else fail(no, "unknown line", t);
    }
}
static int wrong(const Fact *q, int lv, int mask, int preset, int file) {
    if ((mask & q->open) != q->open || (mask & q->closed) || !(q->allow >> mask & 1)) return 1;
    if (q->preset >= 0 && preset != q->preset) return 1;
    if (q->theme >= 0 && (typeOf(lv, preset) == 1) != (q->theme != 0)) return 1;
    return q->file >= 0 && file != q->file;
}
typedef struct { int lv, looks, keyed; const Fact *f[MAXF]; int n; } Group;
static Clues C; static Group G[NSTOPS]; static int NG, TOL;
// number of wrong clues, stops once above TOL; skipKeyed leaves out the table stops
static int count(uint32_t seed, int m, int skipKeyed) {
    if (C.town && !(townExit(seed) & C.town) && ++m > TOL) return m;
    uint32_t st = startSeed(seed);
    for (int g = 0; g < NG; g++) {
        if (G[g].keyed || (skipKeyed && (G[g].lv == CATA2 || G[g].lv == SEWERS2 || G[g].lv == JAIL1))) continue;
        Room r[MAXR]; Look v[MAXR]; int lv = G[g].lv, n = G[g].looks ? genLooks(st, lv, C.diff, r, v) : genLayout(st, lv, C.diff, r, 0, 0), w = -1;
        for (int i = 0; i < n; i++) if (r[i].kind == K_WAYPOINT) { w = i; break; }
        for (int k = 0; k < G[g].n; k++) {
            const Fact *q = G[g].f[k]; int p = w < 0 ? -1 : roomAt(r, n, r[w].x + q->dx, r[w].y + q->dy);
            int bad = q->exists ? (p < 0 || wrong(q, lv, r[p].mask, G[g].looks ? v[p].preset : -1, G[g].looks ? v[p].file : -1)) : p >= 0;
            if (bad && ++m > TOL) return m;
        }
    }
    return m;
}
// base: wrong clues already implied by the table group. Other stops are checked against what is
// left of the tolerance first, so most seeds in groups with a mistake are rejected cheaply.
static int misses(uint32_t seed, int base) { if (base && count(seed, base, 1) > TOL) return TOL + 1; return count(seed, 0, 0); }
// clues a table id contradicts at one stop (a lower bound on misses())
static int idMisses(int lv, int dir, int e, int type, int file) {
    int m = 0, mask = maskOf(dir, e);
    for (int k = 0; k < C.nf; k++) {
        const Fact *q = &C.f[k]; if (q->lv != lv) continue;
        if (!q->dx && !q->dy) { int w = BIT[dir]; m += q->exists ? (w & q->open) != q->open || (w & q->closed) || !(q->allow >> w & 1) : 1; continue; }
        if (q->dx != DX[dir] || q->dy != DY[dir]) continue;
        if (!q->exists) { m++; continue; }
        int bad = (mask & q->open) != q->open || (mask & q->closed) || !(q->allow >> mask & 1);
        if (type < 0) { m += bad; continue; }          // Jail: room type is not part of the key
        if (q->theme >= 0 && (type == 1) != (q->theme != 0) && !(lv == SEWERS2 && type == 1 && q->theme == 0)) bad = 1;
        if (q->preset >= 0) { int k2 = q->preset - presetBase(lv), ty = typeOf(lv, q->preset); if (lv == SEWERS2) ty = ty ? 1 : 0; if (ty != type) bad = 1; else if (typeOf(lv, q->preset) < 2 && (ty ? k2 - 15 : k2) != mask) bad = 1; }
        if (q->file >= 0 && (q->file & (lv == SEWERS2 ? 1 : 3)) != file) bad = 1;
        m += bad;
    }
    return m;
}
// true if the table key already decides every clue of this stop: waypoint room and the one next to it, exits only
static int decidedByKey(const Group *g) {
    if (g->lv != CATA2 && g->lv != SEWERS2 && g->lv != JAIL1) return 0;
    const Fact *w = 0; for (int k = 0; k < g->n; k++) if (!g->f[k]->dx && !g->f[k]->dy) w = g->f[k];
    if (!w || !w->exists || w->theme >= 0 || w->preset >= 0 || w->file >= 0) return 0;
    for (int d = 0; d < 4; d++) {
        if ((BIT[d] & w->open) != w->open || (BIT[d] & w->closed) || !(w->allow >> BIT[d] & 1)) continue;
        for (int k = 0; k < g->n; k++) { const Fact *q = g->f[k]; if (q->theme >= 0 || q->preset >= 0 || q->file >= 0) return 0; if ((q->dx || q->dy) && (q->dx != DX[d] || q->dy != DY[d])) return 0; }
    }
    return 1;
}
// ---- ranking by soft evidence ----
static _Atomic float gFloor = -1e9f; static int KEEP = 200;
static float weighOne(const Weigh *g, int mask, int preset, int file) {
    if (!g->byPreset) return isnan(g->mask[mask]) ? g->dflt : g->mask[mask];
    float best = g->dflt; int hit = 0;
    for (int i = 0; i < g->np; i++) if (g->p[i].preset == preset && (g->p[i].file < 0 || g->p[i].file == file) && (!hit || g->p[i].s > best)) { best = g->p[i].s; hit = 1; }
    return best;
}
static float score(uint32_t seed, float floor_) {
    float t = C.townSoft && !(townExit(seed) & C.townSoft) ? -5.0f : 0; uint32_t st = startSeed(seed);      // a misread town should not rule out a seed
    for (int s = 0; s < NSTOPS; s++) {
        int lv = STOPS[s].lv, any = 0, looks = 0; for (int i = 0; i < NW; i++) if (WG[i].lv == lv) { any = 1; looks |= WG[i].byPreset; }
        if (!any) continue;
        Room r[MAXR]; Look v[MAXR]; int n = looks ? genLooks(st, lv, C.diff, r, v) : genLayout(st, lv, C.diff, r, 0, 0), w = -1;
        for (int i = 0; i < n; i++) if (r[i].kind == K_WAYPOINT) { w = i; break; }
        for (int i = 0; i < NW; i++) if (WG[i].lv == lv) { int p = w < 0 ? -1 : roomAt(r, n, r[w].x + WG[i].dx, r[w].y + WG[i].dy); t += p < 0 ? WG[i].absent : weighOne(&WG[i], r[p].mask, looks ? v[p].preset : 0, looks ? v[p].file : 0); }
        if (t < floor_) return -1e9f;
    }
    return t;
}
typedef struct { float f; uint32_t s; } Ranked;
typedef struct { uint64_t a, b; int base; } Seg;
static Seg *segs; static int nSegs; static atomic_ullong segNext; static const uint32_t *segData; static uint64_t segTotal, *segCum;
typedef struct { uint32_t *s; uint8_t *m; uint64_t n, cap; Ranked *r; int nr; uint64_t pass; } Hits;
static void *solveWorker(void *p) {
    Hits *h = p; const uint64_t CH = 16384;
    for (;;) {
        uint64_t i = atomic_fetch_add(&segNext, CH), e = i + CH; if (i >= segTotal) return 0; if (e > segTotal) e = segTotal;
        int lo_ = 0, hi = nSegs - 1; while (lo_ < hi) { int mid = (lo_ + hi + 1) / 2; if (segCum[mid] <= i) lo_ = mid; else hi = mid - 1; }
        for (int s = lo_; i < e; i++) {
            while (i >= segCum[s] + (segs[s].b - segs[s].a)) s++;
            uint64_t at = segs[s].a + (i - segCum[s]); uint32_t seed = segData ? segData[at] : (uint32_t)at; int m = misses(seed, segs[s].base);
            if (m <= TOL && NW) {       // keep the KEEP best in a small heap
                h->pass++; float fl = atomic_load_explicit(&gFloor, memory_order_relaxed), f = score(seed, fl); if (f <= fl) continue;
                if (h->nr < KEEP) { int x = h->nr++; h->r[x] = (Ranked){ f, seed }; while (x && h->r[(x - 1) / 2].f > h->r[x].f) { Ranked q = h->r[x]; h->r[x] = h->r[(x - 1) / 2]; h->r[(x - 1) / 2] = q; x = (x - 1) / 2; } }
                else if (f > h->r[0].f) { h->r[0] = (Ranked){ f, seed }; for (int x = 0;;) { int l = 2 * x + 1; if (l >= KEEP) break; if (l + 1 < KEEP && h->r[l + 1].f < h->r[l].f) l++; if (h->r[x].f <= h->r[l].f) break; Ranked q = h->r[x]; h->r[x] = h->r[l]; h->r[l] = q; x = l; } }
                if (h->nr == KEEP) { float cur = atomic_load(&gFloor); while (h->r[0].f > cur && !atomic_compare_exchange_weak(&gFloor, &cur, h->r[0].f)) ; }
                continue;
            }
            if (m <= TOL) { if (h->n == h->cap) { h->cap = h->cap ? h->cap * 2 : 1024; h->s = realloc(h->s, h->cap * 4); h->m = realloc(h->m, h->cap); } h->s[h->n] = seed; h->m[h->n++] = (uint8_t)m; }
        }
    }
}
typedef struct { uint8_t m; uint32_t s; } One;
static int cmpOne(const void *a, const void *b) { const One *x = a, *y = b; return x->m != y->m ? x->m - y->m : x->s < y->s ? -1 : x->s > y->s; }
static int cmpRanked(const void *a, const void *b) { const Ranked *x = a, *y = b; return x->f > y->f ? -1 : x->f < y->f; }
static int solve(const char *path, FILE *in, int limit) {
    double t0 = now(); parse(in, &C); if (!C.nf && !C.town && !NW) { printf("{\"error\":\"no clues\"}\n"); return 2; }
    for (int i = 0; i < NSTOPS; i++) { Group g = { .lv = STOPS[i].lv }; for (int k = 0; k < C.nf; k++) if (C.f[k].lv == g.lv) { g.f[g.n++] = &C.f[k]; g.looks |= C.f[k].theme >= 0 || C.f[k].preset >= 0 || C.f[k].file >= 0; } if (g.n) G[NG++] = g; }
    int cm[512], sm[128], jm[32]; uint64_t total = 0; Table t = { 0 };
    for (int i = 0; i < 512; i++) cm[i] = idMisses(CATA2, i >> 7, i >> 4 & 7, i >> 2 & 3, i & 3);
    for (int i = 0; i < 32; i++) jm[i] = idMisses(JAIL1, i >> 3, i & 7, -1, 0);
    for (int i = 0; i < 128; i++) sm[i] = idMisses(SEWERS2, i >> 5, i >> 2 & 7, i >> 1 & 1, i & 1);
    int have = openTable(path, &t); segs = malloc(sizeof(Seg) * (NBUCKETS + 1)); segCum = malloc(8 * (NBUCKETS + 1));
    if (have) { for (int b = 0; b < NBUCKETS; b++) { uint64_t a = t.h->off[b], e = t.h->off[b + 1]; int base = cm[b >> 12] + jm[b >> 7 & 31] + sm[b & 127]; if (e == a || base > TOL) continue; if (nSegs && segs[nSegs - 1].b == a && segs[nSegs - 1].base == base) segs[nSegs - 1].b = e; else segs[nSegs++] = (Seg){ a, e, base }; total += e - a; } segData = t.d; }
    const char *mode = "table";
    if (!have || total > NSEEDS / 2) { mode = "full scan"; segData = 0; nSegs = 1; segs[0] = (Seg){ 0, NSEEDS, 0 }; total = NSEEDS; }
    if (segData && !TOL) for (int g = 0; g < NG; g++) G[g].keyed = decidedByKey(&G[g]);
    uint64_t c = 0; for (int i = 0; i < nSegs; i++) { segCum[i] = c; c += segs[i].b - segs[i].a; } segTotal = total;
    int T = nThreads(); pthread_t th[64]; Hits h[64]; memset(h, 0, sizeof h);
    for (int i = 0; i < T; i++) { h[i].r = malloc(sizeof(Ranked) * KEEP); pthread_create(&th[i], 0, solveWorker, &h[i]); }
    uint64_t n = 0; for (int i = 0; i < T; i++) { pthread_join(th[i], 0); n += h[i].n; }
    if (NW) {
        Ranked *R = malloc(sizeof(Ranked) * (T * KEEP + 1)); int k = 0; uint64_t pass = 0; for (int i = 0; i < T; i++) { pass += h[i].pass; for (int j = 0; j < h[i].nr; j++) R[k++] = h[i].r[j]; }
        qsort(R, k, sizeof *R, cmpRanked); if (k > KEEP) k = KEEP;
        double z = 0; for (int i = 0; i < k; i++) z += exp(R[i].f - R[0].f);
        printf("{\"candidates\":%llu,\"confidence\":%.4f,\"ranked\":[", (unsigned long long)pass, k ? 1 / z : 0.0);
        for (int i = 0; i < k && i < limit; i++) printf("%s[%u,%.2f]", i ? "," : "", R[i].s, R[i].f);
        printf("],\"mode\":\"%s\",\"tested\":%llu,\"ms\":%.0f}\n", mode, (unsigned long long)total, (now() - t0) * 1e3); return 0;
    }
    One *o = malloc(sizeof(One) * (n + 1)); uint64_t k = 0; for (int i = 0; i < T; i++) for (uint64_t j = 0; j < h[i].n; j++) o[k++] = (One){ h[i].m[j], h[i].s[j] };
    qsort(o, n, sizeof *o, cmpOne); uint64_t exact = 0; for (uint64_t i = 0; i < n; i++) exact += !o[i].m;
    printf("{\"matches\":%llu,\"exact\":%llu,\"seeds\":[", (unsigned long long)n, (unsigned long long)exact);
    for (uint64_t i = 0; i < n && i < (uint64_t)limit; i++) printf("%s%u", i ? "," : "", o[i].s);
    printf("],\"wrongClues\":["); for (uint64_t i = 0; i < n && i < (uint64_t)limit; i++) printf("%s%d", i ? "," : "", o[i].m);
    printf("],\"mode\":\"%s\",\"tested\":%llu,\"ms\":%.0f}\n", mode, (unsigned long long)total, (now() - t0) * 1e3); return 0;
}
static void dirs(int m) { if (m & MW) putchar('W'); if (m & MN) putchar('N'); if (m & ME) putchar('E'); if (m & MS) putchar('S'); }
static int diffArg(const char *s) { return !strcmp(s, "normal") ? 0 : !strcmp(s, "nightmare") ? 1 : !strcmp(s, "hell") ? 2 : -1; }
static int describe(int argc, char **argv) {
    uint32_t seed = (uint32_t)strtoul(argv[2], 0, 10), st = startSeed(seed); int diff = 2, i = 3; if (argc > 3 && diffArg(argv[3]) >= 0) diff = diffArg(argv[i++]);
    printf("difficulty %s\ntown ", diff == 0 ? "normal" : diff == 1 ? "nightmare" : "hell"); dirs(townExit(seed)); putchar('\n');
    static char *def[] = { "catacombs2", "sewers2", "jail1" }; char **names = argc > i ? argv + i : def; int nn = argc > i ? argc - i : 3;
    for (int s = 0; s < nn; s++) for (int q = 0; q < NSTOPS; q++) if (!strcmp(names[s], STOPS[q].name)) {
        int lv = STOPS[q].lv; Room r[MAXR]; Look v[MAXR]; int n = hasLooks(lv) ? genLooks(st, lv, diff, r, v) : genLayout(st, lv, diff, r, 0, 0), w = -1;
        for (int k = 0; k < n; k++) if (r[k].kind == K_WAYPOINT) { w = k; break; }
        if (w < 0) continue;
        int d = 0; while (!(r[w].mask & BIT[d])) d++;
        int p = roomAt(r, n, r[w].x + DX[d], r[w].y + DY[d]); printf("stop %s\nroom 0,0 exits=", names[s]); dirs(r[w].mask);
        printf("\nroom %d,%d exits=", DX[d], DY[d]); dirs(r[p].mask); if (hasLooks(lv)) printf(" preset=%d", v[p].preset); if (hasVariants(lv)) printf(" variant=%d", v[p].file); putchar('\n');
        for (int e = 0; e < 4; e++) if ((r[p].mask & BIT[e]) && e != ((d + 2) & 3)) { int k = roomAt(r, n, r[p].x + DX[e], r[p].y + DY[e]); if (k >= 0) { printf("room %d,%d exits=", r[k].x - r[w].x, r[k].y - r[w].y); dirs(r[k].mask); putchar('\n'); } }
    }
    return 0;
}
int main(int argc, char **argv) {
    if (argc >= 3 && !strcmp(argv[1], "build")) return build(argv[2]);
    if (argc >= 3 && !strcmp(argv[1], "verify")) return verify(argv[2]);
    if (argc >= 3 && !strcmp(argv[1], "describe")) return describe(argc, argv);
    if (argc >= 3 && !strcmp(argv[1], "facts")) {
        uint32_t s = (uint32_t)strtoul(argv[2], 0, 10); int t = durielTomb(s);
        printf("{\"seed\":%u,\"town\":\"", s); dirs(townExit(s)); printf("\",\"summoner\":\""); dirs(summonerArm(s)); printf("\",\"nihlathak\":\""); dirs(nihlathakArm(s)); int big; tombLevels(s, &big); printf("\",\"tomb\":%d,\"tombLevel\":%d,\"bigTomb\":%d,\"bigTombLevel\":%d}\n", tombFromLeft(t), t, tombFromLeft(big), big); return 0;
    }
    if (argc >= 4 && !strcmp(argv[1], "dump")) { Room r[MAXR]; Look v[MAXR]; int lv = atoi(argv[3]), df = argc > 4 ? atoi(argv[4]) : 2; uint32_t st = startSeed((uint32_t)strtoul(argv[2], 0, 10)); int L = hasLooks(lv), n = L ? genLooks(st, lv, df, r, v) : genLayout(st, lv, df, r, 0, 0), mx = 99, my = 99; for (int i = 0; i < n; i++) { if (r[i].x < mx) mx = r[i].x; if (r[i].y < my) my = r[i].y; } for (int i = 0; i < n; i++) printf("%d,%d,%d,%d,%d,%d\n", r[i].x - mx, r[i].y - my, r[i].mask, r[i].kind, L ? v[i].preset : 0, L ? v[i].file : 0); return n == 0; }
    if (argc >= 3 && !strcmp(argv[1], "solve")) {
        FILE *in = stdin; int limit = 50;
        for (int i = 3; i < argc; i++) { if (!strcmp(argv[i], "--limit") && i + 1 < argc) limit = atoi(argv[++i]); else if (!strcmp(argv[i], "--tolerate") && i + 1 < argc) TOL = atoi(argv[++i]); else if (!(in = fopen(argv[i], "r"))) { perror(argv[i]); return 1; } }
        if (TOL < 0 || TOL > 1) { fprintf(stderr, "--tolerate takes 0 or 1\n"); return 1; }
        return solve(argv[2], in, limit);
    }
    fprintf(stderr, "usage: seedfinder build|verify|solve <table> ... | describe <seed> [difficulty] [stop...] | facts <seed> | dump <seed> <level>\n"); return 1;
}
