import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @StateObject private var vm = ProcessingViewModel()
    @State private var showFitSettings = false

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("ELISA Workflow")
                .font(.largeTitle)
                .fontWeight(.bold)
                .frame(maxWidth: .infinity, alignment: .center)

            CSVDropZone(files: $vm.csvFiles)
                .frame(minHeight: 180)

            metadataSection

            outputSection

            HStack {
                Spacer()
                Button("Process") { vm.runProcessing() }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(!vm.canProcess || vm.isProcessing)
                Spacer()
            }

            LogView(text: vm.logText, errorMessage: vm.errorMessage, isProcessing: vm.isProcessing)
                .frame(minHeight: 140)
        }
        .padding(24)
        .frame(minWidth: 620, minHeight: 660)
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button { showFitSettings = true } label: {
                    Image(systemName: "gearshape")
                }
                .help("Curve Fit Settings")
            }
        }
        .sheet(isPresented: $showFitSettings) {
            CurveFitSettingsView(vm: vm)
        }
        .alert("Python Not Found", isPresented: $vm.showPythonAlert) {
            Button("OK") {}
        } message: {
            Text(vm.pythonAlertMessage)
        }
    }

    // MARK: - Metadata section

    private var metadataSection: some View {
        ZStack {
            metadataBackground
            metadataContent
        }
        .frame(height: 70)
        .onDrop(of: [.fileURL], isTargeted: nil, perform: handleMetadataDrop)
        .onTapGesture { openMetadataFilePicker() }
        .onHover { inside in
            if inside { NSCursor.pointingHand.push() } else { NSCursor.pop() }
        }
    }

    @ViewBuilder
    private var metadataContent: some View {
        if let name = vm.metadataDisplayName {
            HStack(spacing: 12) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)
                    .font(.title3)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Metadata loaded")
                        .font(.headline)
                    Text(name)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                Spacer()
                Button("Clear") { vm.metadataFile = nil }
                    .buttonStyle(.borderless)
                    .foregroundColor(.red)
            }
            .padding(.horizontal, 16)
        } else {
            HStack(spacing: 16) {
                Button("Create MetaData.xlsx…") { vm.createMetadataTemplate() }
                    .buttonStyle(.bordered)
                Text("or drop / click to browse for an existing MetaData.xlsx")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
        }
    }

    private var metadataBackground: some View {
        RoundedRectangle(cornerRadius: 10)
            .fill(vm.metadataDisplayName != nil
                  ? Color.green.opacity(0.06)
                  : Color(NSColor.controlBackgroundColor))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(
                        vm.metadataDisplayName != nil
                            ? Color.green.opacity(0.35)
                            : Color.secondary.opacity(0.4),
                        style: StrokeStyle(lineWidth: 2, dash: [5, 4])
                    )
            )
    }

    private func openMetadataFilePicker() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [UTType(filenameExtension: "xlsx")].compactMap { $0 }
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url {
            vm.metadataFile = url
        }
    }

    private func handleMetadataDrop(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }
        provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
            let url: URL?
            if let data = item as? Data { url = URL(dataRepresentation: data, relativeTo: nil) }
            else if let u = item as? URL { url = u }
            else { url = nil }
            guard let url, url.pathExtension.lowercased() == "xlsx" else { return }
            DispatchQueue.main.async { vm.metadataFile = url }
        }
        return true
    }

    // MARK: - Output section

    private var outputSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Output").font(.headline)
            HStack(spacing: 12) {
                Button("Choose folder…") {
                    let panel = NSOpenPanel()
                    panel.canChooseDirectories = true
                    panel.canChooseFiles = false
                    panel.allowsMultipleSelection = false
                    panel.prompt = "Select"
                    if panel.runModal() == .OK, let url = panel.url {
                        vm.outputDirectory = url
                    }
                }
                if let dir = vm.outputDirectory {
                    Label(dir.path, systemImage: "folder")
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                Spacer()
            }
            HStack {
                Text("Filename:")
                TextField("e.g. 260521_my_experiment", text: $vm.outputName)
                    .textFieldStyle(.roundedBorder)
                Text(".xlsx")
                    .foregroundColor(.secondary)
            }
        }
        .padding(12)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }
}
