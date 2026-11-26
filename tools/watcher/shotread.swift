// shotread: read one D2R screenshot and print JSON: level name, difficulty and automap wall segments.
//   swiftc -O shotread.swift -o shotread
//   ./shotread screenshot.png [--debug outdir] [--scale 1.0] [--text-only]
// Everything runs locally (macOS Vision for the text). Reads the image, writes nothing else
// unless --debug is given.
//
// Automap walls always run along the two isometric directions, sit on a fixed
// tile grid and have a nearly constant colour. Every possible grid segment gets a
// score: wall-coloured pixels on the segment minus those just above and below it.
// Monsters, fire and floor textures rarely line up with a whole segment.
import Foundation
import CoreGraphics
import ImageIO
import Vision

var args = Array(CommandLine.arguments.dropFirst())
func opt(_ n: String) -> String? { if let i = args.firstIndex(of: n), i + 1 < args.count { let v = args[i + 1]; args.removeSubrange(i...i + 1); return v }; return nil }
let debugDir = opt("--debug"), scaleArg = Double(opt("--scale") ?? "1") ?? 1
let textOnly = args.contains("--text-only"); args.removeAll { $0 == "--text-only" }
func quit(_ m: String) -> Never { print("{\"error\":\"\(m)\"}"); exit(1) }
guard let file = args.first else { quit("usage: shotread <image>") }
let url = URL(fileURLWithPath: file)
guard let src = CGImageSourceCreateWithURL(url as CFURL, nil), let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { quit("cannot read image") }
let W = img.width, H = img.height
// text in the top right corner: level name and difficulty
var lines = [String]()
if let crop = img.cropping(to: CGRect(x: Int(0.78 * Double(W)), y: Int(0.025 * Double(H)), width: Int(0.215 * Double(W)), height: Int(0.11 * Double(H)))) {
    let req = VNRecognizeTextRequest(); req.recognitionLevel = .accurate; req.usesLanguageCorrection = false; req.recognitionLanguages = ["en-US"]
    try? VNImageRequestHandler(cgImage: crop).perform([req])
    let obs = (req.results ?? []).sorted { $0.boundingBox.midY > $1.boundingBox.midY }
    lines = obs.compactMap { $0.topCandidates(1).first?.string }
}
func js(_ t: String) -> String { "\"" + t.replacingOccurrences(of: "\\", with: "").replacingOccurrences(of: "\"", with: "'") + "\"" }
let textJSON = "[" + lines.map(js).joined(separator: ",") + "]"
if textOnly { print("{\"text\":\(textJSON)}"); exit(0) }
var px = [UInt8](repeating: 0, count: W * H * 4)
let cs = CGColorSpace(name: CGColorSpace.sRGB)!
px.withUnsafeMutableBytes { b in
    let c = CGContext(data: b.baseAddress, width: W, height: H, bitsPerComponent: 8, bytesPerRow: W * 4, space: cs, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    c.draw(img, in: CGRect(x: 0, y: 0, width: W, height: H))
}
// pixels per game step along screen x; 6.487 at 1986 px height (calibrated on D2R 3.4)
let K = scaleArg * 6.487 * Double(H) / 1986.0
let TX = 5 * K, TY = 5 * K / 2            // one tile along +x: (+TX,+TY); along +y: (-TX,+TY)
let S = K / 6.487

@inline(__always) func rgb(_ x: Int, _ y: Int) -> (Int, Int, Int) { let i = (y * W + x) * 4; return (Int(px[i]), Int(px[i+1]), Int(px[i+2])) }
func brown(_ r: Int, _ g: Int, _ b: Int) -> Bool { r >= 36 && r <= 140 && r - g >= 1 && r - g <= 24 && (r - b) * 100 >= 24 * r && (r - b) * 100 <= 56 * r }
func red(_ r: Int, _ g: Int, _ b: Int) -> Bool { r >= 44 && r <= 190 && g * 100 <= 46 * r && b * 100 <= 50 * r && g * 100 >= 18 * r && abs(g - b) < 18 }
func tan(_ r: Int, _ g: Int, _ b: Int) -> Bool { r >= 34 && r <= 185 && r - g >= 4 && r - g <= 36 && (r - b) * 100 >= 30 * r && (r - b) * 100 <= 70 * r && (r - g) * 100 <= 32 * r }
func gold(_ r: Int, _ g: Int, _ b: Int) -> Bool { r >= 76 && r <= 160 && r - g >= 8 && r - g <= 40 && g - b >= 18 && g - b <= 58 && (r - b) * 100 >= 36 * r && (r - b) * 100 <= 66 * r }
func white(_ r: Int, _ g: Int, _ b: Int) -> Bool { r >= 72 && r <= 190 && r - g >= -2 && r - g <= 16 && g - b >= 0 && g - b <= 24 && (r - b) * 100 <= 30 * r }
func door(_ r: Int, _ g: Int, _ b: Int) -> Bool { r > 190 && g > 150 && b < 120 && r - b > 100 && g * 100 > 68 * r }
func blocked(_ x: Int, _ y: Int) -> Bool {   // HUD
    let fx = Double(x) / Double(W), fy = Double(y) / Double(H)
    if fy > 0.895 { return true }
    if fy > 0.80 && (fx < 0.26 || fx > 0.74) { return true }
    if fy < 0.11 && fx < 0.22 { return true }
    return fy < 0.26 && fx > 0.87
}
var mask = [[UInt8]](repeating: [UInt8](repeating: 0, count: W * H), count: 5)
var doorMask = [UInt8](repeating: 0, count: W * H)
for y in 0..<H { for x in 0..<W where !blocked(x, y) {
    let (r, g, b) = rgb(x, y); let i = y * W + x
    if door(r, g, b) { doorMask[i] = 1; mask[0][i] = 1; mask[1][i] = 1; mask[2][i] = 1 } else { if tan(r, g, b) { mask[2][i] = 1 }; if white(r, g, b) { mask[4][i] = 1 }; if gold(r, g, b) { mask[3][i] = 1 }; if brown(r, g, b) { mask[0][i] = 1 }; if red(r, g, b) { mask[1][i] = 1 } }
} }
// vertical prefix sums make "fraction in a band" cheap
func prefix(_ m: [UInt8]) -> [Int32] { var p = [Int32](repeating: 0, count: W * (H + 1)); for x in 0..<W { var s: Int32 = 0; for y in 0..<H { s += Int32(m[y * W + x]); p[(y + 1) * W + x] = s } }; return p }
let pre = mask.map(prefix)
@inline(__always) func band(_ p: [Int32], _ x: Int, _ a: Int, _ b: Int) -> Double { // mean of rows a..<b
    if x < 0 || x >= W || a < 0 || b > H { return 0 }
    return Double(p[b * W + x] - p[a * W + x]) / Double(b - a)
}
// wall profiles (pixels above / below the base line): tall boards, low posts
let profiles = [(12.0, 2.0), (17.0, 5.0), (2.0, 2.0)], cut = 0.30   // the last one: thin fence rails
var hU = 0, hD = 0
let gap = Int((5 * S).rounded()), side = Int((11 * S).rounded())
func use(_ i: Int) { hU = Int((profiles[i].0 * S).rounded()); hD = Int((profiles[i].1 * S).rounded()) }
func segment(_ p: [Int32], _ x0: Double, _ y0: Double, _ dx: Double, _ dy: Double) -> Double {
    var on = 0.0, off = 0.0, hits = 0.0; let n = 14
    for k in 0..<n {
        let t = (Double(k) + 0.5) / Double(n), x = Int(x0 + dx * t), y = Int(y0 + dy * t)
        let v = band(p, x, y - hU, y + hD); on += v; if v > cut { hits += 1 }
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
struct UncheckedBuf: @unchecked Sendable { let p: UnsafeMutablePointer<Double> }
// best tile-grid phase and colour family
var best = (-1.0, 0.0, 0.0, 0, 0)
let head = lines.prefix(2).joined(separator: " ").uppercased()
let families = head.contains("ENCAMP") || head.contains("ROGUE") ? [3] : head.contains("SEWER") ? [2] : head.contains("HALLS OF THE D") || head.contains("TOMB") ? [1] : [0]
for (m, pf) in families.flatMap({ $0 == 3 ? [($0, 2)] : [($0, 0), ($0, 1)] }) {
    use(pf)
    // try all grid positions in parallel; results are stored by index, so the outcome does not depend on timing
    func rate(_ pos: [(Double, Double)]) -> [Double] {
        var out = [Double](repeating: 0, count: pos.count); let p = pre[m]
        out.withUnsafeMutableBufferPointer { buf in
            let b = UncheckedBuf(p: buf.baseAddress!)
            DispatchQueue.concurrentPerform(iterations: pos.count) { i in
                let (u, v) = pos[i]; var s = 0.0
                scan(p, Double(W) / 2 + (u - v) * TX, Double(H) / 2 + (u + v) * TY, 1) { _, _, _, _, _, q in if q > 0.28 { s += q * q } }
                b.p[i] = s
            }
        }
        return out
    }
    var grid = [(Double, Double)](); for iu in 0..<10 { for iv in 0..<10 { grid.append((Double(iu) / 10, Double(iv) / 10)) } }
    var coarse = zip(rate(grid), grid).map { ($0, $1.0, $1.1) }
    coarse.sort { ($0.0, $0.1, $0.2) > ($1.0, $1.1, $1.2) }
    var fine = [(Double, Double)](); for c in coarse.prefix(2) { for du in stride(from: -0.08, through: 0.08, by: 0.04) { for dv in stride(from: -0.08, through: 0.08, by: 0.04) { fine.append((c.1 + du, c.2 + dv)) } } }
    for (s, (u, v)) in zip(rate(fine), fine) where s > best.0 { best = (s, Double(W) / 2 + (u - v) * TX, Double(H) / 2 + (u + v) * TY, m, pf) }
}
let (_, OX, OY, fam, prof) = best
use(prof)
struct Edge { var a: Int, b: Int, d: Int, x: Double, y: Double, q: Double }
var all = [String: Edge]()
scan(pre[fam], OX, OY, 1) { a, b, d, x, y, q in if q > 0.12 { all["\(a),\(b),\(d)"] = Edge(a: a, b: b, d: d, x: x, y: y, q: q) } }
func isDoor(_ e: Edge) -> Bool { var n = 0; let dx = e.d == 0 ? TX : -TX; for k in 0..<12 { let t = (Double(k) + 0.5) / 12, x = Int(e.x + dx * t), y = Int(e.y + TY * t); for v in stride(from: -hU, to: hD, by: 2) { let yy = y + v; if x >= 0 && x < W && yy >= 0 && yy < H && doorMask[yy * W + x] == 1 { n += 1 } } }; return n > 22 }
func ends(_ e: Edge) -> [(Int, Int)] { e.d == 0 ? [(e.a, e.b), (e.a + 1, e.b)] : [(e.a, e.b), (e.a, e.b + 1)] }
func nodes(_ k: [String: Edge]) -> [String: [String]] { var pt = [String: [String]](); for (n, e) in k { for p in ends(e) { pt["\(p.0),\(p.1)", default: []].append(n) } }; return pt }
func next(_ e: Edge, _ s: Int) -> String { e.d == 0 ? "\(e.a + s),\(e.b),0" : "\(e.a),\(e.b + s),1" }
func clean(_ all: [String: Edge]) -> [Edge] {
// keep strong segments, plus weaker ones that continue or join kept ones
let strong = 0.34, weak = 0.20
var keep = all.filter { $0.value.q > strong }
for _ in 0..<3 {
    var pts = [String: Int](); for e in keep.values { for p in ends(e) { pts["\(p.0),\(p.1)", default: 0] += 1 } }
    for (k, e) in all where keep[k] == nil && e.q > weak { let n = ends(e).filter { pts["\($0.0),\($0.1)"] != nil }.count; if n == 2 || (n == 1 && e.q > 0.26) { keep[k] = e } }
}
// prune one-segment spurs hanging off a line, then drop groups with no straight run of 3
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
for k in keep.keys.sorted() {
    guard let e = keep[k], e.d == 0 else { continue }
    let q = ["\(e.a),\(e.b),0", "\(e.a),\(e.b + 1),0", "\(e.a),\(e.b),1", "\(e.a + 1),\(e.b),1"]
    if q.allSatisfy({ keep[$0] != nil }) { let r = q.sorted { (keep[$0]!.q, $0) < (keep[$1]!.q, $1) }; for x in r.prefix(2) where keep[next(keep[x]!, 1)] == nil || keep[next(keep[x]!, -1)] == nil { keep[x] = nil } }
}
let pt = nodes(keep)
var seen = Set<String>(); var out = [Edge]()
for k in keep.keys where !seen.contains(k) {
    var st = [k], grp = [String](); seen.insert(k)
    while let q = st.popLast() { grp.append(q); for p in ends(keep[q]!) { for n in pt["\(p.0),\(p.1)"]! where !seen.contains(n) { seen.insert(n); st.append(n) } } }
    let run = grp.contains { let e = keep[$0]!; return keep[next(e, 1)] != nil && keep[next(e, -1)] != nil }
    if grp.count >= 4 && run { out += grp.map { keep[$0]! } }
}
return out
}
let final = clean(all)
// Durance of Hate: white step lines, drawn half a tile higher than the wall base (directions 2 and 3 in the output)
var stepAll = [String: Edge](), stepKept = Set<String>()
if head.contains("DURANCE") {
    hU = Int((20 * S).rounded()); hD = Int((-12 * S).rounded())
    scan(pre[4], OX, OY, 1) { a, b, d, x, y, q in if q > 0.12 { stepAll["\(a),\(b),\(d)"] = Edge(a: a, b: b, d: d, x: x, y: y, q: q) } }
    stepKept = Set(clean(stepAll).map { "\($0.a),\($0.b),\($0.d)" })
    use(prof)
}
// output images
func ctx(_ w: Int, _ h: Int) -> CGContext { let c = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4, space: cs, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!; c.setFillColor(CGColor(red: 0, green: 0, blue: 0, alpha: 1)); c.fill(CGRect(x: 0, y: 0, width: w, height: h)); c.translateBy(x: 0, y: CGFloat(h)); c.scaleBy(x: 1, y: -1); c.setLineCap(.round); return c }
func save(_ c: CGContext, _ p: String) { let d = CGImageDestinationCreateWithURL(URL(fileURLWithPath: p) as CFURL, "public.png" as CFString, 1, nil)!; CGImageDestinationAddImage(d, c.makeImage()!, nil); CGImageDestinationFinalize(d) }
if let outDir = debugDir {
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
}
// all candidate segments with their score; "kept" marks the ones that survive the clean-up
let kept = Set(final.map { "\($0.a),\($0.b),\($0.d)" })
let segs = all.sorted { $0.key < $1.key }.map { (k, e) in "[\(e.a),\(e.b),\(e.d),\(String(format: "%.2f", e.q)),\(kept.contains(k) ? 1 : 0),\(isDoor(e) ? 1 : 0)]" }.joined(separator: ",")
let stepSegs = stepAll.sorted { $0.key < $1.key }.map { (k, e) in ",[\(e.a),\(e.b),\(e.d + 2),\(String(format: "%.2f", e.q)),\(stepKept.contains(k) ? 1 : 0),0]" }.joined()
// player position in tile units (the automap is centred on the player)
let sx = (Double(W) / 2 + 2 * S - OX) / TX, sy = (0.491 * Double(H) - OY) / TY
print("{\"text\":\(textJSON),\"width\":\(W),\"height\":\(H),\"family\":\(fam),\"profile\":\(prof),\"ox\":\(OX),\"oy\":\(OY),\"tx\":\(TX),\"ty\":\(TY),\"player\":[\(String(format: "%.2f", (sx + sy) / 2)),\(String(format: "%.2f", (sy - sx) / 2))],\"segments\":[\(segs.isEmpty ? String(stepSegs.dropFirst()) : segs + stepSegs)]}")
