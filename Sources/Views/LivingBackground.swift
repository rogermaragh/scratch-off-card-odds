import SwiftUI

/// How well the selected state is currently paying. Drives the app's colour.
enum Mood {
    case none      // no scratch-off data for this state
    case cool      // nothing paying above its launch value
    case warm      // something at or just above 1.00x
    case hot       // something well above 1.00x

    init(bestRatio: Double?) {
        guard let bestRatio else { self = .none; return }
        if bestRatio >= 1.15 { self = .hot }
        else if bestRatio >= 1.0 { self = .warm }
        else { self = .cool }
    }

    /// Blob palette. Kept low-saturation: this sits behind content, and the
    /// tickets have to stay the loudest thing on screen.
    var palette: [Color] {
        switch self {
        case .hot:
            return [Color(red: 0.33, green: 0.78, blue: 0.55),
                    Color(red: 0.98, green: 0.82, blue: 0.35),
                    Color(red: 0.40, green: 0.70, blue: 0.90)]
        case .warm:
            return [Color(red: 0.98, green: 0.82, blue: 0.42),
                    Color(red: 0.94, green: 0.66, blue: 0.48),
                    Color(red: 0.60, green: 0.72, blue: 0.92)]
        case .cool:
            return [Color(red: 0.56, green: 0.62, blue: 0.88),
                    Color(red: 0.50, green: 0.74, blue: 0.84),
                    Color(red: 0.72, green: 0.66, blue: 0.88)]
        case .none:
            return [Color(red: 0.62, green: 0.63, blue: 0.68),
                    Color(red: 0.68, green: 0.68, blue: 0.72),
                    Color(red: 0.58, green: 0.60, blue: 0.66)]
        }
    }

    var caption: String? {
        switch self {
        case .hot: return "something's paying well here"
        case .warm: return nil
        case .cool: return nil
        case .none: return nil
        }
    }
}

/// Slowly drifting colour blobs behind the whole app.
///
/// The palette comes from the data, so the motion and the colour are one
/// system rather than decoration stacked on top of a tint: a state with a game
/// paying well runs green and gold, a state with nothing hot runs grey.
struct LivingBackground: View {
    let mood: Mood
    /// Respect Reduce Motion: the colour still changes, the drift stops.
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack {
            Color(.systemGroupedBackground)

            TimelineView(.animation(minimumInterval: 1.0 / 20.0, paused: reduceMotion)) { timeline in
                Canvas { context, size in
                    let t = timeline.date.timeIntervalSinceReferenceDate
                    let colors = mood.palette
                    context.addFilter(.blur(radius: 60))
                    for (index, color) in colors.enumerated() {
                        let phase = Double(index) * 2.1
                        // Slow, irrational-ish periods so the loop never
                        // visibly repeats.
                        let x = 0.5 + 0.42 * sin(t / (23 + Double(index) * 7) + phase)
                        let y = 0.35 + 0.40 * cos(t / (31 + Double(index) * 5) + phase)
                        let r = size.width * (0.42 + 0.06 * sin(t / 17 + phase))
                        let rect = CGRect(x: x * size.width - r / 2,
                                          y: y * size.height - r / 2,
                                          width: r, height: r)
                        context.fill(Path(ellipseIn: rect), with: .color(color))
                    }
                }
                .opacity(0.45)
            }
            .allowsHitTesting(false)
        }
        .ignoresSafeArea()
        .animation(.easeInOut(duration: 0.9), value: mood.palette.count)
    }
}

/// A light sweep travelling across a view, like foil catching the light.
///
/// Applied only to games paying above their launch value, so it stays a signal
/// rather than ambient sparkle.
struct Shimmer: ViewModifier {
    var active: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var phase: CGFloat = -1

    func body(content: Content) -> some View {
        content.overlay {
            if active && !reduceMotion {
                GeometryReader { geo in
                    let width = geo.size.width
                    // Soft-edged so it reads as light catching foil rather
                    // than a grey bar sliding past.
                    Rectangle()
                        .fill(
                            LinearGradient(
                                colors: [.white.opacity(0), .white.opacity(0.13),
                                         .white.opacity(0)],
                                startPoint: .leading, endPoint: .trailing
                            )
                        )
                        .frame(width: 70)
                        .blur(radius: 6)
                        .rotationEffect(.degrees(18))
                        .offset(x: phase * (width + 90))
                        .blendMode(.plusLighter)
                        .onAppear {
                            withAnimation(.linear(duration: 2.6)
                                .repeatForever(autoreverses: false)
                                .delay(Double.random(in: 0...1.4))) {
                                phase = 1.2
                            }
                        }
                }
                .allowsHitTesting(false)
            }
        }
        .clipped()
    }
}

extension View {
    func shimmer(_ active: Bool) -> some View {
        modifier(Shimmer(active: active))
    }
}
