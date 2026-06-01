// Настройки: путь к папке проекта (где лежит ./bin/python и парсеры).
// Хранится в UserDefaults.
import Foundation
import SwiftUI

enum AppSettings {
    private static let keyProjectDir = "projectDir"

    static var defaultProjectDir: String {
        // ~/realty_env по умолчанию
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return "\(home)/realty_env"
    }

    static var projectDir: String {
        get { UserDefaults.standard.string(forKey: keyProjectDir) ?? defaultProjectDir }
        set { UserDefaults.standard.set(newValue, forKey: keyProjectDir) }
    }

    static var projectURL: URL { URL(fileURLWithPath: projectDir) }
    static var pythonURL: URL { projectURL.appendingPathComponent("bin/python") }
    static var commercialXLSX: URL { projectURL.appendingPathComponent("commercial_realty.xlsx") }
    static var savedXLSX: URL { projectURL.appendingPathComponent("saved_realty.xlsx") }
    static var collectScript: URL { projectURL.appendingPathComponent("collect_realty.py") }
    static var saveMarkedScript: URL { projectURL.appendingPathComponent("save_marked.py") }

    /// Проверка предпосылок (Python в venv, скрипты на месте).
    static func validate() -> String? {
        let fm = FileManager.default
        if !fm.fileExists(atPath: projectDir) { return "Папка проекта не найдена: \(projectDir)" }
        if !fm.isExecutableFile(atPath: pythonURL.path) { return "Не найден Python в venv: \(pythonURL.path). Проверь, что venv создан (./bin/python должен существовать)." }
        if !fm.fileExists(atPath: collectScript.path) { return "Нет collect_realty.py в \(projectDir)." }
        if !fm.fileExists(atPath: saveMarkedScript.path) { return "Нет save_marked.py в \(projectDir)." }
        return nil
    }
}

struct SettingsView: View {
    @EnvironmentObject var state: AppState
    @State private var dir: String = AppSettings.projectDir

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Папка проекта Python").font(.headline)
            HStack {
                TextField("/Users/denis/realty_env", text: $dir)
                    .textFieldStyle(.roundedBorder)
                Button("Выбрать…") { pickFolder() }
            }
            Text("В папке должны быть: ./bin/python (venv), collect_realty.py, save_marked.py, commercial_realty.xlsx.")
                .font(.caption)
                .foregroundColor(.secondary)
            HStack {
                Spacer()
                Button("Применить") {
                    AppSettings.projectDir = dir
                    Task { await state.loadAll() }
                }
                .keyboardShortcut(.defaultAction)
            }
        }
    }

    private func pickFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.directoryURL = URL(fileURLWithPath: dir)
        if panel.runModal() == .OK, let url = panel.url {
            dir = url.path
        }
    }
}
