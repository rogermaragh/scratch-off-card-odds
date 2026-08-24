import SwiftUI
import Combine

/// App-wide appearance, reachable from every screen.
///
/// Three states rather than two: "system" is the default and the one most
/// people want, but an explicit choice has to stick — including when it
/// matches the system, so it doesn't silently flip at sunset.
@MainActor
final class Theme: ObservableObject {
    enum Choice: String, CaseIterable {
        case system, light, dark

        var scheme: ColorScheme? {
            switch self {
            case .system: return nil
            case .light: return .light
            case .dark: return .dark
            }
        }

        var symbol: String {
            switch self {
            case .system: return "circle.lefthalf.filled"
            case .light: return "sun.max.fill"
            case .dark: return "moon.fill"
            }
        }

        var label: String {
            switch self {
            case .system: return "Match system appearance"
            case .light: return "Light appearance"
            case .dark: return "Dark appearance"
            }
        }

        var next: Choice {
            switch self {
            case .system: return .light
            case .light: return .dark
            case .dark: return .system
            }
        }
    }

    private static let key = "appearanceChoice"

    @Published var choice: Choice {
        didSet { UserDefaults.standard.set(choice.rawValue, forKey: Self.key) }
    }

    init() {
        let saved = UserDefaults.standard.string(forKey: Self.key) ?? ""
        choice = Choice(rawValue: saved) ?? .system
    }

    func advance() {
        withAnimation(.snappy(duration: 0.28)) { choice = choice.next }
    }
}

/// The toggle itself: a punched chip matching the state strip, cycling
/// system → light → dark. It sits in the same place on every screen so it is
/// always where you left it.
struct ThemeToggle: View {
    @EnvironmentObject private var theme: Theme

    var body: some View {
        Button(action: theme.advance) {
            Image(systemName: theme.choice.symbol)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.primary)
                .frame(width: 30, height: 30)
                .background {
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(.ultraThinMaterial)
                }
                .overlay {
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .strokeBorder(Color.primary.opacity(0.12), lineWidth: 1)
                }
                .contentTransition(.symbolEffect(.replace))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(theme.choice.label)
        .accessibilityHint("Cycles system, light and dark")
    }
}
