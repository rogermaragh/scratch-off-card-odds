import SwiftUI

struct ScratcherDetailView: View {
    let game: Scratcher

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                summary
                prizeTable
                methodology
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 24)
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle(game.name)
        .navigationBarTitleDisplayMode(.inline)
    }

    private var summary: some View {
        SectionCard {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(Fmt.money(game.topPrize))
                        .font(.title2.weight(.semibold))
                    Text("top prize · \(game.topPrizesRemaining ?? 0) remaining")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                RatioBadge(ratio: game.ratio, muted: game.endingSoon == true)
            }
            .padding(.bottom, 14)

            HStack(spacing: 0) {
                StatPair(label: "Ticket", value: Fmt.money(game.price))
                StatPair(label: "Odds", value: game.overallOdds.map { "1 in \(String(format: "%.2f", $0))" } ?? "—")
                StatPair(label: "Return", value: game.returnPct.map { "\(String(format: "%.0f", $0))%" } ?? "—")
            }
            .padding(.bottom, 12)

            HStack(spacing: 0) {
                StatPair(label: "Prizes left",
                         value: game.pctPrizesRemaining.map { "\(String(format: "%.1f", $0))%" } ?? "—")
                StatPair(label: "Tickets left",
                         value: game.ticketsRemaining.map { Fmt.count($0) } ?? "—")
                StatPair(label: "Printed",
                         value: game.ticketsPrinted.map { Fmt.count($0) } ?? "—")
            }

            if game.endingSoon == true {
                Text("This game is nearly sold out. With little inventory left the estimate swings hard on a single claim.")
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .padding(.top, 12)
            }
        }
    }

    private var prizeTable: some View {
        SectionCard {
            Text("Prizes")
                .font(.headline)
                .padding(.bottom, 10)

            HStack {
                Text("Prize").frame(maxWidth: .infinity, alignment: .leading)
                Text("Left").frame(width: 60, alignment: .trailing)
                Text("Of").frame(width: 60, alignment: .trailing)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            .padding(.bottom, 4)

            ForEach(game.tiers) { tier in
                Divider()
                HStack {
                    Text(Fmt.money(tier.value))
                        .font(.subheadline)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Text(Fmt.count(tier.remaining))
                        .font(.subheadline.weight(.medium))
                        .monospacedDigit()
                        .frame(width: 60, alignment: .trailing)
                    Text(Fmt.count(tier.total))
                        .font(.subheadline)
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                        .frame(width: 60, alignment: .trailing)
                }
                .padding(.vertical, 7)
            }
        }
    }

    private var methodology: some View {
        SectionCard {
            Text("How this is calculated")
                .font(.subheadline.weight(.medium))
                .padding(.bottom, 6)
            Text("""
                 Tickets printed comes from the published odds at each prize \
                 tier. Tickets remaining assumes they sell in proportion to \
                 prizes claimed, which is an estimate, not a count the lottery \
                 publishes. Return is the prize money still unclaimed divided \
                 across the tickets thought to be left.
                 """)
                .font(.caption)
                .foregroundStyle(.secondary)

            if let url = game.url, let link = URL(string: url) {
                Link("Official game page", destination: link)
                    .font(.caption)
                    .padding(.top, 10)
            }
        }
    }
}
