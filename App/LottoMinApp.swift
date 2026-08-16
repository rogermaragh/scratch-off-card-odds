import SwiftUI

@main
struct LottoMinApp: App {
    @StateObject private var store = LotteryStore()

    var body: some Scene {
        WindowGroup {
            HomeView()
                .environmentObject(store)
        }
    }
}
