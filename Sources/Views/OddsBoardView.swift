import SwiftUI

struct OddsBoardView: View {
    @EnvironmentObject private var store: LotteryStore
    @StateObject private var loader = ScratcherLoader()
    @State private var sort: Sort = .value
    @State private var priceFilter: Double?

    enum Sort: String, CaseIterable, Identifiable {
        case value = "Value left"
        case topPrize = "Top prize"
        case price = "Price"

        var id: String { rawValue }
    }

    private var loaded: [Scratcher] {
        if case .loaded(let games) = loader.phase { return games }
        return []
    }

    private var games: [Scratcher] {
        var list = loaded
        if let priceFilter {
            list = list.filter { $0.price == priceFilter }
        }
        switch sort {
        case .value:
            return list.sorted { ($0.ratio ?? 0) > ($1.ratio ?? 0) }
        case .topPrize:
            return list.sorted { ($0.topPrize ?? 0) > ($1.topPrize ?? 0) }
        case .price:
            return list.sorted { ($0.price ?? 0) > ($1.price ?? 0) }
        }
    }

    private var prices: [Double] {
        Array(Set(loaded.compactMap(\.price))).sorted()
    }

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 8) {
                switch loader.phase {
                case .idle, .loading:
                    loading
                case .unavailable:
                    unavailable
                case .failed(let message):
                    failure(message)
                case .loaded:
                    header
                    ForEach(games) { game in
                        NavigationLink {
                            ScratcherDetailView(game: game)
                        } label: {
                            ScratcherRow(game: game)
                        }
                        .shimmer((game.ratio ?? 0) >= 1.10 && game.endingSoon != true)
                        .buttonStyle(.plain)
                    }
                    if games.isEmpty {
                        Text("No games match this filter.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .padding(.top, 32)
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 24)
        }
        .background(LivingBackground(mood: store.mood))
        .navigationTitle("Scratch-offs")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) { ThemeToggle() }
        }
        .task(id: store.stateCode) {
            await loader.load(state: store.stateCode)
        }
    }

    private var loading: some View {
        VStack(spacing: 10) {
            ProgressView()
            Text("Loading \(store.stateName) games")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding(.top, 60)
    }

    private var unavailable: some View {
        SectionCard {
            Text("Not available for \(store.stateName)")
                .font(.headline)
            Text("""
                 This state's lottery doesn't publish the prize counts needed to \
                 rank games — or an adapter hasn't been written for it yet. Draw \
                 results still work everywhere.
                 """)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .padding(.top, 6)
        }
        .padding(.top, 24)
    }

    private func failure(_ message: String) -> some View {
        SectionCard {
            Text("Couldn't load games")
                .font(.headline)
            Text(message)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .padding(.top, 6)
        }
        .padding(.top, 24)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 2) {
            TypeStrip(
                options: Sort.allCases.map { .init(value: $0, title: $0.rawValue) },
                selection: $sort
            )

            if !prices.isEmpty {
                ValueStrip(
                    label: "PRICE",
                    options: [(value: nil, title: "All")]
                        + prices.map { (value: Optional($0), title: Fmt.money($0)) },
                    selection: $priceFilter
                )
            }

            Text(sort == .value
                 ? "Prize money left per ticket, against how the game started. Above 1.00× is paying better than at launch."
                 : "Showing \(games.count) active games.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.top, 6)
        }
        .padding(.top, 4)
        .padding(.bottom, 10)
    }
}

private struct ScratcherRow: View {
    let game: Scratcher

    private var ratioText: String {
        game.ratio.map { String(format: "%.2f", $0) } ?? "—"
    }

    /// Above 1.00x the game is paying better than it did at launch; the tile
    /// colour says so before the number is read.
    private var tileColor: Color {
        guard let ratio = game.ratio, game.endingSoon != true else {
            return Color(red: 0.16, green: 0.16, blue: 0.17)
        }
        if ratio >= 1.05 { return Color(red: 0.18, green: 0.62, blue: 0.36) }
        if ratio >= 0.98 { return Color(red: 0.98, green: 0.78, blue: 0.19) }
        return Color(red: 0.16, green: 0.16, blue: 0.17)
    }

    private var tileText: Color {
        guard let ratio = game.ratio, game.endingSoon != true else { return .white }
        return ratio >= 1.05 ? .white : (ratio >= 0.98 ? .black : .white)
    }

    private var footer: String {
        var parts = ["\(game.topPrizesRemaining ?? 0) top left"]
        if let pct = game.pctPrizesRemaining {
            parts.append("\(String(format: "%.0f", pct))% prizes left")
        }
        if game.endingSoon == true { parts.append("ending") }
        return parts.joined(separator: "   ·   ")
    }

    var body: some View {
        TicketCard(heading: game.name,
                   trailing: game.price != nil ? Fmt.money(game.price) : "",
                   serial: footer) {
            DisplayStrip {
                HStack(alignment: .center, spacing: 12) {
                    Text(ratioText)
                        .font(.system(size: 26, weight: .medium, design: .monospaced))
                        .foregroundStyle(tileText)
                        .padding(.vertical, 7)
                        .padding(.horizontal, 10)
                        .background(
                            RoundedRectangle(cornerRadius: 5, style: .continuous)
                                .fill(tileColor)
                        )

                    VStack(alignment: .leading, spacing: 3) {
                        Text("VALUE LEFT")
                            .font(.system(size: 9, weight: .medium, design: .monospaced))
                            .kerning(1.4)
                            .foregroundStyle(Color.white.opacity(0.45))
                        Text(Fmt.money(game.topPrize, compact: true) + " TOP PRIZE")
                            .font(.system(size: 11, weight: .medium, design: .monospaced))
                            .kerning(0.8)
                            .foregroundStyle(Color.white.opacity(0.8))
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Color.white.opacity(0.35))
                }
            }
        }
    }
}
