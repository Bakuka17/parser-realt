// Главный ObservableObject: загрузка xlsx, выбор объектов, запуск парсеров.
import Foundation
import SwiftUI

@MainActor
final class AppState: ObservableObject {

    // Данные
    @Published var saleItems: [RealtyItem] = []
    @Published var rentItems: [RealtyItem] = []
    @Published var savedItems: [SavedItem] = []

    // Состояние UI
    @Published var search: String = ""
    @Published var selectedTab: MainTab = .sale
    @Published var selectedIDs: Set<String> = []   // хэши, выбранные галочкой В ПРИЛОЖЕНИИ
    @Published var isRunning: Bool = false         // занят ли Python-процесс
    @Published var logLines: [String] = []
    @Published var errorMessage: String? = nil

    // Опции парсера
    @Published var optFull: Bool = false
    @Published var optMaxPages: String = "100"
    @Published var optCity: String = "minsk"
    @Published var optSources: Set<Source> = [.realt, .megapolis, .kufar]

    enum MainTab: String, CaseIterable, Identifiable {
        case sale  = "Продажа"
        case rent  = "Аренда"
        case saved = "Сохранённые"
        var id: String { rawValue }
    }
    enum Source: String, CaseIterable, Identifiable {
        case realt = "realt"
        case megapolis = "megapolis"
        case kufar = "kufar"
        var id: String { rawValue }
        var display: String {
            switch self {
            case .realt: return "realt.by"
            case .megapolis: return "megapolis"
            case .kufar: return "kufar.by"
            }
        }
    }

    // MARK: - Загрузка данных

    func loadAll() async {
        if let err = AppSettings.validate() {
            errorMessage = err
            return
        }
        await loadMain()
        await loadSaved()
    }

    func loadMain() async {
        let url = AppSettings.commercialXLSX
        guard FileManager.default.fileExists(atPath: url.path) else {
            // нет файла — это норма до первого прогона
            saleItems = []; rentItems = []; return
        }
        do {
            let pair = try XLSXService.readMain(at: url)
            self.saleItems = pair.sale
            self.rentItems = pair.rent
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadSaved() async {
        let url = AppSettings.savedXLSX
        guard FileManager.default.fileExists(atPath: url.path) else { savedItems = []; return }
        do {
            self.savedItems = try XLSXService.readSaved(at: url)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Фильтр

    func filtered(_ items: [RealtyItem]) -> [RealtyItem] {
        if search.isEmpty { return items }
        return items.filter { $0.matches(search) }
    }

    // MARK: - Запуск collect_realty.py

    func runCollect() {
        if let err = AppSettings.validate() { errorMessage = err; return }
        guard !isRunning else { return }

        var args = ["collect_realty.py"]
        if optFull { args.append("--full") }
        let max = optMaxPages.trimmingCharacters(in: .whitespaces)
        if !max.isEmpty, max != "100" { args += ["--max-pages", max] }
        if optCity != "minsk" { args += ["--city", optCity] }
        if optSources.count < Source.allCases.count {
            args += ["--sources", optSources.map { $0.rawValue }.joined(separator: ",")]
        }
        runPython(args: args, label: "Сбор источников") {
            await self.loadMain()
        }
    }

    /// Сохранить отмеченные в приложении объекты (запуск save_marked.py --hashes).
    func runSaveMarked() {
        if let err = AppSettings.validate() { errorMessage = err; return }
        guard !isRunning else { return }
        let hashes = selectedIDs.filter { !$0.isEmpty }
        guard !hashes.isEmpty else {
            errorMessage = "Никаких объектов не отмечено. Поставь галочки в таблице слева."
            return
        }
        let args = ["save_marked.py",
                    AppSettings.commercialXLSX.path,
                    "--hashes", hashes.joined(separator: ",")]
        runPython(args: args, label: "Сохранение отмеченных") {
            await self.loadSaved()
            self.selectedIDs.removeAll()
        }
    }

    /// Удалить строку из saved_realty.xlsx по хэшу через маленький Python-помощник.
    func deleteSaved(hashes: [String]) {
        if let err = AppSettings.validate() { errorMessage = err; return }
        guard !isRunning else { return }
        let py = """
        import sys
        from pathlib import Path
        from openpyxl import load_workbook
        p = Path(sys.argv[1])
        targets = set(sys.argv[2].split(','))
        wb = load_workbook(p)
        ws = wb.active
        # Найдём индекс колонки «Хэш»
        hdr = [c.value for c in ws[1]]
        hi = hdr.index('Хэш') + 1
        rm = []
        for r in range(2, ws.max_row+1):
            if str(ws.cell(r, hi).value or '') in targets:
                rm.append(r)
        for r in reversed(rm):
            ws.delete_rows(r)
        wb.save(p)
        print(f'Удалено строк: {len(rm)}')
        """
        let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("delete_saved_\(UUID().uuidString).py")
        try? py.write(to: tmp, atomically: true, encoding: .utf8)
        let args = [tmp.path, AppSettings.savedXLSX.path, hashes.joined(separator: ",")]
        runPython(args: args, label: "Удаление из сохранённых", scriptName: tmp.lastPathComponent) {
            await self.loadSaved()
            try? FileManager.default.removeItem(at: tmp)
        }
    }

    // MARK: - Общий запуск Python

    private func runPython(args: [String], label: String, scriptName: String? = nil,
                           onFinish: (@MainActor () async -> Void)? = nil) {
        isRunning = true
        logLines.append("▶︎ \(label): \(scriptName ?? args.first ?? "")")
        let py = AppSettings.pythonURL
        let cwd = AppSettings.projectURL

        Task.detached { [weak self] in
            let code = await ProcessRunner.run(executable: py, arguments: args, cwd: cwd) { line in
                Task { @MainActor in
                    self?.logLines.append(line)
                    if self?.logLines.count ?? 0 > 4000 {
                        self?.logLines.removeFirst(500)
                    }
                }
            }
            await MainActor.run {
                self?.logLines.append("◼︎ Завершено, exit=\(code)\n")
                self?.isRunning = false
            }
            await onFinish?()
        }
    }
}
