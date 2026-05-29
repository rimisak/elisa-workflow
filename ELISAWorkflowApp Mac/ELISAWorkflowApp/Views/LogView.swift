import SwiftUI

struct LogView: View {
    let text: String
    let errorMessage: String?
    let isProcessing: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Log")
                    .font(.headline)
                Spacer()
                if isProcessing {
                    ProgressView()
                        .controlSize(.small)
                } else if errorMessage != nil {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.red)
                } else if !text.isEmpty {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                }
            }

            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        if let err = errorMessage {
                            Text(err)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundColor(.red)
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        } else {
                            Text(text.isEmpty ? "Ready." : text)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundColor(text.isEmpty ? .secondary : .primary)
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .id("bottom")
                        }
                    }
                    .padding(8)
                }
                .onChange(of: text) { _ in
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
            }
        }
        .padding(10)
        .background(Color(NSColor.textBackgroundColor))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .strokeBorder(Color.secondary.opacity(0.2), lineWidth: 1)
        )
    }
}
