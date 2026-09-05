import Foundation

enum Config {
    /// Where the published `core.json` lives.
    ///
    /// The scrape workflow already publishes to GitHub Pages on a schedule;
    /// this is the address the app reads it from. Until it is filled in, a
    /// released build shows whatever was bundled at build time *forever* —
    /// which for an app whose entire product is "what were the winning
    /// numbers" is the worst failure it has.
    ///
    /// Replace the marked segment with the real Pages host:
    ///
    ///     Scripts/set_data_url.py https://<user>.github.io/<repo>/core.json
    ///
    /// The placeholder is deliberately a live-looking URL rather than an empty
    /// string, so the plumbing around it is exercised and visible. It is
    /// treated as unset, because a build that ships this address would
    /// otherwise spend every launch retrying a host that does not exist.
    static let defaultDataURL = "https://REPLACE-ME.github.io/scratchoffcardodds/core.json"

    /// The segment that marks the URL above as not yet configured.
    static let placeholder = "REPLACE-ME"

    /// A debug override so a build can be aimed at a staging URL without a
    /// code change (`defaults write` on the simulator, or a settings toggle).
    static let overrideKey = "dataURLOverride"

    static var dataURL: URL? {
        let raw = UserDefaults.standard.string(forKey: overrideKey) ?? defaultDataURL
        guard !raw.isEmpty, !raw.contains(placeholder) else { return nil }
        return URL(string: raw)
    }

    static var hasRemote: Bool { dataURL != nil }

    /// True when the app was built without anywhere to refresh from.
    ///
    /// Surfaced in the UI rather than kept as a developer detail: a build that
    /// cannot update has to say so, because the alternative is showing a
    /// three-week-old draw as though it were last night's.
    static var isUnconfigured: Bool {
        (UserDefaults.standard.string(forKey: overrideKey) ?? defaultDataURL)
            .contains(placeholder)
    }
}
