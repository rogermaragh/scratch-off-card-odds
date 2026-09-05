import SwiftUI

/// Root: the launch sequence plays over the real app, which is already loading
/// underneath. The animation never delays data — it only covers the moment.
struct RootView: View {
    @EnvironmentObject private var store: LotteryStore
    // The intro is worth one frame and in the way of every other.
    @State private var showingLaunch = !Screenshot.isActive || Screenshot.showsIntro

    var body: some View {
        ZStack {
            HomeView()

            if showingLaunch {
                LaunchView(numbers: launchNumbers) {
                    withAnimation(.easeInOut(duration: 0.45)) { showingLaunch = false }
                }
                .transition(.opacity)
                .zIndex(1)
            }
        }
    }

    /// The sequence settles on a real draw — today's Powerball if we have it —
    /// so the intro is showing something true rather than decorative digits.
    private var launchNumbers: [Int] {
        let draw = store.core?.drawGames.first?.draws.first
        let numbers = draw.map { $0.numbers + [$0.special].compactMap { $0 } } ?? []
        return numbers.isEmpty ? [7, 11, 21, 33, 45, 9] : Array(numbers.prefix(6))
    }
}

/// A ticket printing itself: tiles spin through digits, land one by one, and
/// the stub tears away.
struct LaunchView: View {
    let numbers: [Int]
    let finished: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var landed = 0
    @State private var lift = false
    @State private var wordmarkIn = false

    var body: some View {
        ZStack {
            LivingBackground(mood: .warm)

            VStack(spacing: 20) {
                Spacer()

                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        // Twice the length of the name this replaced, so the
                        // letter-spacing comes down and the line is allowed to
                        // shrink rather than truncate. A wordmark that ends in
                        // "..." is worse than a slightly tighter one.
                        Text("SCRATCH OFF CARD ODDS")
                            .kerning(1.4)
                            .lineLimit(1)
                            .minimumScaleFactor(0.75)
                        Spacer(minLength: 8)
                        Text("DRAWING")
                            .kerning(1.4)
                            .foregroundStyle(.secondary)
                            .layoutPriority(-1)
                    }
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 16)
                    .padding(.top, 14)
                    .padding(.bottom, 12)

                    DisplayStrip {
                        HStack(spacing: 6) {
                            ForEach(Array(numbers.enumerated()), id: \.offset) { index, value in
                                SpinTile(value: value,
                                         settled: index < landed,
                                         accent: index == numbers.count - 1)
                            }
                        }
                    }
                    .padding(.horizontal, 16)

                    Rectangle()
                        .fill(Color.primary.opacity(0.22))
                        .frame(height: 1)
                        .mask(HStack(spacing: 3) {
                            ForEach(0..<60, id: \.self) { _ in Rectangle().frame(width: 4) }
                        })
                        .padding(.top, 14)

                    Text("every state · unofficial")
                        .font(.system(size: 10, weight: .regular, design: .monospaced))
                        .kerning(1.2)
                        .foregroundStyle(.tertiary)
                        .padding(.horizontal, 16)
                        .padding(.top, 9)
                        .padding(.bottom, 13)
                }
                .background {
                    ZStack {
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .fill(Color(.secondarySystemGroupedBackground))
                        HStack {
                            Circle().fill(Color(.systemGroupedBackground))
                                .frame(width: 14, height: 14).offset(x: -7)
                            Spacer()
                            Circle().fill(Color(.systemGroupedBackground))
                                .frame(width: 14, height: 14).offset(x: 7)
                        }
                    }
                }
                .padding(.horizontal, 28)
                .scaleEffect(wordmarkIn ? 1 : 0.94)
                .opacity(wordmarkIn ? 1 : 0)
                .offset(y: lift ? -34 : 0)

                Spacer()
            }
        }
        .contentShape(Rectangle())
        .onTapGesture { finished() }          // never trap anyone in an intro
        .accessibilityAddTraits(.isButton)
        .accessibilityLabel("Skip intro")
        .onAppear(perform: run)
    }

    private func run() {
        guard !reduceMotion else {
            landed = numbers.count
            wordmarkIn = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5, execute: finished)
            return
        }

        withAnimation(.spring(response: 0.5, dampingFraction: 0.8)) { wordmarkIn = true }

        // Land the tiles left to right, like a draw being read out.
        for index in numbers.indices {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.42 + Double(index) * 0.13) {
                withAnimation(.spring(response: 0.32, dampingFraction: 0.62)) {
                    landed = index + 1
                }
            }
        }

        let settle = 0.42 + Double(numbers.count) * 0.13

        // A shot of the intro holds on the landed ticket instead of racing the
        // animation with a sleep. Timing a screenshot into a 1.6-second window
        // is a coin toss, and the frame it loses is the home screen wearing the
        // intro's caption -- wrong in a way that looks fine until it is next to
        // the others. A tap still dismisses it.
        guard !Screenshot.showsIntro else { return }

        DispatchQueue.main.asyncAfter(deadline: .now() + settle + 0.28) {
            withAnimation(.easeIn(duration: 0.3)) { lift = true }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + settle + 0.5, execute: finished)
    }
}

/// A tile that spins through digits until told to settle.
private struct SpinTile: View {
    let value: Int
    let settled: Bool
    var accent: Bool

    @State private var spin = 0
    @State private var timer: Timer?

    var body: some View {
        Text(String(format: "%02d", settled ? value : spin))
            .font(.system(size: 20, weight: .medium, design: .monospaced))
            .foregroundStyle(settled && accent ? Color.black : Color.white)
            .frame(minWidth: 40)
            .padding(.vertical, 9)
            .padding(.horizontal, 3)
            .background(
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .fill(settled && accent
                          ? Color(red: 0.98, green: 0.78, blue: 0.19)
                          : Color(red: 0.16, green: 0.16, blue: 0.17))
            )
            .scaleEffect(settled ? 1 : 0.94)
            .onAppear {
                timer = Timer.scheduledTimer(withTimeInterval: 0.055, repeats: true) { t in
                    if settled { t.invalidate() } else { spin = Int.random(in: 0...69) }
                }
            }
            .onChange(of: settled) { _, done in
                if done { timer?.invalidate() }
            }
            .onDisappear { timer?.invalidate() }
    }
}
