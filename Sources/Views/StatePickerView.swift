import SwiftUI

struct StatePickerView: View {
    @EnvironmentObject private var store: LotteryStore
    @StateObject private var locator = StateLocator()
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""

    private var filtered: [(code: String, name: String, scratchers: Int)] {
        guard !query.isEmpty else { return store.allStates }
        return store.allStates.filter {
            $0.name.localizedCaseInsensitiveContains(query)
                || $0.code.localizedCaseInsensitiveContains(query)
        }
    }

    private var withScratchers: Int {
        store.allStates.filter { $0.scratchers > 0 }.count
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button(action: detect) {
                        HStack {
                            Label(detectLabel, systemImage: "location.fill")
                            Spacer()
                            if locator.status == .locating { ProgressView() }
                        }
                    }
                    .disabled(locator.status == .locating)

                    if case .denied = locator.status {
                        Text("Location access is off. Enable it in Settings, or pick a state below.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if case .failed(let message) = locator.status {
                        Text(message).font(.caption).foregroundStyle(.secondary)
                    }
                }

                Section {
                    ForEach(filtered, id: \.code) { state in
                        Button {
                            store.stateCode = state.code
                            dismiss()
                        } label: {
                            HStack {
                                Text(state.name)
                                Spacer()
                                if state.scratchers > 0 {
                                    Text("\(state.scratchers)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .monospacedDigit()
                                }
                                if store.stateCode == state.code {
                                    Image(systemName: "checkmark")
                                        .font(.footnote.weight(.semibold))
                                        .foregroundStyle(Color.accentColor)
                                }
                            }
                        }
                        .foregroundStyle(.primary)
                    }
                } header: {
                    Text("Draw results everywhere · scratch-offs in \(withScratchers)")
                } footer: {
                    Text("The number shows how many scratch-off games are ranked for that state.")
                }
            }
            .searchable(text: $query, prompt: "Search states")
            .navigationTitle("Choose state")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private var detectLabel: String {
        switch locator.status {
        case .locating: return "Detecting…"
        case .found(let code): return "Detected \(code)"
        default: return "Use my location"
        }
    }

    private func detect() {
        locator.detect { code in
            guard store.allStates.contains(where: { $0.code == code }) else { return }
            store.stateCode = code
            dismiss()
        }
    }
}
