import SwiftUI
import UniformTypeIdentifiers

struct MetadataDropZone: View {
    @Binding var file: URL?
    @State private var isTargeted = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 10)
                .fill(isTargeted
                      ? Color.orange.opacity(0.15)
                      : Color(NSColor.controlBackgroundColor))
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(
                    isTargeted ? Color.orange : Color.secondary.opacity(0.4),
                    style: StrokeStyle(lineWidth: 2, dash: [5, 4])
                )

            if let file {
                HStack(spacing: 10) {
                    Image(systemName: "tablecells.fill")
                        .foregroundColor(.green)
                        .font(.title3)
                    VStack(alignment: .leading) {
                        Text("MetaData.xlsx")
                            .font(.headline)
                        Text(file.path)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                    Spacer()
                    Button("Remove") { self.file = nil }
                        .buttonStyle(.borderless)
                        .foregroundColor(.red)
                }
                .padding(.horizontal, 16)
            } else {
                HStack(spacing: 10) {
                    Image(systemName: "tablecells")
                        .foregroundColor(.secondary)
                        .font(.title3)
                    Text("Drop MetaData.xlsx here or click to browse")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
            }
        }
        .onDrop(of: [.fileURL], isTargeted: $isTargeted, perform: handleDrop)
        .onTapGesture { openFilePicker() }
        .onHover { inside in
            if inside { NSCursor.pointingHand.push() } else { NSCursor.pop() }
        }
    }

    private func openFilePicker() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [UTType(filenameExtension: "xlsx")].compactMap { $0 }
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url {
            self.file = url
        }
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }
        provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
            let url: URL?
            if let data = item as? Data {
                url = URL(dataRepresentation: data, relativeTo: nil)
            } else if let u = item as? URL {
                url = u
            } else {
                url = nil
            }
            guard let url, url.pathExtension.lowercased() == "xlsx" else { return }
            DispatchQueue.main.async { self.file = url }
        }
        return true
    }
}
