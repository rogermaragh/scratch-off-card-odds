import SwiftUI

struct OddsBoardView: View {
    @EnvironmentObject private var store: LotteryStore
    @State private var sort: Sort = .value
    @State private var priceFilter: Double?

    enum Sort: String, CaseIterable, Identifiable {
        case value = "Value left"
        case topPrize = "Top prize"
        case price = "Price"

        var id: String { rawValue }
    }

    private var games: [Scratcher] {
        var list = store.scratchers
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
        Array(Set(store.scratchers.compactMap(\.price))).sorted()
    }

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 8) {
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
            .padding(.horizontal, 16)
            .padding(.bottom, 24)
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("Scratch-offs")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 2) {
            TypeStrip(
                options: Sort.allCases.map { .init(value: $0, title: $0.rawValue) },
                selection: $sort
            )

            ValueStrip(
                label: "PRICE",
                options: [(value: nil, title: "All")]
                    + prices.map { (value: Optional($0), title: Fmt.money($0)) },
                selection: $priceFilter
            )

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
                    Text(Fmt.money(game.price))
                    Text("·")
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
