// Главный экран: тулбар, переключатель вкладок, таблица, лог-панель.
import SwiftUI

struct ContentView: View {
    @EnvironmentObject var state: AppState
    @State private var showLog = false

    var body: some View {
        VStack(spacing: 0) {
            ToolbarBar(showLog: $showLog)
                .padding(.horizontal).padding(.top, 8).padding(.bottom, 6)

            Divider()

            Picker("", selection: $state.selectedTab) {
                ForEach(AppState.MainTab.allCases) { tab in
                    Text(tabLabel(tab)).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal).padding(.vertical, 6)

            Group {
                switch state.selectedTab {
                case .sale:  MainTableView(items: state.filtered(state.saleItems))
                case .rent:  MainTableView(items: state.filtered(state.rentItems))
                case .saved: SavedView()
                }
            }

            if showLog {
                Divider()
                LogPanel().frame(height: 220)
            }
        }
        .alert("Ошибка", isPresented: Binding(
            get: { state.errorMessage != nil },
            set: { if !$0 { state.errorMessage = nil } }
        ), actions: {
            Button("OK") { state.errorMessage = nil }
        }, message: {
            Text(state.errorMessage ?? "")
        })
    }

    private func tabLabel(_ t: AppState.MainTab) -> String {
        switch t {
        case .sale:  return "Продажа (\(state.saleItems.count))"
        case .rent:  return "Аренда (\(state.rentItems.count))"
        case .saved: return "Сохранённые (\(state.savedItems.count))"
        }
    }
}

// MARK: - Тулбар с кнопками и опциями

struct ToolbarBar: View {
    @EnvironmentObject var state: AppState
    @Binding var showLog: Bool

    var body: some View {
        HStack(spacing: 14) {
            // Запустить сбор
            Button {
                state.runCollect()
                showLog = true
            } label: {
                Label(state.isRunning ? "Идёт сбор…" : "Запустить сбор",
                      systemImage: "arrow.down.circle.fill")
            }
            .disabled(state.isRunning)

            Menu("Опции сбора") {
                Toggle("--full (полный перепрогон)", isOn: $state.optFull)
                Divider()
                ForEach(AppState.Source.allCases) { src in
                    Toggle(src.display, isOn: Binding(
                        get: { state.optSources.contains(src) },
                        set: { ok in
                            if ok { state.optSources.insert(src) } else { state.optSources.remove(src) }
                        }
                    ))
                }
                Divider()
                LabeledContent("--city") {
                    TextField("minsk", text: $state.optCity).frame(width: 80)
                }
                LabeledContent("--max-pages") {
                    TextField("100", text: $state.optMaxPages).frame(width: 60)
                }
            }
            .menuStyle(.borderlessButton)
            .frame(width: 160)
            .disabled(state.isRunning)

            // Сохранить выбранное
            Button {
                state.runSaveMarked()
                showLog = true
            } label: {
                Label("Сохранить выбранное (\(state.selectedIDs.count))",
                      systemImage: "bookmark.fill")
            }
            .disabled(state.isRunning || state.selectedIDs.isEmpty)

            Spacer()

            TextField("Поиск", text: $state.search)
                .textFieldStyle(.roundedBorder)
                .frame(width: 240)

            Button { showLog.toggle() } label: {
                Image(systemName: showLog ? "chevron.up.square" : "chevron.down.square")
            }
            .help("Показать/скрыть лог")

            if state.isRunning { ProgressView().controlSize(.small) }
        }
    }
}
