// Таблица «Сохранённые» (saved_realty.xlsx) + удаление выбранного.
import SwiftUI
import AppKit

struct SavedView: View {
    @EnvironmentObject var state: AppState
    @State private var selectedIDs: Set<String> = []
    @State private var sortOrder: [KeyPathComparator<SavedItem>] = []

    var filtered: [SavedItem] {
        guard !state.search.isEmpty else { return state.savedItems }
        let q = state.search.lowercased()
        return state.savedItems.filter { it in
            it.raw.values.contains { $0.lowercased().contains(q) }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Сохранённых: \(state.savedItems.count)").font(.subheadline)
                Spacer()
                Button(role: .destructive) {
                    let hashes = Array(selectedIDs).filter { !$0.isEmpty }
                    if !hashes.isEmpty {
                        state.deleteSaved(hashes: hashes)
                        selectedIDs.removeAll()
                    }
                } label: {
                    Label("Удалить выбранное (\(selectedIDs.count))", systemImage: "trash")
                }
                .disabled(selectedIDs.isEmpty || state.isRunning)
            }
            .padding(.horizontal).padding(.vertical, 6)

            Table(of: SavedItem.self, selection: $selectedIDs, sortOrder: $sortOrder) {
                TableColumn("Тип", value: \.type).width(min: 80, ideal: 90)
                TableColumn("Адрес", value: \.address).width(min: 180, ideal: 240)
                TableColumn("Цена", value: \.priceTotal).width(min: 130, ideal: 160)
                TableColumn("Телефон", value: \.phone).width(min: 140, ideal: 170)
                TableColumn("Активность", value: \.activity).width(min: 100, ideal: 120)
                TableColumn("До транспорта, м", value: \.toTransit).width(min: 110, ideal: 130)
                TableColumn("📂 Фото") { item in
                    Button {
                        openPhotoFolder(for: item)
                    } label: {
                        if item.photoFiles.isEmpty {
                            Text("—").foregroundColor(.secondary)
                        } else {
                            let count = item.photoFiles.split(separator: ";").count
                            Label("\(count) шт", systemImage: "folder")
                        }
                    }
                    .buttonStyle(.borderless)
                    .disabled(item.photoFiles.isEmpty)
                }
                .width(min: 80, ideal: 90)
                TableColumn("Ссылка") { item in
                    if let url = URL(string: item.link), !item.link.isEmpty {
                        Link(destination: url) { Text(item.link).lineLimit(1).foregroundColor(.accentColor).underline() }
                    } else {
                        Text("")
                    }
                }
                .width(min: 200, ideal: 280)
            } rows: {
                ForEach(filtered.sorted(using: sortOrder)) { item in
                    TableRow(item)
                }
            }
        }
    }

    /// Открывает папку с фото в Finder и подсвечивает первый файл.
    private func openPhotoFolder(for item: SavedItem) {
        let firstPath = item.photoFiles.split(separator: ";").first.map(String.init) ?? ""
        guard !firstPath.isEmpty else { return }
        let url = AppSettings.projectURL.appendingPathComponent(firstPath)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }
}
