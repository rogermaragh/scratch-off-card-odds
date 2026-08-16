import Foundation

enum Config {
    /// Where the published `lottery.json` lives.
    ///
    /// Empty means "no remote configured": the app runs entirely on the copy
    /// bundled at build time and never touches the network. Point this at the
    /// object-store URL the scraper workflow publishes to.
    static let defaultDataURL = ""

    /// A debug override so a build can be aimed at a staging URL without a
    /// code change (`defaults write` on the simulator, or a settings toggle).
    static let overrideKey = "dataURLOverride"

    static var dataURL: URL? {
        let raw = UserDefaults.standard.string(forKey: overrideKey) ?? defaultDataURL
        guard !raw.isEmpty else { return nil }
        return URL(string: raw)
    }

    static var hasRemote: Bool { dataURL != nil }
}
