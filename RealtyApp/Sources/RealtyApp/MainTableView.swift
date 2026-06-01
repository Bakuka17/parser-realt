// Таблица «Продажа» / «Аренда» с чекбоксом «Сохранить» (в памяти).
import SwiftUI

struct MainTableView: View {
    @EnvironmentObject var state: AppState
    let items: [RealtyItem]
    @State private var sortOrder: [KeyPathComparator<RealtyItem>] = [
        .init(\.pubDate, order: .reverse)
    ]

    var body: some View {
        Table(of: RealtyItem.self, selection: .constant(Set<String>()), sortOrder: $sortOrder) {
            TableColumn("✓") { item in
                Toggle("", isOn: Binding(
                    get: { state.selectedIDs.contains(item.id) },
                    set: { ok in
                        if ok { state.selectedIDs.insert(item.id) }
                        else  { state.selectedIDs.remove(item.id) }
                    }
                )).labelsHidden()
            }
            .width(30)

            TableColumn("Тип", value: \.type).width(min: 80, ideal: 90)
            TableColumn("Адрес", value: \.address).width(min: 180, ideal: 240)
            TableColumn("Район/Город", value: \.district).width(min: 110, ideal: 140)
            TableColumn("Площадь", value: \.area).width(min: 70, ideal: 80)
            TableColumn("Цена общая", value: \.priceTotal).width(min: 130, ideal: 160)
            TableColumn("Телефон", value: \.phone).width(min: 140, ideal: 170)
            TableColumn("Дата", value: \.pubDate).width(min: 80, ideal: 90)
            TableColumn("Источник", value: \.source).width(min: 110, ideal: 130)
            TableColumn("Ссылка") { item in
                if let url = URL(string: item.link), !item.link.isEmpty {
                    Link(destination: url) {
                        Text(item.link)
                            .lineLimit(1)
                            .foregroundColor(.accentColor)
                            .underline()
                    }
                } else {
                    Text("")
                }
            }
            .width(min: 200, ideal: 280)
        } rows: {
            ForEach(items.sorted(using: sortOrder)) { item in
                TableRow(item)
            }
        }
    }
}
