// Точка входа SwiftUI-приложения.
import SwiftUI

@main
struct RealtyAppApp: App {
    @StateObject private var state = AppState()

    var body: some Scene {
        WindowGroup("Коммерческая недвижимость") {
            ContentView()
                .environmentObject(state)
                .frame(minWidth: 1100, minHeight: 700)
                .task { await state.loadAll() }
        }
        .windowToolbarStyle(.unified)
        .commands {
            CommandGroup(replacing: .newItem) {} // убираем стандартное New Window
        }

        Settings {
            SettingsView()
                .environmentObject(state)
                .frame(width: 520, height: 220)
                .padding()
        }
    }
}
