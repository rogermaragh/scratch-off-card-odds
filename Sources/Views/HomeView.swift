import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var store: LotteryStore
    @StateObject private var locator = StateLocator()
    @State private var showingStatePicker = false
    @State private var showingChecker = false
    @State private var showingScratchers = false

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

                    if store.needsLocation, locator.status == .locating {
                        HStack(spacing: 8) {
                            ProgressView().controlSize(.small)
                            Text("finding your state")
                                .font(.system(size: 11, weight: .medium,
                                              design: .monospaced))
                                .kerning(1.2)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.bottom, 2)
                    }

                    StateStrip(showingPicker: $showingStatePicker)
                        .padding(.horizontal, -16)
                        .padding(.bottom, 2)

                    ForEach(store.nationalGames) { game in
                        DrawGameCard(game: game)
                    }

                    ForEach(store.stateGames) { game in
                        DrawGameCard(game: game)
                    }

                    if store.stateGames.isEmpty {
                        localGamesNote
                    }

                    checkTicketLink
                    scratchOffLink
                    footer
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
            }
            .refreshable { await store.refresh() }
            .task {
                // First launch only: pick up where the user actually is rather
                // than defaulting to a state they have no connection to.
                guard store.needsLocation else { return }
                locator.detect { code in store.adopt(detected: code) }
            }
            .onChange(of: locator.status) { _, status in
                // Denied or failed is a fine outcome -- the picker still works.
                switch status {
                case .denied, .failed:
                    store.skipLocation()
                default:
                    break
                }
            }
            .background(LivingBackground(mood: store.mood))
            .navigationTitle(store.stateName)
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    ThemeToggle()
                }
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
            .sheet(isPresented: $showingChecker) {
                TicketCheckerView()
            }
            .navigationDestination(isPresented: $showingScratchers) {
                OddsBoardView()
            }
            // Screenshot runs open a screen by launch argument rather than by
            // simulated taps, so a set is reproducible and a mistimed tap
            // cannot quietly shoot the wrong screen.
            .task {
                switch Screenshot.screen {
                // The detail screen is pushed from the board, so the board has
                // to open first -- asking for the detail alone left the app on
                // the home screen wearing the detail screen's caption.
                case .scratchers, .scratcherDetail: showingScratchers = true
                case .checker: showingChecker = true
                case .statePicker: showingStatePicker = true
                case .home, .none: break
                }
            }
        }
    }

    private var checkTicketLink: some View {
        Button { showingChecker = true } label: {
            SectionCard {
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Check a ticket")
                            .font(.headline)
                            .foregroundStyle(.primary)
                        Text("Match your numbers against recent draws")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .buttonStyle(.plain)
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

    /// Most states run their own daily games. Showing only the multi-state ones
    /// with no comment reads as "this is everything", which is wrong — Florida
    /// sells ten games and we cover two of them.
    private var localGamesNote: some View {
        SectionCard {
            Text("\(store.stateName)'s own games aren't here yet")
                .font(.subheadline.weight(.medium))
            Text("Most states also run daily games — Pick 3, Fantasy 5 and the like. "
                 + "Those need a separate source per state, and only a few are wired "
                 + "up so far. The multi-state games above are complete.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.top, 5)
        }
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

    private var serial: String? {
        guard let first = latest.first else { return nil }
        // A stub serial derived from the draw itself, so it stays put between
        // launches. The date is already in the header, so it isn't repeated;
        // the stub footer carries the disclaimer instead.
        // Swift seeds hashValue per process, so it differs every launch. A
        // stub serial that changes while you look at it is worse than none.
        let seed = game.id.unicodeScalars.reduce(0) { ($0 &* 31 &+ Int($1.value)) % 9000 }
        return "no. \(seed + 1000)-\(first.numbers.count)   ·   unofficial"
    }

    /// What the highlighted tile is, and any multiplier, on one line.
    ///
    /// The accent tile alone says "this number is different" without saying
    /// how: a Virginia player sees a highlighted 05 on a Pick 4 card with no
    /// hint that it is the Fireball rather than a fifth digit. Every game that
    /// draws an extra ball names it, so name it here.
    private func caption(for draw: Draw) -> String? {
        var parts: [String] = []
        if let special = draw.special, let label = game.specialLabel {
            parts.append(String(format: "%02d ", special) + label.uppercased())
        }
        if let multiplier = draw.multiplier, !multiplier.isEmpty {
            parts.append("\(multiplier)× MULTIPLIER")
        }
        return parts.isEmpty ? nil : parts.joined(separator: "   ·   ")
    }

    var body: some View {
        TicketCard(heading: game.name,
                   trailing: latest.first.map { Fmt.drawDate($0.date) } ?? "",
                   serial: serial) {
            if latest.isEmpty {
                Text("No draws available")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(latest.enumerated()), id: \.offset) { index, draw in
                        DisplayStrip {
                            VStack(alignment: .leading, spacing: 7) {
                                if let label = draw.label {
                                    Text(label.uppercased())
                                        .font(.system(size: 9, weight: .medium,
                                                      design: .monospaced))
                                        .kerning(1.4)
                                        .foregroundStyle(Color.white.opacity(0.45))
                                }
                                FlipRow(numbers: draw.numbers, special: draw.special)
                                if let caption = caption(for: draw) {
                                    Text(caption)
                                        .font(.system(size: 9, weight: .medium,
                                                      design: .monospaced))
                                        .kerning(1.2)
                                        .foregroundStyle(Color.white.opacity(0.45))
                                }
                            }
                        }
                        .id(index)
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
