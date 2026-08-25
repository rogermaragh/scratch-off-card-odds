import SwiftUI

/// A ticket-shaped card: perforated notches on the sides, a dashed tear line,
/// and a monospaced serial footer.
///
/// The frame follows the system theme so it sits in a light or dark app, while
/// the numbers inside sit on a permanently dark display strip — the way a real
/// scoreboard reads regardless of the room.
struct TicketCard<Content: View>: View {
    let heading: String
    let trailing: String
    var serial: String?
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(heading.uppercased())
                    .kerning(1.6)
                Spacer()
                Text(trailing.uppercased())
                    .kerning(1.0)
                    .foregroundStyle(.secondary)
            }
            .font(.system(size: 10, weight: .medium, design: .monospaced))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 16)
            .padding(.top, 14)
            .padding(.bottom, 12)

            content
                .padding(.horizontal, 16)

            if let serial {
                TearLine()
                    .padding(.top, 14)
                Text(serial.uppercased())
                    .font(.system(size: 10, weight: .regular, design: .monospaced))
                    .kerning(1.2)
                    .foregroundStyle(.tertiary)
                    .padding(.horizontal, 16)
                    .padding(.top, 9)
                    .padding(.bottom, 13)
            } else {
                Color.clear.frame(height: 14)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background {
            ZStack {
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(Color(.secondarySystemGroupedBackground))
                // White on near-white leans entirely on a shadow for its edge,
                // which survives on a screen and disappears in a screenshot.
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .strokeBorder(Color.primary.opacity(0.07), lineWidth: 1)
                // Notches punched out of both edges, like a torn stub.
                HStack {
                    Notch().offset(x: -7)
                    Spacer()
                    Notch().offset(x: 7)
                }
            }
        }
    }
}

private struct Notch: View {
    var body: some View {
        Circle()
            .fill(Color(.systemGroupedBackground))
            .frame(width: 14, height: 14)
    }
}

private struct TearLine: View {
    var body: some View {
        Rectangle()
            .fill(Color.primary.opacity(0.22))
            .frame(height: 1)
            .mask(
                HStack(spacing: 3) {
                    ForEach(0..<60, id: \.self) { _ in
                        Rectangle().frame(width: 4)
                    }
                }
            )
    }
}

/// The dark strip the numbers sit on.
struct DisplayStrip<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(.vertical, 12)
            .padding(.horizontal, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color(red: 0.08, green: 0.08, blue: 0.09))
            )
    }
}

/// One drawn number, as a split-flap tile.
///
/// The flip is what makes a refresh feel like a draw rather than a table
/// reload: tiles turn over in sequence instead of all at once.
struct FlipTile: View {
    let value: Int
    var accent: Bool = false
    var index: Int = 0
    /// Explicit width when the row is sizing tiles to fit; nil lets the tile
    /// size itself inside a wrapping grid.
    var width: CGFloat? = nil

    @State private var shown: Int = 0
    @State private var flipping = false

    private var text: String { String(format: "%02d", shown) }

    var body: some View {
        Text(text)
            .font(.system(size: 22, weight: .medium, design: .monospaced))
            .foregroundStyle(accent ? Color.black : Color.white)
            .frame(width: width, height: 40)
            .frame(minWidth: width == nil ? 34 : nil)
            .background(
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .fill(accent ? Color(red: 0.98, green: 0.78, blue: 0.19)
                                 : Color(red: 0.16, green: 0.16, blue: 0.17))
            )
            .rotation3DEffect(.degrees(flipping ? -90 : 0),
                              axis: (x: 1, y: 0, z: 0),
                              anchor: .center,
                              perspective: 0.6)
            .onAppear { animate(to: value) }
            .onChange(of: value) { _, new in animate(to: new) }
    }

    private func animate(to new: Int) {
        guard shown != new else {
            shown = new
            return
        }
        // Stagger by position so the row reads left to right.
        let delay = Double(index) * 0.07
        withAnimation(.easeIn(duration: 0.13).delay(delay)) { flipping = true }
        DispatchQueue.main.asyncAfter(deadline: .now() + delay + 0.13) {
            shown = new
            withAnimation(.easeOut(duration: 0.16)) { flipping = false }
        }
    }
}

/// A row of flip tiles sized to fit.
///
/// Horizontal scrolling was the obvious fix for a row that overflows, but it
/// hides part of the draw — and the numbers are the entire point. Instead the
/// tiles shrink to fit the width, down to a floor where they stop being
/// legible; only past that does the row wrap. So a 7-ball game (NY Lotto) fits
/// one line, and Pick 10's twenty numbers still wrap rather than shrink to
/// nothing.
struct FlipRow: View {
    let numbers: [Int]
    let special: Int?

    private let spacing: CGFloat = 6
    private let maxWidth: CGFloat = 48
    private let minWidth: CGFloat = 34

    private var count: Int { numbers.count + (special == nil ? 0 : 1) }

    var body: some View {
        GeometryReader { geo in
            let fitted = (geo.size.width - spacing * CGFloat(count - 1)) / CGFloat(count)
            let width = min(maxWidth, fitted)

            Group {
                if width >= minWidth {
                    HStack(spacing: spacing) { tiles(width: width) }
                } else {
                    // Too many to fit legibly: wrap instead of shrinking further.
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: minWidth, maximum: maxWidth),
                                           spacing: spacing)],
                        alignment: .leading,
                        spacing: spacing
                    ) { tiles(width: nil) }
                }
            }
            .frame(width: geo.size.width, alignment: .leading)
        }
        .frame(height: rowHeight)
    }

    /// Height has to be declared because GeometryReader fills its parent.
    private var rowHeight: CGFloat {
        let perRow = max(1, Int((360 + spacing) / (minWidth + spacing)))
        let rows = Int(ceil(Double(count) / Double(perRow)))
        return CGFloat(rows) * 40 + CGFloat(max(0, rows - 1)) * spacing
    }

    @ViewBuilder
    private func tiles(width: CGFloat?) -> some View {
        ForEach(Array(numbers.enumerated()), id: \.offset) { index, n in
            FlipTile(value: n, index: index, width: width)
        }
        if let special {
            FlipTile(value: special, accent: true, index: numbers.count, width: width)
        }
    }
}
