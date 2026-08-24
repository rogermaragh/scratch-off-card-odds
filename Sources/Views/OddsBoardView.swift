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
        .background(Color(.systemGroupedBackground))
        .navigationTitle("Scratch-offs")
        .navigationBarTitleDisplayMode(.inline)
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

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(game.name)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(1)
                    .foregroundStyle(.primary)

                HStack(spacing: 6) {
                    if game.price != nil {
                        Text(Fmt.money(game.price))
                        Text("·")
                    }
                    Text("\(game.topPrizesRemaining ?? 0) top left")
                    if let pct = game.pctPrizesRemaining {
                        Text("·")
                        Text("\(String(format: "%.0f", pct))% prizes left")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)

                if game.endingSoon == true {
                    Text("Ending — low stock, estimate less reliable")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                }
            }

            Spacer(minLength: 8)

            VStack(alignment: .trailing, spacing: 3) {
                RatioBadge(ratio: game.ratio, muted: game.endingSoon == true)
                Text(Fmt.money(game.topPrize, compact: true))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground),
                    in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}
