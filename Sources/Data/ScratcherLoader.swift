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
    private var loadedCode: String?

    func load(state code: String) async {
        guard loadedCode != code else { return }
        loadedCode = code
        phase = .loading

        if let local = bundled(code) {
            phase = .loaded(local.scratchers)
            return
        }
        guard let base = Config.dataURL else {
            phase = .unavailable
            return
        }

        let url = base
            .appendingPathComponent("scratchers")
            .appendingPathComponent("\(code).json")
        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            if let http = response as? HTTPURLResponse {
                guard http.statusCode != 404 else {
                    phase = .unavailable
                    return
                }
                guard (200..<300).contains(http.statusCode) else {
                    throw URLError(.badServerResponse)
                }
            }
            let decoded = try JSONDecoder().decode(ScratcherFile.self, from: data)
            phase = .loaded(decoded.scratchers)
        } catch {
            // A failed fetch is recoverable; let the next visit try again.
            loadedCode = nil
            phase = .failed(error.localizedDescription)
        }
    }

    private func bundled(_ code: String) -> ScratcherFile? {
        guard let url = Foundation.Bundle.main.url(forResource: code, withExtension: "json"),
              let data = try? Data(contentsOf: url)
        else { return nil }
        return try? JSONDecoder().decode(ScratcherFile.self, from: data)
    }
}
