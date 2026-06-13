// Точка входа. Окно = веб-дашборд в WKWebView; сервер живёт ровно пока открыто приложение.
import SwiftUI

@main
struct RealtyAppApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var server = ServerController()

    var body: some Scene {
        WindowGroup("Коммерческая недвижимость — консоль обзвона") {
            ContentView()
                .environmentObject(server)
                .frame(minWidth: 1100, minHeight: 720)
                .task {
                    delegate.server = server
                    server.start()
                }
        }
        .commands { CommandGroup(replacing: .newItem) {} }   // убрать «New Window»
    }
}

/// Закрывает приложение при закрытии окна и гасит локальный сервер при выходе.
final class AppDelegate: NSObject, NSApplicationDelegate {
    weak var server: ServerController?
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { server?.stop() }
}
