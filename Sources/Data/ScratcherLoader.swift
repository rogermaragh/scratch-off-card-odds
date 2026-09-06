import Foundation
import Combine

/// Loads one state's scratch-off inventory, on demand.
///
/// These files are the large, slow part of the data and only exist for states
/// with an adapter, so they are deliberately kept out of the core payload. A
/// state ships its file inside the app when available and otherwise fetches it
/// from the configured base URL, which is what lets coverage grow without
/// shipping a new build.
@MainActor
final class ScratcherLoader: ObservableObject {
    enum Phase {
        case idle
        case loading
        case loaded([Scratcher])
        case unavailable
        case failed(String)
    }

    @Published private(set) var phase: Phase = .idle

    /// When these prize counts were read from the state, which is not when the
    /// app last published. Draw games refresh twice a day and scratch-off
    /// inventories once, so a single "updated" date across both would say the
    /// prizes are hours fresher than they are.
    @Published private(set) var scrapedAt: String?
    private var loadedCode: String?

    /// Loads one state's scratch-off inventory: what is on hand first, then
    /// what the publisher has this morning.
    ///
    /// The bundled file is a photograph of the state taken when the build was
    /// made, and remaining prize counts fall every day as people claim. Showing
    /// it and stopping there -- which is what this did -- froze the ranking at
    /// build time for exactly the nineteen states that have data, while the
    /// draw results beside it refreshed twice a day. That combination is worse
    /// than either alone: the app said "updated today" over week-old prizes.
    ///
    /// So the local copy still goes up immediately, because it renders with no
    /// wait and works with no signal, and the download replaces it when it
    /// turns out to be newer.
    func load(state code: String) async {
        guard loadedCode != code else { return }
        loadedCode = code
        phase = .loading

        // Whichever of the two local copies is newer. After an app update the
        // build can be ahead of a download from months ago, so this is not
        // simply "cache first".
        let onHand = [cached(code), bundled(code)]
            .compactMap { $0 }
            .max { ($0.generatedAt ?? "") < ($1.generatedAt ?? "") }

        if let onHand {
            scrapedAt = onHand.generatedAt
            phase = .loaded(onHand.scratchers)
        }

        // A screenshot run must show the same numbers every time it runs.
        guard let base = Config.dataURL, !Screenshot.isActive else {
            if onHand == nil { phase = .unavailable }
            return
        }

        let url = base
            .appendingPathComponent("scratchers")
            .appendingPathComponent("\(code).json")
        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse {
                // No file for this state is an answer rather than a failure --
                // unless something is already on screen, which stays.
                guard http.statusCode != 404 else {
                    if onHand == nil { phase = .unavailable }
                    return
                }
                guard (200..<300).contains(http.statusCode) else {
                    throw URLError(.badServerResponse)
                }
            }
            let decoded = try JSONDecoder().decode(ScratcherFile.self, from: data)

            // Decoded before it is trusted, and taken only if it is genuinely
            // newer. A half-failed publish can serve a file older than the one
            // in the build, and going backwards is worse than not refreshing.
            guard isNewer(decoded, than: onHand) else { return }

            if let destination = cacheURL(for: code) {
                try? data.write(to: destination, options: .atomic)
            }
            scrapedAt = decoded.generatedAt
            phase = .loaded(decoded.scratchers)
        } catch {
            // Let the next visit try again either way. With prizes already on
            // screen the failure stays silent, the way a failed background
            // refresh does elsewhere -- a phone with no signal is not an error
            // worth interrupting someone over.
            loadedCode = nil
            if onHand == nil { phase = .failed(error.localizedDescription) }
        }
    }

    /// Timestamps are ISO-8601 in a fixed UTC form, so string order is time
    /// order and this needs no date parsing.
    private func isNewer(_ fresh: ScratcherFile, than existing: ScratcherFile?) -> Bool {
        guard let existing else { return true }
        guard let new = fresh.generatedAt, let old = existing.generatedAt else { return true }
        return new > old
    }

    private func cacheURL(for code: String) -> URL? {
        guard let directory = try? FileManager.default
            .url(for: .applicationSupportDirectory, in: .userDomainMask,
                 appropriateFor: nil, create: true)
            .appendingPathComponent("scratchers", isDirectory: true)
        else { return nil }
        try? FileManager.default.createDirectory(at: directory,
                                                 withIntermediateDirectories: true)
        return directory.appendingPathComponent("\(code).json")
    }

    private func cached(_ code: String) -> ScratcherFile? {
        guard let url = cacheURL(for: code), let data = try? Data(contentsOf: url)
        else { return nil }
        return try? JSONDecoder().decode(ScratcherFile.self, from: data)
    }

    private func bundled(_ code: String) -> ScratcherFile? {
        guard let url = Foundation.Bundle.main.url(forResource: code, withExtension: "json"),
              let data = try? Data(contentsOf: url)
        else { return nil }
        return try? JSONDecoder().decode(ScratcherFile.self, from: data)
    }
}
