// clearroute: a short walk that passes close to all reachable floor of one level.
// stdin: "w h reach budget_ms sx sy ex ey [vx vy]\n" then w*h bytes (1 = walkable). ex < 0: end anywhere.
// vx vy: a point the walk goes to first (then clears the rest).
// stdout: "covered steps points\n" then one "x y" per line.
// Floor is cut into 4x4 cells. A cell counts as cleared when the walk comes within `reach` steps of it (around walls).
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#define Q 4
#define MAXP 400
static int w, h, W, H, N, reach; static uint8_t *F; static int *id, *cx, *cy, *wt, (*nb)[8], (*nc)[8], *nn;   // cells, neighbours, step costs (5 straight, 7 diagonal)
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec / 1e9; }
static uint32_t rs = 2463534242u; static uint32_t rnd(void) { rs ^= rs << 13; rs ^= rs >> 17; rs ^= rs << 5; return rs; }
static int *nearList, *nearOff, *bkt[8], bn[8], *dtmp;
// shortest distances from s (bucket queue); stops beyond `lim`
static void dist(int s, int *d, int *prev, int lim, int *order, int *cnt) {
    for (int i = 0; i < 8; i++) bn[i] = 0;
    int c = 0, left = 1, k = 0; d[s] = 0; if (prev) prev[s] = -1; bkt[0][bn[0]++] = s;
    for (; left; k++) { int b = k & 7; for (int i = 0; i < bn[b]; i++) { int u = bkt[b][i]; left--; if (d[u] != k) continue; if (order) order[c] = u; c++;
            for (int e = 0; e < nn[u]; e++) { int v = nb[u][e], x = k + nc[u][e]; if (x <= lim && x < d[v]) { d[v] = x; if (prev) prev[v] = u; bkt[x & 7][bn[x & 7]++] = v; left++; } } }
        bn[b] = 0; }
    if (cnt) *cnt = c;
}
static int n, P[MAXP], *D[MAXP], *PV[MAXP], T[MAXP], hasEnd, F0 = 1;   // F0: tour positions before it stay fixed
static int dd(int a, int b) { return D[a][P[b]]; }
static int len(const int *t) { int s = 0; for (int i = 1; i < n; i++) s += dd(t[i - 1], t[i]); return s; }
static void improve(int *t) {
    int top = hasEnd ? n - 1 : n, go = 1;                    // positions 1..top-1 may move
    while (go) {
        go = 0;
        for (int i = 1; i < top - 1; i++) for (int j = i + 1; j < top; j++) {                 // reverse i..j
            if (i < F0) continue;
            int o = dd(t[i - 1], t[i]) + (j + 1 < n ? dd(t[j], t[j + 1]) : 0), m = dd(t[i - 1], t[j]) + (j + 1 < n ? dd(t[i], t[j + 1]) : 0);
            if (m < o) { for (int a = i, b = j; a < b; a++, b--) { int q = t[a]; t[a] = t[b]; t[b] = q; } go = 1; }
        }
        for (int m = 1; m <= 3; m++) for (int i = F0; i + m <= top; i++) {                     // move i..i+m-1 elsewhere
            int a = t[i], b = t[i + m - 1], nx = i + m < n ? t[i + m] : -1, gain = dd(t[i - 1], a) + (nx >= 0 ? dd(b, nx) - dd(t[i - 1], nx) : 0), best = 0, at = -1, rev = 0;
            for (int k = 0; k < top; k++) {                  // insert after position k
                if ((k >= i - 1 && k < i + m) || k < F0 - 1) continue;
                int p = t[k], q = k + 1 < n ? t[k + 1] : -1; int c0 = dd(p, a) + (q >= 0 ? dd(b, q) - dd(p, q) : 0), c1 = dd(p, b) + (q >= 0 ? dd(a, q) - dd(p, q) : 0);
                if (gain - c0 > best) { best = gain - c0; at = k; rev = 0; } if (gain - c1 > best) { best = gain - c1; at = k; rev = 1; }
            }
            if (at < 0) continue;
            int seg[3], u[MAXP], z = 0; for (int x = 0; x < m; x++) seg[x] = rev ? t[i + m - 1 - x] : t[i + x];
            for (int k = 0; k < n; k++) { if (k >= i && k < i + m) continue; u[z++] = t[k]; if (k == at) for (int x = 0; x < m; x++) u[z++] = seg[x]; }
            memcpy(t, u, sizeof(int) * n); go = 1;
        }
    }
}
static void search(double until) {
    int best[MAXP], cur[MAXP]; improve(T); memcpy(best, T, sizeof best); int bl = len(T), top = hasEnd ? n - 1 : n;
    while (now() < until && top > F0 + 7) {                  // double bridge, then improve again
        memcpy(cur, best, sizeof cur); int a = F0 + rnd() % (top - F0 - 2), b = F0 + rnd() % (top - F0 - 2), c = F0 + rnd() % (top - F0 - 2), x;
        if (a > b) { x = a; a = b; b = x; } if (b > c) { x = b; b = c; c = x; } if (a > b) { x = a; a = b; b = x; }
        int z = a, u[MAXP]; memcpy(u, cur, sizeof u); for (int k = b; k < c; k++) u[z++] = cur[k]; for (int k = a; k < b; k++) u[z++] = cur[k];
        improve(u); int l = len(u); if (l < bl) { bl = l; memcpy(best, u, sizeof best); }
    }
    memcpy(T, best, sizeof best);
}
static int *path, pn, *hits;
static void makePath(void) {
    pn = 0; path[pn++] = P[T[0]];
    for (int i = 1; i < n; i++) { int a = T[i - 1], b = P[T[i]], st = pn; for (int q = b; q != P[a]; q = PV[a][q]) path[pn++] = q; for (int x = st, y = pn - 1; x < y; x++, y--) { int q = path[x]; path[x] = path[y]; path[y] = q; } }
}
static void countHits(void) { memset(hits, 0, sizeof(int) * N); for (int i = 0; i < pn; i += i + 2 < pn || i == pn - 1 ? 2 : 1) for (int k = nearOff[path[i]]; k < nearOff[path[i] + 1]; k++) hits[nearList[k]]++; }
static double covered(void) { double s = 0, t = 0; for (int i = 0; i < N; i++) { t += wt[i]; if (hits[i]) s += wt[i]; } return t ? s / t : 0; }
int main(void) {
    int sx, sy, ex, ey, ms, vx = -1, vy = -1; char line[256];
    if (!fgets(line, sizeof line, stdin) || sscanf(line, "%d %d %d %d %d %d %d %d %d %d", &w, &h, &reach, &ms, &sx, &sy, &ex, &ey, &vx, &vy) < 8 || w < 8 || h < 8 || w > 4000 || h > 4000) return 2;
    F = malloc((size_t)w * h); if (!F || fread(F, 1, (size_t)w * h, stdin) != (size_t)w * h) return 2;
    W = w / Q; H = h / Q;
    // floor that can really be reached
    uint8_t *R = calloc((size_t)w * h, 1); int *st = malloc(sizeof(int) * (size_t)w * h), sp = 0, best = -1, bd = 1 << 30;
    for (int y = sy - 20; y <= sy + 20; y++) for (int x = sx - 20; x <= sx + 20; x++) if (x > 0 && y > 0 && x < w - 1 && y < h - 1 && F[y * w + x]) { int d = (x - sx) * (x - sx) + (y - sy) * (y - sy); if (d < bd) { bd = d; best = y * w + x; } }
    if (best < 0) return 3;
    long fine = 0; R[best] = 1; st[sp++] = best;
    while (sp) { int c = st[--sp], x = c % w, y = c / w; fine++; if (x > 0 && F[c - 1] && !R[c - 1]) { R[c - 1] = 1; st[sp++] = c - 1; } if (x < w - 1 && F[c + 1] && !R[c + 1]) { R[c + 1] = 1; st[sp++] = c + 1; } if (y > 0 && F[c - w] && !R[c - w]) { R[c - w] = 1; st[sp++] = c - w; } if (y < h - 1 && F[c + w] && !R[c + w]) { R[c + w] = 1; st[sp++] = c + w; } }
    uint8_t *cnt = calloc((size_t)W * H, 1); id = malloc(sizeof(int) * (size_t)W * H);
    for (int y = 0; y < H * Q; y++) for (int x = 0; x < W * Q; x++) cnt[y / Q * W + x / Q] += R[y * w + x];
    int *list = malloc(sizeof(int) * (size_t)W * H), start = -1;
    for (int th = 9; th >= 3; th -= 2) {                     // loosen until nothing important is cut off
        for (int i = 0; i < W * H; i++) id[i] = -1;
        start = -1; bd = 1 << 30; for (int i = 0; i < W * H; i++) if (cnt[i] >= th) { int x = i % W * Q + 2 - best % w, y = i / W * Q + 2 - best / w; if (x * x + y * y < bd) { bd = x * x + y * y; start = i; } }
        if (start < 0) continue;
        N = 0; long got = 0; id[start] = 0; list[N++] = start;
        for (int i = 0; i < N; i++) { int c = list[i], x = c % W, y = c / W; got += cnt[c]; int t[4] = { x ? c - 1 : -1, x < W - 1 ? c + 1 : -1, y ? c - W : -1, y < H - 1 ? c + W : -1 }; for (int k = 0; k < 4; k++) if (t[k] >= 0 && cnt[t[k]] >= th && id[t[k]] < 0) { id[t[k]] = N; list[N++] = t[k]; } }
        if (got >= 0.96 * fine) break;
    }
    if (start < 0 || N < 2) return 3;
    cx = malloc(4 * N); cy = malloc(4 * N); wt = malloc(4 * N); nb = malloc(sizeof *nb * N); nc = malloc(sizeof *nc * N); nn = calloc(N, 4);
    for (int i = 0; i < N; i++) { cx[i] = list[i] % W; cy[i] = list[i] / W; wt[i] = cnt[list[i]]; }
    for (int i = 0; i < N; i++) for (int dy = -1; dy <= 1; dy++) for (int dx = -1; dx <= 1; dx++) {
        int x = cx[i] + dx, y = cy[i] + dy; if ((!dx && !dy) || x < 0 || y < 0 || x >= W || y >= H || id[y * W + x] < 0) continue;
        if (dx && dy && (id[cy[i] * W + x] < 0 || id[y * W + cx[i]] < 0)) continue;
        nb[i][nn[i]] = id[y * W + x]; nc[i][nn[i]++] = dx && dy ? 7 : 5;
    }
    for (int i = 0; i < 8; i++) bkt[i] = malloc(sizeof(int) * N * 9);
    dtmp = malloc(4 * N); for (int i = 0; i < N; i++) dtmp[i] = 1 << 29;
    // what each cell clears
    int *order = malloc(4 * N), lim = reach * 5 / Q; nearOff = malloc(4 * (N + 1)); size_t cap = (size_t)N * 64, used = 0; nearList = malloc(4 * cap);
    for (int i = 0; i < N; i++) { int c; dist(i, dtmp, 0, lim, order, &c); nearOff[i] = used; if (used + c > cap) { cap = cap * 2 + c; nearList = realloc(nearList, 4 * cap); } for (int k = 0; k < c; k++) { nearList[used++] = order[k]; } for (int k = 0; k < c; k++) dtmp[order[k]] = 1 << 29; }
    nearOff[N] = used;
    // greedy cover
    uint8_t *done = calloc(N, 1); int *gain = malloc(4 * N); double total = 0, left; for (int i = 0; i < N; i++) total += wt[i]; left = total;
    for (int i = 0; i < N; i++) { gain[i] = 0; for (int k = nearOff[i]; k < nearOff[i + 1]; k++) gain[i] += wt[nearList[k]]; }
    int endCell = -1; if (ex >= 0) { bd = 1 << 30; for (int i = 0; i < N; i++) { int x = cx[i] * Q + 2 - ex, y = cy[i] * Q + 2 - ey; if (x * x + y * y < bd) { bd = x * x + y * y; endCell = i; } } if (bd > 900 || !endCell) endCell = -1; }
    int viaCell = -1; if (vx >= 0) { bd = 1 << 30; for (int i = 0; i < N; i++) { int x = cx[i] * Q + 2 - vx, y = cy[i] * Q + 2 - vy; if (x * x + y * y < bd) { bd = x * x + y * y; viaCell = i; } } if (bd > 900 || !viaCell || viaCell == endCell) viaCell = -1; }
    P[n++] = 0; if (viaCell > 0) P[n++] = viaCell; if (endCell > 0) { P[n++] = endCell; hasEnd = 1; }
    for (int i = 0; i < n; i++) for (int k = nearOff[P[i]]; k < nearOff[P[i] + 1]; k++) if (!done[nearList[k]]) { done[nearList[k]] = 1; left -= wt[nearList[k]]; }
    while (n < MAXP - 1 && left > 0.01 * total) {
        int b = -1, bg = 0; for (int i = 0; i < N; i++) if (gain[i] > bg) { int g = 0; for (int k = nearOff[i]; k < nearOff[i + 1]; k++) if (!done[nearList[k]]) g += wt[nearList[k]]; gain[i] = g; if (g > bg) { bg = g; b = i; } }
        if (b < 0 || bg < 8) break;
        P[n++] = b; for (int k = nearOff[b]; k < nearOff[b + 1]; k++) if (!done[nearList[k]]) { done[nearList[k]] = 1; left -= wt[nearList[k]]; }
    }
    for (int i = 0; i < n; i++) { D[i] = malloc(4 * N); PV[i] = malloc(4 * N); for (int k = 0; k < N; k++) D[i][k] = 1 << 29; dist(P[i], D[i], PV[i], 1 << 28, 0, 0); }
    // nearest neighbour, then local search
    uint8_t usedp[MAXP] = { 0 }; T[0] = 0; usedp[0] = 1; int lastPos = hasEnd ? n - 1 : n; if (hasEnd) { T[n - 1] = viaCell > 0 ? 2 : 1; usedp[T[n - 1]] = 1; }
    if (viaCell > 0) { T[1] = 1; usedp[1] = 1; F0 = 2; }
    for (int i = F0; i < lastPos; i++) { int b = -1; for (int j = 0; j < n; j++) if (!usedp[j] && (b < 0 || dd(T[i - 1], j) < dd(T[i - 1], b))) b = j; T[i] = b; usedp[b] = 1; }
    double t0 = now(), bud = ms / 1000.0; search(t0 + bud * 0.4);
    path = malloc(sizeof(int) * ((size_t)N * 4 + 1000) * 4); hits = malloc(4 * N); size_t capPath = ((size_t)N * 4 + 1000) * 4; long tot = len(T) / 5 + n; if ((size_t)tot + 10 > capPath) { path = realloc(path, sizeof(int) * (tot + 1000)); }
    // drop points whose floor the rest of the walk clears anyway
    makePath(); countHits(); double base = covered();
    for (int pass = 0; pass < 3; pass++) for (int i = n - 1 - hasEnd; i >= F0; i--) {
        int keep[MAXP], old = n, save = len(T); memcpy(keep, T, sizeof keep);
        memmove(T + i, T + i + 1, sizeof(int) * (n - i - 1)); n--; int l = len(T);
        if (l >= save) { memcpy(T, keep, sizeof keep); n = old; continue; }
        makePath(); countHits(); if (covered() < base - 0.0006 * (pass + 1)) { memcpy(T, keep, sizeof keep); n = old; }
    }
    // renumber and search again
    { int np[MAXP], *nd[MAXP], *npv[MAXP]; for (int i = 0; i < n; i++) { np[i] = P[T[i]]; nd[i] = D[T[i]]; npv[i] = PV[T[i]]; } for (int i = 0; i < n; i++) { P[i] = np[i]; D[i] = nd[i]; PV[i] = npv[i]; T[i] = i; } }
    search(now() + bud * 0.6); makePath(); countHits();
    double steps = 0; for (int i = 1; i < pn; i++) steps += Q * hypot(cx[path[i]] - cx[path[i - 1]], cy[path[i]] - cy[path[i - 1]]);
    printf("%.4f %.0f %d\n", covered(), steps, n); for (int i = 0; i < pn; i++) printf("%d %d\n", cx[path[i]] * Q + 2, cy[path[i]] * Q + 2);
    return 0;
}
