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
    private var lastRefreshAttempt: Date?

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

    /// How long to leave it before trying again on foreground.
    ///
    /// Draws land a few times a day at most, so refetching on every switch
    /// back into the app would spend a phone's battery and someone's data plan
    /// to learn nothing. Fifteen minutes is far more often than the numbers
    /// change and far less often than people reopen an app.
    private static let minimumRefreshInterval: TimeInterval = 15 * 60

    /// Refresh on launch and on returning to the app, quietly.
    ///
    /// Separate from `refresh()` because the two want opposite things from a
    /// failure. Someone who pulled to refresh is owed an answer; a background
    /// attempt that fails is usually just a phone with no signal, and saying
    /// so unprompted turns a working offline app into a broken-looking one.
    /// The cached data stays on screen either way, and the staleness banner
    /// already says how old it is.
    func refreshOnOpen() async {
        guard Config.hasRemote, !Screenshot.isActive else { return }
        if case .loading = refreshState { return }
        if let last = lastRefreshAttempt,
           Date().timeIntervalSince(last) < Self.minimumRefreshInterval { return }
        await refresh(automatic: true)
    }

    func refresh(automatic: Bool = false) async {
        guard let base = Config.dataURL else { return }
        lastRefreshAttempt = Date()
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
            refreshState = automatic ? .idle : .failed(error.localizedDescription)
        }
    }

    // MARK: - Derived

    /// Every jurisdiction, alphabetically. All are selectable: draw results
    /// exist everywhere even where scratch-off data doesn't.
    /// One row of the state list.
    ///
    /// Named rather than a tuple because three views spell the type out, and a
    /// bare tuple makes adding a field a compile error in each of them.
    struct StateRow: Identifiable {
        let code: String
        let name: String
        let scratchers: Int
        let localGames: Int
        var id: String { code }
    }

    var allStates: [StateRow] {
        (core?.states ?? [:])
            .map { StateRow(code: $0.key, name: $0.value.name,
                            scratchers: $0.value.scratcherCount,
                            localGames: ($0.value.drawGames ?? []).count) }
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

    /// How many days old the bundled or downloaded data is.
    var dataAgeInDays: Int? {
        guard let raw = core?.generatedAt,
              let date = ISO8601DateFormatter().date(from: raw) else { return nil }
        return Calendar.current.dateComponents([.day], from: date, to: Date()).day
    }

    /// What to say about the data's age, if anything.
    ///
    /// Most draw games run daily, so anything past a couple of days has
    /// certainly missed results. The app is careful never to show a stale draw
    /// as current in the scraper; saying nothing here would let the same thing
    /// happen one layer up, where none of those guards reach.
    enum Freshness { case fine, ageing, stale }

    var freshness: Freshness {
        guard let days = dataAgeInDays else { return .fine }
        if days >= 7 { return .stale }
        if days >= 3 { return .ageing }
        return .fine
    }

    var stalenessMessage: String? {
        // Not in the App Store set. The frames are shot from whatever was last
        // scraped, which is always a few days behind by the time they are
        // taken -- so the banner would appear in every screenshot and describe
        // the shoot rather than the app. A released build with its data URL
        // filled in refreshes on launch and rarely shows this at all.
        guard !Screenshot.isActive else { return nil }
        guard let days = dataAgeInDays, freshness != .fine else { return nil }
        let age = days == 1 ? "1 day" : "\(days) days"
        if Config.isUnconfigured {
            // No point telling someone to pull to refresh when the build has
            // nowhere to refresh from.
            return "These results are \(age) old. This build has no update "
                 + "source, so check your state lottery for tonight's numbers."
        }
        return "These results are \(age) old. Pull down to refresh."
    }

    var sourceDescription: String {
        switch (source, Config.hasRemote) {
        case (.bundled, false): return "Bundled with the app"
        case (.bundled, true): return "Bundled — pull to refresh"
        case (.downloaded, _): return "Downloaded"
        }
    }
}
