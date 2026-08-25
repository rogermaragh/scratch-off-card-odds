import Foundation
import Combine

/// Owns the core data and which state the user is viewing.
///
/// The core file is small and ships with the app, so the first screen is
/// instant and works offline in every jurisdiction. Scratch-off inventories are
/// large and only exist for some states, so they load on demand — see
/// `ScratcherLoader`.
@MainActor
final class LotteryStore: ObservableObject {
    enum Source: Equatable {
        case bundled
        case downloaded(Date)
    }

    enum RefreshState: Equatable {
        case idle
        case loading
        case failed(String)
    }

    @Published private(set) var core: Core?
    @Published private(set) var loadError: String?
    @Published private(set) var source: Source = .bundled
    @Published private(set) var refreshState: RefreshState = .idle

    @Published var stateCode: String {
        didSet { UserDefaults.standard.set(stateCode, forKey: Self.stateKey) }
    }

    private static let stateKey = "selectedStateCode"

    private var cacheURL: URL? {
        try? FileManager.default.url(for: .applicationSupportDirectory,
                                     in: .userDomainMask,
                                     appropriateFor: nil,
                                     create: true)
            .appendingPathComponent("core.json")
    }

    /// True until the user (or geolocation) has actually picked a state, so
    /// the first launch can detect where they are instead of guessing.
    @Published private(set) var needsLocation: Bool

    init() {
        let saved = UserDefaults.standard.string(forKey: Self.stateKey)
        // A pinned state also suppresses the location prompt: a screenshot run
        // must not depend on where the machine taking it happens to be.
        let pinned = Screenshot.state
        needsLocation = pinned == nil && saved == nil
        stateCode = pinned ?? saved ?? "NC"
        loadFromDisk()
    }

    /// Adopt a detected state, if it is one we carry.
    @discardableResult
    func adopt(detected code: String) -> Bool {
        guard core?.states[code] != nil else {
            needsLocation = false
            return false
        }
        stateCode = code
        needsLocation = false
        return true
    }

    func skipLocation() { needsLocation = false }

    // MARK: - Loading

    private func loadFromDisk() {
        if let cacheURL,
           let data = try? Data(contentsOf: cacheURL),
           let decoded = try? JSONDecoder().decode(Core.self, from: data) {
            let modified = (try? cacheURL.resourceValues(forKeys: [.contentModificationDateKey]))?
                .contentModificationDate ?? Date()
            apply(decoded, source: .downloaded(modified))
            return
        }

        guard let url = Foundation.Bundle.main.url(forResource: "core", withExtension: "json")
        else {
            loadError = "core.json is missing from the app bundle."
            return
        }
        do {
            let data = try Data(contentsOf: url)
            apply(try JSONDecoder().decode(Core.self, from: data), source: .bundled)
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func apply(_ decoded: Core, source: Source) {
        core = decoded
        self.source = source
        loadError = nil
        if decoded.states[stateCode] == nil, let first = allStates.first {
            stateCode = first.code
        }
    }

    // MARK: - Refresh

    func refresh() async {
        guard let base = Config.dataURL else { return }
        refreshState = .loading
        do {
            var request = URLRequest(url: base.appendingPathComponent("core.json"))
            request.cachePolicy = .reloadIgnoringLocalCacheData
            let (data, response) = try await URLSession.shared.data(for: request)

            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                throw URLError(.badServerResponse)
            }

            // Decode before overwriting the cache so a broken publish can never
            // replace a good local copy.
            let decoded = try JSONDecoder().decode(Core.self, from: data)
            if let cacheURL { try? data.write(to: cacheURL, options: .atomic) }
            apply(decoded, source: .downloaded(Date()))
            refreshState = .idle
        } catch {
            refreshState = .failed(error.localizedDescription)
        }
    }

    // MARK: - Derived

    /// Every jurisdiction, alphabetically. All are selectable: draw results
    /// exist everywhere even where scratch-off data doesn't.
    var allStates: [(code: String, name: String, scratchers: Int)] {
        (core?.states ?? [:])
            .map { (code: $0.key, name: $0.value.name, scratchers: $0.value.scratcherCount) }
            .sorted { $0.name < $1.name }
    }

    var currentState: StateSummary? { core?.states[stateCode] }

    var stateName: String { currentState?.name ?? stateCode }

    /// Draw games available in the selected state, national ones first.
    var nationalGames: [DrawGame] {
        (core?.drawGames ?? []).filter { $0.sold(in: stateCode) }
    }

    /// In-state games for the selected state, where they've been scraped.
    var stateGames: [DrawGame] { currentState?.drawGames ?? [] }

    var scratcherCount: Int { currentState?.scratcherCount ?? 0 }

    var hasScratchers: Bool { scratcherCount > 0 }

    /// Drives the ambient colour: how well this state's best game is paying.
    var mood: Mood { Mood(bestRatio: currentState?.bestRatio) }

    func payout(for gameID: String) -> Payout? {
        currentState?.payouts?[gameID]
    }

    var lastUpdated: String {
        guard let raw = core?.generatedAt else { return "unknown" }
        guard let date = ISO8601DateFormatter().date(from: raw) else { return raw }
        let out = DateFormatter()
        out.dateFormat = "MMM d, h:mm a"
        return out.string(from: date)
    }

    var sourceDescription: String {
        switch (source, Config.hasRemote) {
        case (.bundled, false): return "Bundled with the app"
        case (.bundled, true): return "Bundled — pull to refresh"
        case (.downloaded, _): return "Downloaded"
        }
    }
}
