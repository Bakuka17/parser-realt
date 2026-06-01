// Чтение xlsx через CoreXLSX.
// commercial_realty.xlsx устроен так (см. realty_parser_v8.write_excel):
//   листы "Сводка", "Продажа", "Аренда"; строка 1 — мерж-заголовок,
//   строка 2 — заголовки колонок, строки 3+ — данные.
// saved_realty.xlsx: один лист "Сохранённые", строка 1 — заголовки, 2+ — данные.
import Foundation
import CoreXLSX

enum XLSXError: Error, LocalizedError {
    case fileNotFound(String)
    case parseFailed(String)
    case noWorksheet(String)

    var errorDescription: String? {
        switch self {
        case .fileNotFound(let p): return "Файл не найден: \(p)"
        case .parseFailed(let m): return "Ошибка чтения xlsx: \(m)"
        case .noWorksheet(let n): return "Не найден лист: \(n)"
        }
    }
}

struct XLSXService {

    /// Читает commercial_realty.xlsx. Возвращает (Продажа, Аренда).
    static func readMain(at url: URL) throws -> (sale: [RealtyItem], rent: [RealtyItem]) {
        let file = try openFile(at: url)
        let strings: SharedStrings? = try? file.parseSharedStrings()
        let workbook = try file.parseWorkbooks().first ?? { throw XLSXError.parseFailed("Нет workbook") }()
        let nameMap = try file.parseWorksheetPathsAndNames(workbook: workbook)

        func readSheet(_ name: String) -> [RealtyItem] {
            guard let path = nameMap.first(where: { $0.name == name })?.path else { return [] }
            guard let ws = try? file.parseWorksheet(at: path) else { return [] }
            return parseRealtyRows(ws: ws, strings: strings, dealSheet: name)
        }
        return (readSheet("Продажа"), readSheet("Аренда"))
    }

    /// Читает saved_realty.xlsx (первый лист).
    static func readSaved(at url: URL) throws -> [SavedItem] {
        let file = try openFile(at: url)
        let strings: SharedStrings? = try? file.parseSharedStrings()
        let workbook = try file.parseWorkbooks().first ?? { throw XLSXError.parseFailed("Нет workbook") }()
        let nameMap = try file.parseWorksheetPathsAndNames(workbook: workbook)
        guard let path = nameMap.first?.path,
              let ws = try? file.parseWorksheet(at: path) else { return [] }
        return parseSavedRows(ws: ws, strings: strings)
    }

    // MARK: - private

    private static func openFile(at url: URL) throws -> XLSXFile {
        let fm = FileManager.default
        guard fm.fileExists(atPath: url.path) else { throw XLSXError.fileNotFound(url.path) }
        guard let file = XLSXFile(filepath: url.path) else { throw XLSXError.parseFailed("CoreXLSX не открыл файл") }
        return file
    }

    /// Заголовки для commercial: строка 2. Данные с 3-й.
    private static func parseRealtyRows(ws: Worksheet, strings: SharedStrings?, dealSheet: String) -> [RealtyItem] {
        let rows = ws.data?.rows ?? []
        guard rows.count >= 3 else { return [] }
        // Найдём строку заголовков: первая строка, где встречается "Тип" + "Хэш" среди значений.
        var headers: [String: String] = [:]   // refColumn -> headerName
        var headerRowIdx = 1
        for (i, row) in rows.enumerated() {
            let texts = row.cells.compactMap { cellText($0, strings: strings) }
            if texts.contains(Col.type) && texts.contains(Col.hash) {
                for cell in row.cells {
                    if let t = cellText(cell, strings: strings) {
                        let col = String(cell.reference.column.value)
                        headers[col] = t
                    }
                }
                headerRowIdx = i
                break
            }
        }
        guard !headers.isEmpty else { return [] }

        var out: [RealtyItem] = []
        for row in rows.suffix(from: headerRowIdx + 1) {
            var raw: [String: String] = [:]
            for cell in row.cells {
                let col = String(cell.reference.column.value)
                if let header = headers[col], let val = cellText(cell, strings: strings) {
                    raw[header] = val
                }
            }
            if raw[Col.link] != nil || raw[Col.hash] != nil {
                out.append(RealtyItem(dealSheet: dealSheet, raw: raw))
            }
        }
        return out
    }

    /// saved_realty.xlsx: заголовки в строке 1.
    private static func parseSavedRows(ws: Worksheet, strings: SharedStrings?) -> [SavedItem] {
        let rows = ws.data?.rows ?? []
        guard let headerRow = rows.first else { return [] }
        var headers: [String: String] = [:]
        for cell in headerRow.cells {
            if let t = cellText(cell, strings: strings) {
                headers[String(cell.reference.column.value)] = t
            }
        }
        var out: [SavedItem] = []
        for row in rows.dropFirst() {
            var raw: [String: String] = [:]
            for cell in row.cells {
                let col = String(cell.reference.column.value)
                if let h = headers[col], let v = cellText(cell, strings: strings) {
                    raw[h] = v
                }
            }
            if !raw.isEmpty { out.append(SavedItem(raw: raw)) }
        }
        return out
    }

    /// Возвращает строковое значение ячейки (поддерживает inline + shared strings + числа).
    private static func cellText(_ cell: Cell, strings: SharedStrings?) -> String? {
        if let s = cell.inlineString?.text { return s }
        if let ss = strings, let val = cell.stringValue(ss) { return val }
        if let v = cell.value { return v }
        return nil
    }
}
