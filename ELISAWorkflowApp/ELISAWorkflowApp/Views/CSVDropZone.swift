import SwiftUI
import UniformTypeIdentifiers

struct CSVDropZone: View {
    @Binding var files: [URL]
    @State private var isTargeted = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 12)
                .fill(isTargeted
                      ? Color.accentColor.opacity(0.15)
                      : Color(NSColor.controlBackgroundColor))
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(
                    isTargeted ? Color.accentColor : Color.secondary.opacity(0.4),
                    style: StrokeStyle(lineWidth: 2, dash: [6, 4])
                )

            if files.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "doc.on.doc")
                        .font(.system(size: 36))
                        .foregroundColor(.secondary)
                    Text("Drop CSV files here")
                        .font(.headline)
                    Text("Drop files here or click to browse")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(.green)
                        Text("\(files.count) CSV file\(files.count == 1 ? "" : "s") loaded")
                            .font(.headline)
                        Spacer()
                        Button("Clear") { files = [] }
                            .buttonStyle(.borderless)
                            .foregroundColor(.red)
                    }
                    Divider()
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 2) {
                            ForEach(files, id: \.self) { file in
                                Text(file.lastPathComponent)
                                    .font(.system(.caption, design: .monospaced))
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                }
                .padding(12)
            }
        }
        .onDrop(of: [.fileURL], isTargeted: $isTargeted, perform: handleDrop)
        .onTapGesture { openFileDialog() }
    }

    private func openFileDialog() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        if let csvType = UTType(filenameExtension: "csv") {
            panel.allowedContentTypes = [csvType]
        }
        panel.prompt = "Add"
        guard panel.runModal() == .OK else { return }
        for url in panel.urls where !files.contains(url) {
            files.append(url)
        }
        files.sort { $0.lastPathComponent < $1.lastPathComponent }
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                let url: URL?
                if let data = item as? Data {
                    url = URL(dataRepresentation: data, relativeTo: nil)
                } else if let u = item as? URL {
                    url = u
                } else {
                    url = nil
                }
                guard let url, url.pathExtension.uppercased() == "CSV" else { return }
                DispatchQueue.main.async {
                    if !files.contains(url) {
                        files.append(url)
                        files.sort { $0.lastPathComponent < $1.lastPathComponent }
                    }
                }
            }
        }
        return true
    }
}
