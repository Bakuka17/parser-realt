// Управляет жизнью локального сервера дашборда: запускает web/server.py при
// старте приложения, ловит из его вывода адрес (http://localhost:PORT) и гасит
// процесс при выходе. REALTY_NO_BROWSER=1 — чтобы server.py не открывал Safari.
import Foundation
import Combine

final class ServerController: ObservableObject {
    @Published var serverURL: URL?
    @Published var status: String = "Запускаю сервер дашборда…"
    @Published var failed: String?

    private var process: Process?

    func start() {
        guard process == nil else { return }
        let py = AppSettings.pythonURL
        let server = AppSettings.projectURL.appendingPathComponent("web/server.py")
        let fm = FileManager.default
        guard fm.isExecutableFile(atPath: py.path) else {
            return setFailed("Не найден Python venv: \(py.path)\nПроверь папку проекта в настройках.")
        }
        guard fm.fileExists(atPath: server.path) else {
            return setFailed("Не найден web/server.py в \(AppSettings.projectDir)")
        }

        let p = Process()
        p.executableURL = py
        p.arguments = ["-u", server.path]          // -u: небуферизованный вывод (адрес приходит сразу)
        p.currentDirectoryURL = AppSettings.projectURL
        var env = ProcessInfo.processInfo.environment
        env["REALTY_NO_BROWSER"] = "1"             // не открывать Safari — мы покажем в окне
        p.environment = env

        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        // Постоянно вычитываем вывод (иначе буфер заполнится и сервер встанет),
        // а в первой строке с адресом — выдёргиваем URL.
        pipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let data = h.availableData
            guard !data.isEmpty, let s = String(data: data, encoding: .utf8) else { return }
            if let r = s.range(of: #"http://localhost:\d+"#, options: .regularExpression) {
                self?.setURL(String(s[r]) + "/index.html")
            }
        }

        do { try p.run() } catch {
            return setFailed("Не удалось запустить сервер: \(error.localizedDescription)")
        }
        process = p
    }

    func stop() {
        process?.terminate()
        process = nil
    }

    private func setURL(_ s: String) {
        DispatchQueue.main.async {
            guard self.serverURL == nil, let u = URL(string: s) else { return }
            self.serverURL = u
            self.status = "Готово"
        }
    }

    private func setFailed(_ m: String) {
        DispatchQueue.main.async { self.failed = m }
    }
}
