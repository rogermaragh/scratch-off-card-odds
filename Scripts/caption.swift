#!/usr/bin/env swift
//
// Composites App Store caption frames as lottery ticket stubs: a serial-number
// kicker, a headline and sub-caption, a perforated tear line, and the device
// screenshot below it.
//
// Reads a TSV manifest on stdin, one frame per line:
//   inPath <TAB> outPath <TAB> kicker <TAB> headline <TAB> subcaption
//
// Bare screenshots convert poorly on the App Store — most people decide from
// the caption at thumbnail size, so the text has to carry the frame. The stub
// is the app's own metaphor: every result in it is drawn as a ticket, and a
// listing that looks like the product is easier to recognise on return.

import AppKit
import Foundation

/// The frame follows the screenshot rather than the other way round.
///
/// A light screenshot inside the dark stub reads as glare — a bright slab
/// dropped into a black tile — where every other frame reads as one object.
/// Rather than carry a flag in the manifest that can be set wrong, each frame
/// asks its own screenshot how bright it is.
struct Palette {
    let page: NSColor
    let stub: NSColor
    let accent: NSColor
    let hair: NSColor
    let headline: NSColor
    let sub: NSColor
    let edge: NSColor

    static let dark = Palette(
        page: NSColor(srgbRed: 0.039, green: 0.039, blue: 0.043, alpha: 1),
        stub: NSColor(srgbRed: 0.078, green: 0.078, blue: 0.082, alpha: 1),
        accent: NSColor(srgbRed: 0.961, green: 0.773, blue: 0.094, alpha: 1),
        hair: NSColor(white: 0.24, alpha: 1),
        headline: .white,
        sub: NSColor(white: 0.62, alpha: 1),
        edge: NSColor(white: 0.20, alpha: 1))

    // Paper rather than plain white, and a darker gold, because the bright
    // yellow that carries on black is illegible on it.
    static let light = Palette(
        page: NSColor(srgbRed: 0.937, green: 0.933, blue: 0.914, alpha: 1),
        stub: NSColor(srgbRed: 0.969, green: 0.965, blue: 0.949, alpha: 1),
        accent: NSColor(srgbRed: 0.541, green: 0.427, blue: 0.035, alpha: 1),
        hair: NSColor(white: 0.78, alpha: 1),
        headline: NSColor(srgbRed: 0.078, green: 0.078, blue: 0.059, alpha: 1),
        sub: NSColor(white: 0.38, alpha: 1),
        edge: NSColor(white: 0.84, alpha: 1))
}

/// Mean luminance of the screenshot, sampled on a coarse grid — enough to tell
/// a light screen from a dark one, and far cheaper than reading every pixel.
func isLight(_ rep: NSBitmapImageRep) -> Bool {
    let step = max(1, min(rep.pixelsWide, rep.pixelsHigh) / 40)
    var total = 0.0, count = 0.0
    for x in stride(from: 0, to: rep.pixelsWide, by: step) {
        for y in stride(from: 0, to: rep.pixelsHigh, by: step) {
            guard let colour = rep.colorAt(x: x, y: y) else { continue }
            total += Double(colour.brightnessComponent)
            count += 1
        }
    }
    return count > 0 && total / count > 0.5
}

func render(input: String, output: String,
            kicker: String, headline: String, sub: String) -> Bool {
    guard let source = NSImage(contentsOfFile: input),
          let sourceRep = NSBitmapImageRep(data: source.tiffRepresentation!) else {
        FileHandle.standardError.write("cannot read \(input)\n".data(using: .utf8)!)
        return false
    }
    let W = CGFloat(sourceRep.pixelsWide)
    let H = CGFloat(sourceRep.pixelsHigh)
    let isPad = W > 1600
    let palette = isLight(sourceRep) ? Palette.light : Palette.dark

    guard let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: Int(W), pixelsHigh: Int(H),
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return false }
    rep.size = NSSize(width: W, height: H)
    guard let ctx = NSGraphicsContext(bitmapImageRep: rep) else { return false }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = ctx

    palette.page.setFill()
    NSRect(x: 0, y: 0, width: W, height: H).fill()

    let side = W * 0.072
    let textWidth = W - side * 2
    let kickerSize = isPad ? W * 0.016 : W * 0.020
    let headlineSize = isPad ? W * 0.052 : W * 0.064
    let subSize = isPad ? W * 0.024 : W * 0.030

    let centered = NSMutableParagraphStyle()
    centered.alignment = .center
    centered.lineBreakMode = .byWordWrapping

    // Monospace for the kicker, matching the serial line the app prints on
    // every ticket.
    let kickerString = NSAttributedString(string: kicker.uppercased(), attributes: [
        .font: NSFont.monospacedSystemFont(ofSize: kickerSize, weight: .medium),
        .foregroundColor: palette.accent,
        .paragraphStyle: centered,
        .kern: kickerSize * 0.18,
    ])
    let headlineString = NSAttributedString(string: headline, attributes: [
        .font: NSFont.systemFont(ofSize: headlineSize, weight: .bold),
        .foregroundColor: palette.headline,
        .paragraphStyle: centered,
        .kern: -headlineSize * 0.02,
    ])
    let subString = NSAttributedString(string: sub, attributes: [
        .font: NSFont.systemFont(ofSize: subSize, weight: .regular),
        .foregroundColor: palette.sub,
        .paragraphStyle: centered,
    ])

    let bounds = NSSize(width: textWidth, height: .greatestFiniteMagnitude)
    func height(_ s: NSAttributedString) -> CGFloat {
        s.boundingRect(with: bounds, options: .usesLineFragmentOrigin).height
    }
    let kickerH = height(kickerString)
    let headlineH = height(headlineString)
    let subH = height(subString)

    let topInset = H * 0.040
    let gapAfterKicker = H * 0.011
    let gapAfterHeadline = H * 0.009
    let stubBottom = H - (topInset + kickerH + gapAfterKicker
                          + headlineH + gapAfterHeadline + subH + H * 0.030)

    // The stub panel, then the tear line across its foot.
    palette.stub.setFill()
    NSRect(x: 0, y: stubBottom, width: W, height: H - stubBottom).fill()

    var y = H - topInset - kickerH
    kickerString.draw(with: NSRect(x: side, y: y, width: textWidth, height: kickerH),
                      options: .usesLineFragmentOrigin)
    y -= gapAfterKicker + headlineH
    headlineString.draw(with: NSRect(x: side, y: y, width: textWidth, height: headlineH),
                        options: .usesLineFragmentOrigin)
    y -= gapAfterHeadline + subH
    subString.draw(with: NSRect(x: side, y: y, width: textWidth, height: subH),
                   options: .usesLineFragmentOrigin)

    // Perforation: a dashed rule with a notch bitten out of each edge, which is
    // what actually reads as "tear here" rather than "hairline divider".
    let dash = NSBezierPath()
    dash.move(to: NSPoint(x: side * 0.5, y: stubBottom))
    dash.line(to: NSPoint(x: W - side * 0.5, y: stubBottom))
    dash.lineWidth = max(2, W * 0.0022)
    dash.setLineDash([W * 0.012, W * 0.010], count: 2, phase: 0)
    palette.hair.setStroke()
    dash.stroke()

    let notch = W * 0.026
    palette.page.setFill()
    for centre in [CGFloat(0), W] {
        NSBezierPath(ovalIn: NSRect(x: centre - notch, y: stubBottom - notch,
                                    width: notch * 2, height: notch * 2)).fill()
    }

    // Device screenshot, filling what the stub left.
    let shotTop = stubBottom - H * 0.030
    let bottomMargin = H * 0.020
    let available = shotTop - bottomMargin
    let maxWidth = W * (isPad ? 0.82 : 0.845)
    var shotWidth = maxWidth
    var shotHeight = shotWidth * (H / W)
    if shotHeight > available {
        shotHeight = available
        shotWidth = shotHeight * (W / H)
    }
    let shotRect = NSRect(x: (W - shotWidth) / 2, y: shotTop - shotHeight,
                          width: shotWidth, height: shotHeight)
    let radius = shotWidth * 0.055

    // A hairline instead of a drop shadow: the frame is nearly black, so a
    // shadow is invisible and only an edge separates screenshot from page.
    NSGraphicsContext.saveGraphicsState()
    let frame = NSBezierPath(roundedRect: shotRect, xRadius: radius, yRadius: radius)
    frame.addClip()
    source.draw(in: shotRect, from: NSRect(x: 0, y: 0, width: W, height: H),
                operation: .sourceOver, fraction: 1)
    NSGraphicsContext.restoreGraphicsState()

    palette.edge.setStroke()
    frame.lineWidth = max(1, W * 0.0015)
    frame.stroke()

    NSGraphicsContext.restoreGraphicsState()

    guard let data = rep.representation(using: .png, properties: [:]) else { return false }
    do {
        try data.write(to: URL(fileURLWithPath: output))
        return true
    } catch {
        FileHandle.standardError.write("write failed \(output): \(error)\n".data(using: .utf8)!)
        return false
    }
}

var processed = 0
while let line = readLine(strippingNewline: true) {
    guard !line.isEmpty else { continue }
    let parts = line.components(separatedBy: "\t")
    guard parts.count == 5 else {
        FileHandle.standardError.write("bad manifest line: \(line)\n".data(using: .utf8)!)
        continue
    }
    if render(input: parts[0], output: parts[1], kicker: parts[2],
              headline: parts[3], sub: parts[4]) {
        processed += 1
        print("✓ \(URL(fileURLWithPath: parts[1]).lastPathComponent)")
    }
}
print("\(processed) frames")
