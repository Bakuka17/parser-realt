// Пути к проекту Python (venv + web/server.py). Папку можно переопределить в UserDefaults.
import Foundation

enum AppSettings {
    private static let keyProjectDir = "projectDir"

    static var defaultProjectDir: String {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return "\(home)/realty_env"
    }
    static var projectDir: String {
        get { UserDefaults.standard.string(forKey: keyProjectDir) ?? defaultProjectDir }
        set { UserDefaults.standard.set(newValue, forKey: keyProjectDir) }
    }
    static var projectURL: URL { URL(fileURLWithPath: projectDir) }
    static var pythonURL: URL { projectURL.appendingPathComponent("bin/python") }
}
