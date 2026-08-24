import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var store: LotteryStore
    @State private var showingStatePicker = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    if let error = store.loadError {
                        SectionCard {
                            Text("Couldn't load data")
                                .font(.headline)
                            Text(error)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                                .padding(.top, 4)
                        }
                    }

                    ForEach(store.nationalGames) { game in
                        DrawGameCard(game: game)
                    }

                    ForEach(store.stateGames) { game in
                        DrawGameCard(game: game)
                    }

                    scratchOffLink
                    footer
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
            }
            .refreshable { await store.refresh() }
            .background(Color(.systemGroupedBackground))
            .navigationTitle(store.stateName)
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                if Config.hasRemote {
                    ToolbarItem(placement: .topBarLeading) {
                        Button {
                            Task { await store.refresh() }
                        } label: {
                            if store.refreshState == .loading {
                                ProgressView()
                            } else {
                                Label("Refresh", systemImage: "arrow.clockwise")
                            }
                        }
                        .disabled(store.refreshState == .loading)
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showingStatePicker = true
                    } label: {
                        Label("Change state", systemImage: "mappin.and.ellipse")
                    }
                }
            }
            .sheet(isPresented: $showingStatePicker) {
                StatePickerView()
            }
        }
    }

    private var scratchOffLink: some View {
        NavigationLink {
            OddsBoardView()
        } label: {
            SectionCard {
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Scratch-offs")
                            .font(.headline)
                            .foregroundStyle(store.hasScratchers ? .primary : .secondary)
                        Text(store.hasScratchers
                             ? "\(store.scratcherCount) games ranked by value left"
                             : "No prize data published for this state")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    if store.hasScratchers {
                        Image(systemName: "chevron.right")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(.tertiary)
                    }
                }
            }
        }
        .buttonStyle(.plain)
        .disabled(!store.hasScratchers)
    }

    private var footer: some View {
        VStack(spacing: 4) {
            if case .failed(let message) = store.refreshState {
                Text("Refresh failed: \(message)")
                    .foregroundStyle(.orange)
            }
            Text("Updated \(store.lastUpdated) · \(store.sourceDescription)")
            Text("Unofficial. Always verify with your state lottery.")
        }
        .font(.caption2)
        .foregroundStyle(.tertiary)
        .multilineTextAlignment(.center)
        .padding(.top, 8)
    }
}

private struct DrawGameCard: View {
    @EnvironmentObject private var store: LotteryStore
    let game: DrawGame

    private var latest: [Draw] { game.latestDraws }

    var body: some View {
        SectionCard {
            HStack(alignment: .firstTextBaseline) {
                Text(game.name)
                    .font(.headline)
                Spacer()
                if let first = latest.first {
                    Text(Fmt.drawDate(first.date))
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.bottom, 12)

            if latest.isEmpty {
                Text("No draws available")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(latest.enumerated()), id: \.offset) { index, draw in
                    if index > 0 { Divider().padding(.vertical, 10) }

                    if let label = draw.label {
                        Text(label)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(.bottom, 6)
                    }
                    BallRow(numbers: draw.numbers, special: draw.special)

                    if let multiplier = draw.multiplier, !multiplier.isEmpty {
                        Text("\(multiplier)× multiplier")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(.top, 8)
                    }
                }

                // Winner counts are scraped from the state's own site, which can
                // post a newer draw than the numbers feed has published. Only
                // show them when they demonstrably describe the draw on screen.
                if let payout = store.payout(for: game.id),
                   let shownDate = latest.first?.date,
                   payout.drawDate == shownDate {
                    WinnerSummary(payout: payout, stateName: store.stateName)
                        .padding(.top, 12)
                }
            }
        }
    }
}

/// Winner counts, when the selected state publishes them.
private struct WinnerSummary: View {
    let payout: Payout
    let stateName: String
    @State private var expanded = false

    private var jackpotWinners: Int { payout.tiers.first?.winners ?? 0 }
    private var totalWinners: Int { payout.tiers.reduce(0) { $0 + $1.winners } }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Divider().padding(.bottom, 10)

            Button {
                withAnimation(.snappy) { expanded.toggle() }
            } label: {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(jackpotWinners > 0
                             ? "\(jackpotWinners) jackpot winner\(jackpotWinners == 1 ? "" : "s")"
                             : "No jackpot winner")
                            .font(.footnote)
                            .foregroundStyle(.primary)
                        Text("\(Fmt.count(totalWinners)) winners in \(stateName)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.tertiary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.plain)

            if expanded {
                VStack(spacing: 0) {
                    ForEach(payout.tiers) { tier in
                        HStack {
                            Text(tier.match)
                                .font(.caption.weight(.medium))
                                .frame(width: 46, alignment: .leading)
                            Text(Fmt.money(tier.prize, compact: true))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(Fmt.count(tier.winners))
                                .font(.caption)
                                .monospacedDigit()
                        }
                        .padding(.vertical, 5)
                    }
                }
                .padding(.top, 8)
            }
        }
    }
}
