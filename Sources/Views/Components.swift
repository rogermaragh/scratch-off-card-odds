import SwiftUI

/// A drawn number. `accent` marks the Powerball / Mega Ball.
struct NumberBall: View {
    let value: Int
    var accent: Bool = false

    var body: some View {
        Text(String(format: "%02d", value))
            .font(.system(.callout, design: .rounded).weight(.medium))
            .monospacedDigit()
            .foregroundStyle(accent ? Color.white : Color.primary)
            .frame(width: 36, height: 36)
            .background {
                if accent {
                    Circle().fill(Color.accentColor)
                } else {
                    Circle().strokeBorder(Color.primary.opacity(0.18), lineWidth: 1)
                }
            }
    }
}

struct BallRow: View {
    let numbers: [Int]
    let special: Int?

    // Twenty-number games (NY Pick 10) overflow any single row, so the balls
    // flow onto as many rows as they need.
    private let columns = [GridItem(.adaptive(minimum: 36, maximum: 36), spacing: 6)]

    var body: some View {
        LazyVGrid(columns: columns, alignment: .leading, spacing: 6) {
            ForEach(Array(numbers.enumerated()), id: \.offset) { _, n in
                NumberBall(value: n)
            }
            if let special {
                NumberBall(value: special, accent: true)
            }
        }
    }
}

/// The value-remaining badge: above 1.00x the game is paying better than it
/// started, below 1.00x the good prizes have already been claimed.
struct RatioBadge: View {
    let ratio: Double?
    var muted: Bool = false

    private var tint: Color {
        guard let ratio, !muted else { return .secondary }
        if ratio >= 1.05 { return .green }
        if ratio >= 0.95 { return .orange }
        return .secondary
    }

    var body: some View {
        Text(ratio.map { String(format: "%.2f×", $0) } ?? "—")
            .font(.footnote.weight(.medium))
            .monospacedDigit()
            .foregroundStyle(tint)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(tint.opacity(0.12), in: Capsule())
    }
}

struct SectionCard<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0) { content }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemGroupedBackground),
                        in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

struct StatPair: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.subheadline.weight(.medium))
                .monospacedDigit()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
