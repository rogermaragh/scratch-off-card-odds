import SwiftUI

@main
struct LottoMinApp: App {
    @StateObject private var store = LotteryStore()
    @StateObject private var theme = Theme()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .environmentObject(theme)
                .preferredColorScheme(theme.choice.scheme)
        }
    }
}
