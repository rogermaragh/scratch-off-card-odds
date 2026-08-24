import SwiftUI

/// Check a ticket against recent draws.
///
/// This is the thing people actually open a lottery app to do. It works
/// entirely on data already downloaded, so it runs offline, and it never
/// claims a win it cannot substantiate: where a state publishes prize tiers
/// the payout is named, and where it doesn't the match is reported plainly
/// with no dollar figure invented.
struct TicketCheckerView: View {
    @EnvironmentObject private var store: LotteryStore
    @Environment(\.dismiss) private var dismiss

    @State private var gameIndex = 0
    @State private var picks: [Int?] = []
    @State private var special: Int?
    @State private var focus = 0          // which tile the keypad fills
    @State private var checked = false

    private var games: [DrawGame] {
        (store.nationalGames + store.stateGames).filter { !$0.draws.isEmpty }
    }

    private var game: DrawGame? {
        games.indices.contains(gameIndex) ? games[gameIndex] : nil
    }

    /// Shape comes from the game's own draws — number counts differ wildly
    /// (Pick 3 draws three, NY Pick 10 draws twenty).
    private var mainCount: Int { game?.draws.first?.numbers.count ?? 5 }
    private var hasSpecial: Bool { game?.draws.first?.special != nil }

    /// Highest number this game draws, inferred from its own history. Pick 3
    /// tops out at 9, Powerball at 69 — without this, tapping 1 then 9 on a
    /// single-digit game silently becomes 19, a number it cannot draw.
    private var maxMain: Int {
        game?.draws.flatMap(\.numbers).max() ?? 99
    }

    private var maxSpecial: Int {
        game?.draws.compactMap(\.special).max() ?? 99
    }

    private var complete: Bool {
        picks.count == mainCount
            && picks.allSatisfy { $0 != nil }
            && (!hasSpecial || special != nil)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    gamePicker
                    entry
                    if checked, let game { results(for: game) }
                    disclaimer
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 28)
            }
            .background(LivingBackground(mood: store.mood))
            .navigationTitle("Check a ticket")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { ThemeToggle() }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .onAppear(perform: reset)
        .onChange(of: gameIndex) { _, _ in reset() }
    }

    // MARK: - Pieces

    private var gamePicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 7) {
                ForEach(Array(games.enumerated()), id: \.offset) { index, g in
                    let selected = index == gameIndex
                    Button { gameIndex = index } label: {
                        Text(g.name.uppercased())
                            .font(.system(size: 11, weight: .medium, design: .monospaced))
                            .kerning(0.8)
                            .foregroundStyle(selected ? Color(.systemBackground) : .secondary)
                            .padding(.horizontal, 11)
                            .padding(.vertical, 7)
                            .background {
                                if selected {
                                    RoundedRectangle(cornerRadius: 3).fill(Color.primary)
                                } else {
                                    RoundedRectangle(cornerRadius: 3)
                                        .strokeBorder(style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                                        .foregroundStyle(.tertiary)
                                }
                            }
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var entry: some View {
        TicketCard(heading: "your numbers",
                   trailing: complete ? "ready" : "\(filledCount)/\(mainCount + (hasSpecial ? 1 : 0))",
                   serial: nil) {
            VStack(alignment: .leading, spacing: 12) {
                DisplayStrip {
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: 42, maximum: 56), spacing: 6)],
                        alignment: .leading, spacing: 6
                    ) {
                        ForEach(0..<mainCount, id: \.self) { index in
                            EntryTile(value: picks.indices.contains(index) ? picks[index] : nil,
                                      active: focus == index,
                                      accent: false)
                                .onTapGesture { focus = index }
                        }
                        if hasSpecial {
                            EntryTile(value: special, active: focus == mainCount, accent: true)
                                .onTapGesture { focus = mainCount }
                        }
                    }
                }

                Keypad(
                    onDigit: append,
                    onDelete: deleteLast,
                    onCheck: complete ? { checked = true } : nil
                )
            }
        }
    }

    private func results(for game: DrawGame) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(game.draws.prefix(6).enumerated()), id: \.offset) { _, draw in
                let hits = matches(draw)
                let specialHit = hasSpecial && special != nil && draw.special == special
                TicketCard(heading: Fmt.drawDate(draw.date),
                           trailing: draw.label ?? "",
                           serial: prizeLine(game: game, hits: hits, specialHit: specialHit)) {
                    VStack(alignment: .leading, spacing: 8) {
                        DisplayStrip {
                            LazyVGrid(
                                columns: [GridItem(.adaptive(minimum: 42, maximum: 56), spacing: 6)],
                                alignment: .leading, spacing: 6
                            ) {
                                ForEach(Array(draw.numbers.enumerated()), id: \.offset) { _, n in
                                    ResultTile(value: n, hit: picks.contains(n))
                                }
                                if let s = draw.special {
                                    ResultTile(value: s, hit: specialHit, accent: true)
                                }
                            }
                        }
                        Text(summary(hits: hits, specialHit: specialHit))
                            .font(.footnote.weight(hits > 0 || specialHit ? .medium : .regular))
                            .foregroundStyle(hits > 0 || specialHit ? .primary : .secondary)
                    }
                }
            }
        }
    }

    private var disclaimer: some View {
        Text("Matches are worked out from published results. This is not a "
             + "claim of winnings — check your ticket with your state lottery "
             + "before doing anything with it.")
            .font(.caption2)
            .foregroundStyle(.tertiary)
            .padding(.top, 2)
    }

    // MARK: - Logic

    private var filledCount: Int {
        picks.compactMap { $0 }.count + (special != nil ? 1 : 0)
    }

    private func matches(_ draw: Draw) -> Int {
        // Duplicate digits matter: Pick 3 can draw 5-5-8, so matching is done
        // by consuming each drawn number once rather than by set intersection.
        var pool = draw.numbers
        var hits = 0
        for pick in picks.compactMap({ $0 }) {
            if let index = pool.firstIndex(of: pick) {
                pool.remove(at: index)
                hits += 1
            }
        }
        return hits
    }

    private func summary(hits: Int, specialHit: Bool) -> String {
        switch (hits, specialHit) {
        case (0, false): return "No match"
        case (0, true): return "\(game?.specialLabel ?? "Special") only"
        case (let n, false): return "\(n) number\(n == 1 ? "" : "s") matched"
        case (let n, true):
            return "\(n) + \(game?.specialLabel ?? "special")"
        }
    }

    /// Only name a prize when the state actually published one for this tier.
    private func prizeLine(game: DrawGame, hits: Int, specialHit: Bool) -> String? {
        guard hits > 0 || specialHit else { return nil }
        guard let payout = store.payout(for: game.id) else {
            return "prize tiers not published for this state"
        }
        let key = specialHit ? "\(hits)+" : "\(hits)"
        let tier = payout.tiers.first {
            let match = $0.match.lowercased()
            return specialHit
                ? match.hasPrefix(key) || (hits == 0 && match.count <= 3 && match.contains(where: \.isLetter))
                : match == key
        }
        guard let tier, let prize = tier.prize else {
            return "no prize at this match level"
        }
        return "\(tier.match) · \(Fmt.money(prize)) in \(store.stateName)"
    }

    private func append(_ digit: Int) {
        checked = false
        let target = focus
        if target < mainCount {
            let current = picks.indices.contains(target) ? picks[target] : nil
            let value = extend(current, with: digit, limit: maxMain)
            if picks.indices.contains(target) { picks[target] = value }
            // Move on once no further digit could fit — on a 1-9 game that is
            // immediately, on a 1-69 game only after a second digit.
            if value * 10 > maxMain { advance() }
        } else {
            special = extend(special, with: digit, limit: maxSpecial)
        }
    }

    /// Append a digit if the result is still a number this game can draw;
    /// otherwise start the tile over with the new digit.
    private func extend(_ current: Int?, with digit: Int, limit: Int) -> Int {
        guard let current, current > 0 else { return digit }
        let combined = current * 10 + digit
        return combined <= limit ? combined : digit
    }

    private func advance() {
        let last = mainCount + (hasSpecial ? 1 : 0) - 1
        if focus < last { focus += 1 }
    }

    private func deleteLast() {
        checked = false
        if focus < mainCount, picks.indices.contains(focus), picks[focus] != nil {
            picks[focus] = nil
        } else if focus == mainCount {
            special = nil
        } else if focus > 0 {
            focus -= 1
            if picks.indices.contains(focus) { picks[focus] = nil }
        }
    }

    private func reset() {
        picks = Array(repeating: nil, count: mainCount)
        special = nil
        focus = 0
        checked = false
    }
}

// MARK: - Small pieces

private struct EntryTile: View {
    let value: Int?
    let active: Bool
    let accent: Bool

    var body: some View {
        Text(value.map { String(format: "%02d", $0) } ?? "––")
            .font(.system(size: 20, weight: .medium, design: .monospaced))
            .foregroundStyle(value == nil ? Color.white.opacity(0.30)
                             : (accent ? .black : .white))
            .frame(minWidth: 42)
            .padding(.vertical, 9)
            .background(
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .fill(value != nil && accent
                          ? Color(red: 0.98, green: 0.78, blue: 0.19)
                          : Color(red: 0.16, green: 0.16, blue: 0.17))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .strokeBorder(Color.white.opacity(active ? 0.75 : 0), lineWidth: 1.5)
            )
            .contentShape(Rectangle())
    }
}

private struct ResultTile: View {
    let value: Int
    let hit: Bool
    var accent: Bool = false

    var body: some View {
        Text(String(format: "%02d", value))
            .font(.system(size: 20, weight: .medium, design: .monospaced))
            .foregroundStyle(hit ? .black : (accent ? .black : .white))
            .frame(minWidth: 42)
            .padding(.vertical, 9)
            .background(
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .fill(hit ? Color(red: 0.33, green: 0.82, blue: 0.50)
                          : (accent ? Color(red: 0.98, green: 0.78, blue: 0.19)
                             : Color(red: 0.16, green: 0.16, blue: 0.17)))
            )
    }
}

/// A keypad in the app's own language rather than the system one — the entry
/// tiles are not text fields, so there is nothing for a system keyboard to
/// attach to.
private struct Keypad: View {
    let onDigit: (Int) -> Void
    let onDelete: () -> Void
    let onCheck: (() -> Void)?

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 6), count: 3)

    var body: some View {
        LazyVGrid(columns: columns, spacing: 6) {
            ForEach(1...9, id: \.self) { digit in
                key(String(digit)) { onDigit(digit) }
            }
            key("⌫", muted: true) { onDelete() }
            key("0") { onDigit(0) }
            Button(action: { onCheck?() }) {
                Text("CHECK")
                    .font(.system(size: 13, weight: .semibold, design: .monospaced))
                    .kerning(0.8)
                    .foregroundStyle(onCheck == nil ? Color.secondary : Color(.systemBackground))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 13)
                    .background(
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .fill(onCheck == nil ? Color.secondary.opacity(0.15) : Color.primary)
                    )
            }
            .buttonStyle(.plain)
            .disabled(onCheck == nil)
        }
    }

    private func key(_ label: String, muted: Bool = false,
                     action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 19, weight: .medium, design: .monospaced))
                .foregroundStyle(muted ? .secondary : .primary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .fill(Color.primary.opacity(0.07))
                )
        }
        .buttonStyle(.plain)
    }
}
