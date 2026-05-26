import Foundation
import SwiftUI
import UniformTypeIdentifiers

@MainActor
class ProcessingViewModel: ObservableObject {
    // MARK: - File state
    @Published var csvFiles: [URL] = []
    @Published var metadataFile: URL? = nil
    @Published var outputDirectory: URL? = nil
    @Published var outputName: String = "ELISA_Output"

    // MARK: - Processing state
    @Published var logText: String = ""
    @Published var isProcessing: Bool = false
    @Published var errorMessage: String? = nil
    @Published var showPythonAlert: Bool = false
    @Published var pythonAlertMessage: String = ""

    // MARK: - Derived state

    var metadataDisplayName: String? { metadataFile?.lastPathComponent }

    var canProcess: Bool {
        !csvFiles.isEmpty &&
        metadataFile != nil &&
        outputDirectory != nil &&
        !outputName.trimmingCharacters(in: .whitespaces).isEmpty
    }

    // MARK: - Create metadata template

    func createMetadataTemplate() {
        guard let python = findPython3() else {
            pythonAlertMessage = """
                python3 was not found, or it is missing required packages \
                (openpyxl, scipy, numpy).

                Install them with:
                  pip3 install openpyxl scipy numpy
                """
            showPythonAlert = true
            return
        }

        guard let scriptPath = Bundle.main.path(forResource: "elisa_workflow", ofType: "py") else {
            errorMessage = "Processing script not found in app bundle."
            return
        }

        let panel = NSSavePanel()
        panel.nameFieldStringValue = "MetaData.xlsx"
        if let xlsxType = UTType(filenameExtension: "xlsx") {
            panel.allowedContentTypes = [xlsxType]
        }
        panel.prompt = "Create"
        guard panel.runModal() == .OK, let url = panel.url else { return }

        let numPlates = max(csvFiles.count, 1)
        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = [
            scriptPath,
            "--create-template",
            "--num-plates", "\(numPlates)",
            "--template-output", url.path
        ]
        let errPipe = Pipe()
        process.standardError  = errPipe
        process.standardOutput = Pipe()

        do {
            try process.run()
            process.waitUntilExit()
            if process.terminationStatus == 0 {
                metadataFile = url
                NSWorkspace.shared.open(url)
            } else {
                let d = errPipe.fileHandleForReading.readDataToEndOfFile()
                errorMessage = String(data: d, encoding: .utf8) ?? "Failed to create template"
            }
        } catch {
            errorMessage = "Failed to launch python3: \(error.localizedDescription)"
        }
    }

    // MARK: - Processing

    func runProcessing() {
        guard canProcess else { return }

        guard let python = findPython3() else {
            pythonAlertMessage = """
                python3 was not found, or it is missing required packages \
                (openpyxl, scipy, numpy).

                Install them with:
                  pip3 install openpyxl scipy numpy

                Common locations checked:
                  /opt/homebrew/bin/python3
                  /usr/local/bin/python3
                  ~/anaconda3/bin/python3
                  ~/miniconda3/bin/python3
                """
            showPythonAlert = true
            return
        }

        guard let scriptPath = Bundle.main.path(forResource: "elisa_workflow", ofType: "py") else {
            errorMessage = "Processing script not found in app bundle. Please rebuild the app."
            return
        }

        isProcessing = true
        logText = ""
        errorMessage = nil

        let files    = csvFiles.map(\.path)
        let outDir   = outputDirectory!.path
        let outName  = outputName.trimmingCharacters(in: .whitespaces)
        let metaPath = metadataFile!.path

        Task.detached(priority: .userInitiated) { [weak self] in
            var args = ["-u", scriptPath, "--input-files"] + files
            args += ["--metadata", metaPath, "--output-dir", outDir, "--output-name", outName]

            let process = Process()
            process.executableURL = URL(fileURLWithPath: python)
            process.arguments = args

            let stdoutPipe = Pipe()
            let stderrPipe = Pipe()
            process.standardOutput = stdoutPipe
            process.standardError  = stderrPipe

            stdoutPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
                let captured = self
                Task { @MainActor in captured?.logText += text }
            }

            do {
                try process.run()
            } catch {
                await MainActor.run { [weak self] in
                    self?.errorMessage = "Failed to launch python3: \(error.localizedDescription)"
                    self?.isProcessing = false
                }
                return
            }

            process.waitUntilExit()
            stdoutPipe.fileHandleForReading.readabilityHandler = nil

            let exitCode = process.terminationStatus
            await MainActor.run { [weak self] in
                if exitCode != 0 {
                    let errData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
                    let errText = String(data: errData, encoding: .utf8) ?? ""
                    self?.errorMessage = errText.isEmpty
                        ? "Processing failed (exit code \(exitCode))"
                        : errText
                }
                self?.isProcessing = false
            }
        }
    }

    // MARK: - Python discovery

    private func findPython3() -> String? {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let candidates = [
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "\(home)/anaconda3/bin/python3",
            "\(home)/miniconda3/bin/python3",
            "\(home)/opt/anaconda3/bin/python3",
            "\(home)/.pyenv/shims/python3",
            "/usr/bin/python3",
        ]
        for path in candidates where FileManager.default.isExecutableFile(atPath: path) {
            if pythonHasRequiredPackages(at: path) { return path }
        }
        return shellDiscoveredPython()
    }

    private func pythonHasRequiredPackages(at python: String) -> Bool {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: python)
        p.arguments = ["-c", "import openpyxl, scipy, numpy"]
        let pipe = Pipe()
        p.standardError  = pipe
        p.standardOutput = pipe
        try? p.run()
        p.waitUntilExit()
        return p.terminationStatus == 0
    }

    private func shellDiscoveredPython() -> String? {
        for shell in ["/bin/zsh", "/bin/bash"] where FileManager.default.fileExists(atPath: shell) {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: shell)
            p.arguments = ["-l", "-c", "which python3"]
            let pipe = Pipe()
            p.standardOutput = pipe
            p.standardError  = Pipe()
            try? p.run()
            p.waitUntilExit()
            guard p.terminationStatus == 0 else { continue }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let path = (String(data: data, encoding: .utf8) ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !path.isEmpty && pythonHasRequiredPackages(at: path) { return path }
        }
        return nil
    }
}
