import Foundation

/// Launch arguments that drive the app straight to a screen.
///
/// The App Store set has to be reshot whenever the design moves, and doing it
/// by tapping through the simulator is neither repeatable nor reviewable: a
/// mistimed tap lands on the wrong state, and nobody notices until the frames
/// are side by side. Every shot here is addressed by argument instead, so a
/// run is deterministic and a re-shoot months later produces the same frames.
///
/// Everything is read through UserDefaults, which already folds `-key value`
/// launch arguments over the stored domain. That means these override the
/// user's own settings for the life of the process without writing to them.
///
///     xcrun simctl launch <udid> com.ticketwise.app \
///         -shotState VA -shotScreen scratchers -shotTheme dark
///
enum Screenshot {
    private static func string(_ key: String) -> String? {
        guard let value = UserDefaults.standard.string(forKey: key),
              !value.isEmpty else { return nil }
        return value
    }

    /// Which screen to open on launch.
    enum Screen: String {
        case home, scratchers, checker, statePicker, scratcherDetail
    }

    static var screen: Screen? {
        string("shotScreen").flatMap(Screen.init(rawValue:))
    }

    /// The state to show, whatever was last selected or geolocated.
    static var state: String? { string("shotState")?.uppercased() }

    /// Pins light or dark. Left alone, a set shot across a sunset would
    /// disagree with itself halfway through.
    static var theme: String? { string("shotTheme") }

    /// The intro animation is worth one frame and in the way of every other,
    /// so it is skipped unless a shot explicitly asks for it.
    static var showsIntro: Bool {
        UserDefaults.standard.bool(forKey: "shotIntro")
    }

    /// Ticket-checker picks, so the "you matched 4" frame shows a real result
    /// rather than an empty keypad. Comma-separated: `-shotPicks 13,31,54`.
    static var picks: [Int]? {
        string("shotPicks").map { raw in
            raw.split(separator: ",").compactMap { Int($0.trimmingCharacters(
                in: .whitespaces)) }
        }
    }

    /// Any launch argument at all puts the app in screenshot mode.
    static var isActive: Bool {
        screen != nil || state != nil || theme != nil || showsIntro
    }
}
