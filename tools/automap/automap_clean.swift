// automap_clean: isolate the D2R automap from a screenshot.
//   swiftc -O automap_clean.swift -o automap_clean
//   ./automap_clean screenshot.png [outdir] [scale]
// Writes <name>_clean.png (bright walls on black), <name>_flat.png (top-down view)
// and <name>_edges.json (detected wall segments on the 5-step tile grid).
//
// Automap walls always run along the two isometric directions, sit on a fixed
// tile grid and have a nearly constant colour. Every possible grid segment gets a
// score: wall-coloured pixels on the segment minus those just above and below it.
// Monsters, fire and floor textures rarely line up with a whole segment.
import Foundation
import CoreGraphics
import ImageIO

let args = CommandLine.arguments
guard args.count > 1 else { print("usage: automap_clean <image> [outdir] [scale]"); exit(1) }
let url = URL(fileURLWithPath: args[1])
let outDir = args.count > 2 ? args[2] : url.deletingLastPathComponent().path
guard let src = CGImageSourceCreateWithURL(url as CFURL, nil), let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { print("cannot read image"); exit(1) }
let W = img.width, H = img.height
var px = [UInt8](repeating: 0, count: W * H * 4)
let cs = CGColorSpace(name: CGColorSpace.sRGB)!
px.withUnsafeMutableBytes { b in
    let c = CGContext(data: b.baseAddress, width: W, height: H, bitsPerComponent: 8, bytesPerRow: W * 4, space: cs, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    c.draw(img, in: CGRect(x: 0, y: 0, width: W, height: H))
}
// pixels per game step along screen x; 6.487 at 1986 px height (calibrated on D2R 3.4)
let K = (args.count > 3 ? Double(args[3])! : 1.0) * 6.487 * Double(H) / 1986.0
let TX = 5 * K, TY = 5 * K / 2            // one tile along +x: (+TX,+TY); along +y: (-TX,+TY)
let S = K / 6.487

@inline(__always) func rgb(_ x: Int, _ y: Int) -> (Int, Int, Int) { let i = (y * W + x) * 4; return (Int(px[i]), Int(px[i+1]), Int(px[i+2])) }
func brown(_ r: Int, _ g: Int, _ b: Int) -> Bool { r >= 36 && r <= 140 && r - g >= 1 && r - g <= 24 && (r - b) * 100 >= 24 * r && (r - b) * 100 <= 56 * r }
func red(_ r: Int, _ g: Int, _ b: Int) -> Bool { r >= 44 && r <= 190 && g * 100 <= 46 * r && b * 100 <= 50 * r && g * 100 >= 18 * r && abs(g - b) < 18 }
func door(_ r: Int, _ g: Int, _ b: Int) -> Bool { r > 190 && g > 150 && b < 120 && r - b > 100 && g * 100 > 68 * r }
func blocked(_ x: Int, _ y: Int) -> Bool {   // HUD
    let fx = Double(x) / Double(W), fy = Double(y) / Double(H)
    if fy > 0.895 { return true }
    if fy > 0.80 && (fx < 0.26 || fx > 0.74) { return true }
    if fy < 0.11 && fx < 0.22 { return true }
    return fy < 0.26 && fx > 0.87
}
var mask = [[UInt8]](repeating: [UInt8](repeating: 0, count: W * H), count: 2)
var doorMask = [UInt8](repeating: 0, count: W * H)
for y in 0..<H { for x in 0..<W where !blocked(x, y) {
    let (r, g, b) = rgb(x, y); let i = y * W + x
    if door(r, g, b) { doorMask[i] = 1; mask[0][i] = 1; mask[1][i] = 1 } else { if brown(r, g, b) { mask[0][i] = 1 }; if red(r, g, b) { mask[1][i] = 1 } }
} }
// vertical prefix sums make "fraction in a band" cheap
func prefix(_ m: [UInt8]) -> [Int32] { var p = [Int32](repeating: 0, count: W * (H + 1)); for x in 0..<W { var s: Int32 = 0; for y in 0..<H { s += Int32(m[y * W + x]); p[(y + 1) * W + x] = s } }; return p }
let pre = mask.map(prefix)
@inline(__always) func band(_ p: [Int32], _ x: Int, _ a: Int, _ b: Int) -> Double { // mean of rows a..<b
    if x < 0 || x >= W || a < 0 || b > H { return 0 }
    return Double(p[b * W + x] - p[a * W + x]) / Double(b - a)
}
// wall profiles (pixels above / below the base line): tall boards, low posts
let profiles = [(17.0, 5.0), (9.0, 7.0)]
var hU = 0, hD = 0
let gap = Int((5 * S).rounded()), side = Int((11 * S).rounded())
func use(_ i: Int) { hU = Int((profiles[i].0 * S).rounded()); hD = Int((profiles[i].1 * S).rounded()) }
func segment(_ p: [Int32], _ x0: Double, _ y0: Double, _ dx: Double, _ dy: Double) -> Double {
    var on = 0.0, off = 0.0, hits = 0.0; let n = 14
    for k in 0..<n {
        let t = (Double(k) + 0.5) / Double(n), x = Int(x0 + dx * t), y = Int(y0 + dy * t)
        let v = band(p, x, y - hU, y + hD); on += v; if v > 0.40 { hits += 1 }
        off += 0.5 * (band(p, x, y - hU - gap - side, y - hU - gap) + band(p, x, y + hD + gap, y + hD + gap + side))
    }
    let cover = hits / Double(n)
    return cover * max(0, on / Double(n) - 0.55 * off / Double(n))
}
let ci = Int(Double(W) / TX) + 2, cj = Int(Double(H) / TY) + 2
func scan(_ p: [Int32], _ ox: Double, _ oy: Double, _ step: Int, _ f: (Int, Int, Int, Double, Double, Double) -> Void) {
    var a = -cj; while a <= cj + ci { var b = -ci - cj; while b <= ci + cj {
        let x = ox + Double(a - b) * TX, y = oy + Double(a + b) * TY
        if x > -TX && x < Double(W) + TX && y > 0 && y < Double(H) {
            f(a, b, 0, x, y, segment(p, x, y, TX, TY)); f(a, b, 1, x, y, segment(p, x, y, -TX, TY))
        }
        b += step }; a += step }
}
// best tile-grid phase and colour family
var best = (-1.0, 0.0, 0.0, 0, 0)
for (m, pf) in [(0, 0), (0, 1), (1, 0)] {
    use(pf)
    var coarse = [(Double, Double, Double)]()
    for iu in 0..<10 { for iv in 0..<10 {
        let u = Double(iu) / 10, v = Double(iv) / 10, ox = Double(W) / 2 + (u - v) * TX, oy = Double(H) / 2 + (u + v) * TY
        var s = 0.0; scan(pre[m], ox, oy, 1) { _, _, _, _, _, q in if q > 0.28 { s += q * q } }
        coarse.append((s, u, v)) } }
    coarse.sort { $0.0 > $1.0 }
    for c in coarse.prefix(2) { for du in stride(from: -0.08, through: 0.08, by: 0.04) { for dv in stride(from: -0.08, through: 0.08, by: 0.04) {
        let u = c.1 + du, v = c.2 + dv, ox = Double(W) / 2 + (u - v) * TX, oy = Double(H) / 2 + (u + v) * TY
        var s = 0.0; scan(pre[m], ox, oy, 1) { _, _, _, _, _, q in if q > 0.28 { s += q * q } }
        if s > best.0 { best = (s, ox, oy, m, pf) } } } }
}
let (_, OX, OY, fam, prof) = best
use(prof)
struct Edge { var a: Int, b: Int, d: Int, x: Double, y: Double, q: Double }
var all = [String: Edge]()
scan(pre[fam], OX, OY, 1) { a, b, d, x, y, q in if q > 0.12 { all["\(a),\(b),\(d)"] = Edge(a: a, b: b, d: d, x: x, y: y, q: q) } }
func isDoor(_ e: Edge) -> Bool { var n = 0; let dx = e.d == 0 ? TX : -TX; for k in 0..<12 { let t = (Double(k) + 0.5) / 12, x = Int(e.x + dx * t), y = Int(e.y + TY * t); for v in stride(from: -hU, to: hD, by: 2) { let yy = y + v; if x >= 0 && x < W && yy >= 0 && yy < H && doorMask[yy * W + x] == 1 { n += 1 } } }; return n > 22 }
// keep strong segments, plus weaker ones that continue or join kept ones
func ends(_ e: Edge) -> [(Int, Int)] { e.d == 0 ? [(e.a, e.b), (e.a + 1, e.b)] : [(e.a, e.b), (e.a, e.b + 1)] }
let strong = 0.34, weak = 0.20
var keep = all.filter { $0.value.q > strong }
for _ in 0..<3 {
    var pts = [String: Int](); for e in keep.values { for p in ends(e) { pts["\(p.0),\(p.1)", default: 0] += 1 } }
    for (k, e) in all where keep[k] == nil && e.q > weak { let n = ends(e).filter { pts["\($0.0),\($0.1)"] != nil }.count; if n == 2 || (n == 1 && e.q > 0.26) { keep[k] = e } }
}
// prune one-segment spurs hanging off a line, then drop groups with no straight run of 3
func nodes(_ k: [String: Edge]) -> [String: [String]] { var pt = [String: [String]](); for (n, e) in k { for p in ends(e) { pt["\(p.0),\(p.1)", default: []].append(n) } }; return pt }
func next(_ e: Edge, _ s: Int) -> String { e.d == 0 ? "\(e.a + s),\(e.b),0" : "\(e.a),\(e.b + s),1" }
for _ in 0..<2 {
    let pt = nodes(keep); var gone = [String]()
    for (k, e) in keep {
        let deg = ends(e).map { pt["\($0.0),\($0.1)"]!.count }
        let free = deg.filter { $0 == 1 }.count, other = deg.max()!
        let inLine = keep[next(e, 1)] != nil || keep[next(e, -1)] != nil
        if free == 1 && other >= 3 && !inLine && e.q < 0.72 && !isDoor(e) { gone.append(k) }
    }
    for k in gone { keep[k] = nil }
}
// little diamonds in corners: remove the two weaker sides when all four are present
for (k, e) in keep where e.d == 0 {
    let q = ["\(e.a),\(e.b),0", "\(e.a),\(e.b + 1),0", "\(e.a),\(e.b),1", "\(e.a + 1),\(e.b),1"]
    if q.allSatisfy({ keep[$0] != nil }) { let r = q.sorted { keep[$0]!.q < keep[$1]!.q }; for x in r.prefix(2) where keep[next(keep[x]!, 1)] == nil || keep[next(keep[x]!, -1)] == nil { keep[x] = nil } }
    _ = k
}
let pt = nodes(keep)
var seen = Set<String>(); var final = [Edge]()
for k in keep.keys where !seen.contains(k) {
    var st = [k], grp = [String](); seen.insert(k)
    while let q = st.popLast() { grp.append(q); for p in ends(keep[q]!) { for n in pt["\(p.0),\(p.1)"]! where !seen.contains(n) { seen.insert(n); st.append(n) } } }
    let run = grp.contains { let e = keep[$0]!; return keep[next(e, 1)] != nil && keep[next(e, -1)] != nil }
    if grp.count >= 4 && run { final += grp.map { keep[$0]! } }
}
// output images
func ctx(_ w: Int, _ h: Int) -> CGContext { let c = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4, space: cs, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!; c.setFillColor(CGColor(red: 0, green: 0, blue: 0, alpha: 1)); c.fill(CGRect(x: 0, y: 0, width: w, height: h)); c.translateBy(x: 0, y: CGFloat(h)); c.scaleBy(x: 1, y: -1); c.setLineCap(.round); return c }
func save(_ c: CGContext, _ p: String) { let d = CGImageDestinationCreateWithURL(URL(fileURLWithPath: p) as CFURL, "public.png" as CFString, 1, nil)!; CGImageDestinationAddImage(d, c.makeImage()!, nil); CGImageDestinationFinalize(d) }
let name = url.deletingPathExtension().lastPathComponent
let c1 = ctx(W, H); let wall = CGColor(red: 1, green: 1, blue: 1, alpha: 1), dcol = CGColor(red: 1, green: 0.8, blue: 0, alpha: 1)
for e in final { c1.setStrokeColor(isDoor(e) ? dcol : wall); c1.setLineWidth(6 * S); c1.move(to: CGPoint(x: e.x, y: e.y - 6 * S)); c1.addLine(to: CGPoint(x: e.x + (e.d == 0 ? TX : -TX), y: e.y + TY - 6 * S)); c1.strokePath() }
c1.setFillColor(CGColor(red: 0.2, green: 0.6, blue: 1, alpha: 1)); c1.fillEllipse(in: CGRect(x: Double(W) / 2 + 2 * S - 8, y: 0.491 * Double(H) - 8, width: 16, height: 16))
save(c1, "\(outDir)/\(name)_clean.png")
if !final.isEmpty {
    let as_ = final.map { $0.a }, bs = final.map { $0.b }, a0 = as_.min()! - 1, b0 = bs.min()! - 1, cell = 22
    let fw = (as_.max()! - a0 + 3) * cell, fh = (bs.max()! - b0 + 3) * cell, c2 = ctx(fw, fh)
    for e in final { let x = (e.a - a0) * cell, y = (e.b - b0) * cell; c2.setStrokeColor(isDoor(e) ? dcol : wall); c2.setLineWidth(5); c2.move(to: CGPoint(x: x, y: y)); c2.addLine(to: CGPoint(x: e.d == 0 ? x + cell : x, y: e.d == 0 ? y : y + cell)); c2.strokePath() }
    save(c2, "\(outDir)/\(name)_flat.png")
}
let js = final.map { "[\($0.a),\($0.b),\($0.d),\(String(format: "%.3f", $0.q)),\(isDoor($0) ? 1 : 0)]" }.joined(separator: ",")
try! "{\"ox\":\(OX),\"oy\":\(OY),\"tx\":\(TX),\"ty\":\(TY),\"family\":\(fam),\"edges\":[\(js)]}".write(toFile: "\(outDir)/\(name)_edges.json", atomically: true, encoding: .utf8)
print("\(name): \(final.count) wall segments, colour \(fam == 0 ? "brown" : "red"), profile \(prof)")
