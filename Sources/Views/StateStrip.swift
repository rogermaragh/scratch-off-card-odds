import SwiftUI

/// A punch-card row of state codes: the current one is punched through, the
/// rest are dashed outlines waiting to be selected.
///
/// It keeps the states someone actually switches between one tap away, instead
/// of behind a modal picker. The full list is still there at the end.
struct StateStrip: View {
    @EnvironmentObject private var store: LotteryStore
    @Binding var showingPicker: Bool

    /// Jurisdictions whose games are local rather than national. Millionaire
    /// for Life runs in 31 states, so a simple "has a states list" test would
    /// flood the strip; a genuinely in-state game runs in a handful.
    private var localGameStates: Set<String> {
        Set((store.core?.drawGames ?? [])
            .compactMap { $0.states }
            .filter { $0.count <= 5 }
            .flatMap { $0 })
    }

    /// States worth surfacing: those with scratch-off data or in-state games,
    /// plus wherever the user currently is.
    ///
    /// New York keeps its five in-state games in the national list scoped to
    /// NY, not under states["NY"].drawGames — checking only the latter left the
    /// best-covered state out of the switcher entirely.
    private var featured: [(code: String, name: String, scratchers: Int)] {
        let local = localGameStates
        let interesting = store.allStates.filter {
            $0.scratchers > 0
                || local.contains($0.code)
                || (store.core?.states[$0.code]?.drawGames?.isEmpty == false)
        }
        if interesting.contains(where: { $0.code == store.stateCode }) {
            return interesting
        }
        return store.allStates.filter { $0.code == store.stateCode } + interesting
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 7) {
                    ForEach(featured, id: \.code) { state in
                        chip(for: state.code)
                            .id(state.code)
                    }
                    Button { showingPicker = true } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "ellipsis")
                            Text("ALL")
                        }
                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                        .kerning(0.8)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .overlay(
                            RoundedRectangle(cornerRadius: 3)
                                .strokeBorder(style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                                .foregroundStyle(.tertiary)
                        )
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 2)
            }
            .onAppear { proxy.scrollTo(store.stateCode, anchor: .center) }
            .onChange(of: store.stateCode) { _, code in
                withAnimation(.snappy) { proxy.scrollTo(code, anchor: .center) }
            }
        }
    }

    private func chip(for code: String) -> some View {
        let selected = code == store.stateCode
        return Button {
            withAnimation(.snappy(duration: 0.2)) { store.stateCode = code }
        } label: {
            Text(code)
                .font(.system(size: 11, weight: .medium, design: .monospaced))
                .kerning(1.0)
                .foregroundStyle(selected ? Color(.systemBackground) : .secondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
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
