import Foundation
import Combine

/// Owns the lottery data and which state the user is viewing.
///
/// Data resolves newest-first: a previously downloaded copy on disk wins over
/// the copy bundled at build time, so the app opens instantly and offline
/// either way, then refreshes in the background when a remote is configured.
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

    @Published private(set) var bundle: Bundle?
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
            .appendingPathComponent("lottery.json")
    }

    init() {
        stateCode = UserDefaults.standard.string(forKey: Self.stateKey) ?? "NC"
        loadFromDisk()
    }

    // MARK: - Loading

    private func loadFromDisk() {
        if let cacheURL,
           let data = try? Data(contentsOf: cacheURL),
           let decoded = try? JSONDecoder().decode(Bundle.self, from: data) {
            let modified = (try? cacheURL.resourceValues(forKeys: [.contentModificationDateKey]))?
                .contentModificationDate ?? Date()
            apply(decoded, source: .downloaded(modified))
            return
        }

        guard let url = Foundation.Bundle.main.url(forResource: "lottery", withExtension: "json")
        else {
            loadError = "lottery.json is missing from the app bundle."
            return
        }
        do {
            let data = try Data(contentsOf: url)
            apply(try JSONDecoder().decode(Bundle.self, from: data), source: .bundled)
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func apply(_ decoded: Bundle, source: Source) {
        bundle = decoded
        self.source = source
        loadError = nil
        if decoded.states[stateCode] == nil, let first = availableStates.first {
            stateCode = first.code
        }
    }

    // MARK: - Refresh

    func refresh() async {
        guard let url = Config.dataURL else { return }
        refreshState = .loading
        do {
            var request = URLRequest(url: url)
            request.cachePolicy = .reloadIgnoringLocalCacheData
            let (data, response) = try await URLSession.shared.data(for: request)

            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                throw URLError(.badServerResponse)
            }

            // Decode before overwriting the cache so a broken publish can never
            // replace a good local copy.
            let decoded = try JSONDecoder().decode(Bundle.self, from: data)
            if let cacheURL { try? data.write(to: cacheURL, options: .atomic) }
            apply(decoded, source: .downloaded(Date()))
            refreshState = .idle
        } catch {
            refreshState = .failed(error.localizedDescription)
        }
    }

    // MARK: - Derived

    var availableStates: [(code: String, name: String)] {
        (bundle?.states ?? [:])
            .map { (code: $0.key, name: $0.value.name) }
            .sorted { $0.name < $1.name }
    }

    var currentState: StateData? { bundle?.states[stateCode] }

    var stateName: String { currentState?.name ?? stateCode }

    var drawGames: [DrawGame] { bundle?.drawGames ?? [] }

    /// In-state games for the selected state, e.g. Pick 3 and Pick 4.
    var stateDrawGames: [DrawGame] { currentState?.drawGames ?? [] }

    var scratchers: [Scratcher] {
        (currentState?.scratchers ?? []).sorted { ($0.ratio ?? 0) > ($1.ratio ?? 0) }
    }

    func payout(for gameID: String) -> Payout? {
        currentState?.payouts?[gameID]
    }

    var hasScratchers: Bool { !(currentState?.scratchers.isEmpty ?? true) }

    /// When the data itself was scraped, not when it was downloaded.
    var lastUpdated: String {
        guard let raw = bundle?.generatedAt else { return "unknown" }
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
