import SwiftUI

/// A selector with no control chrome: weight and colour carry the state, and a
/// short rule slides beneath the active option.
///
/// The visible type is deliberately small, so each option is padded out to the
/// 44pt minimum hit area — the tappable region is larger than what it looks.
struct TypeStrip<Value: Hashable>: View {
    struct Option {
        let value: Value
        let title: String
    }

    let options: [Option]
    @Binding var selection: Value
    var activeSize: CGFloat = 19
    var inactiveSize: CGFloat = 15

    @Namespace private var underline

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 14) {
            ForEach(Array(options.enumerated()), id: \.offset) { _, option in
                let isActive = option.value == selection
                VStack(alignment: .leading, spacing: 5) {
                    Text(option.title)
                        .font(.system(size: isActive ? activeSize : inactiveSize,
                                      weight: isActive ? .medium : .regular))
                        .foregroundStyle(isActive ? .primary : .tertiary)

                    // The rule is matched-geometry so it slides between options
                    // instead of cross-fading.
                    Group {
                        if isActive {
                            Capsule()
                                .fill(Color.primary)
                                .frame(height: 2)
                                .matchedGeometryEffect(id: "rule", in: underline)
                        } else {
                            Color.clear.frame(height: 2)
                        }
                    }
                }
                .contentShape(Rectangle())
                .padding(.vertical, 11)
                .onTapGesture {
                    withAnimation(.snappy(duration: 0.25)) { selection = option.value }
                }
                .accessibilityElement()
                .accessibilityLabel(option.title)
                .accessibilityAddTraits(isActive ? [.isButton, .isSelected] : .isButton)
            }
            Spacer(minLength: 0)
        }
    }
}

/// The same idea at caption scale, for a long row of values like ticket prices.
/// Scrolls horizontally and keeps the selection legible by weight alone.
struct ValueStrip<Value: Hashable>: View {
    let label: String
    let options: [(value: Value?, title: String)]
    @Binding var selection: Value?

    var body: some View {
        HStack(alignment: .center, spacing: 0) {
            Text(label)
                .font(.system(size: 11))
                .foregroundStyle(.tertiary)
                .kerning(0.6)
                .padding(.trailing, 12)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 14) {
                    ForEach(Array(options.enumerated()), id: \.offset) { _, option in
                        let isActive = option.value == selection
                        Text(option.title)
                            .font(.system(size: 14, weight: isActive ? .medium : .regular))
                            .foregroundStyle(isActive ? .primary : .tertiary)
                            .contentShape(Rectangle())
                            .padding(.vertical, 12)
                            .onTapGesture {
                                withAnimation(.snappy(duration: 0.2)) {
                                    selection = isActive ? nil : option.value
                                }
                            }
                            .accessibilityElement()
                            .accessibilityLabel("\(label) \(option.title)")
                            .accessibilityAddTraits(
                                isActive ? [.isButton, .isSelected] : .isButton
                            )
                    }
                }
            }
        }
    }
}
