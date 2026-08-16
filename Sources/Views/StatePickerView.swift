import SwiftUI

struct StatePickerView: View {
    @EnvironmentObject private var store: LotteryStore
    @StateObject private var locator = StateLocator()
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""

    /// Every US jurisdiction that runs a lottery. Coverage is a separate
    /// question: a state is listed here but only selectable once a scraper
    /// adapter exists for it.
    private static let allStates: [(code: String, name: String)] = [
        ("AZ", "Arizona"), ("AR", "Arkansas"), ("CA", "California"),
        ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"),
        ("DC", "District of Columbia"), ("FL", "Florida"), ("GA", "Georgia"),
        ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"),
        ("KS", "Kansas"), ("KY", "Kentucky"), ("LA", "Louisiana"),
        ("ME", "Maine"), ("MD", "Maryland"), ("MA", "Massachusetts"),
        ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"),
        ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"),
        ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"),
        ("NY", "New York"), ("NC", "North Carolina"), ("ND", "North Dakota"),
        ("OH", "Ohio"), ("OK", "Oklahoma"), ("OR", "Oregon"),
        ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
        ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"),
        ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"),
        ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming"),
    ]

    private var covered: Set<String> { Set(store.availableStates.map(\.code)) }

    private var filtered: [(code: String, name: String)] {
        guard !query.isEmpty else { return Self.allStates }
        return Self.allStates.filter {
            $0.name.localizedCaseInsensitiveContains(query)
                || $0.code.localizedCaseInsensitiveContains(query)
        }
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button(action: detect) {
                        HStack {
                            Label(detectLabel, systemImage: "location.fill")
                            Spacer()
                            if locator.status == .locating {
                                ProgressView()
                            }
                        }
                    }
                    .disabled(locator.status == .locating)

                    if case .denied = locator.status {
                        Text("Location access is off. Enable it in Settings, or pick a state below.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if case .failed(let message) = locator.status {
                        Text(message)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Section {
                    ForEach(filtered, id: \.code) { state in
                        row(for: state)
                    }
                } header: {
                    Text("\(covered.count) of \(Self.allStates.count) states have data")
                } footer: {
                    Text("Greyed-out states run lotteries but don't have a data adapter yet.")
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

    @ViewBuilder
    private func row(for state: (code: String, name: String)) -> some View {
        let isCovered = covered.contains(state.code)
        Button {
            guard isCovered else { return }
            store.stateCode = state.code
            dismiss()
        } label: {
            HStack {
                Text(state.name)
                    .foregroundStyle(isCovered ? .primary : .tertiary)
                Spacer()
                if store.stateCode == state.code {
                    Image(systemName: "checkmark")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Color.accentColor)
                } else if !isCovered {
                    Text("Soon")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .disabled(!isCovered)
    }

    private func detect() {
        locator.detect { code in
            guard covered.contains(code) else { return }
            store.stateCode = code
            dismiss()
        }
    }
}
