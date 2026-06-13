// Содержимое окна: пока сервер поднимается — спиннер; готов — веб-дашборд; ошибка — текст.
import SwiftUI

struct ContentView: View {
    @EnvironmentObject var server: ServerController

    var body: some View {
        Group {
            if let url = server.serverURL {
                WebView(url: url)
            } else if let err = server.failed {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 40)).foregroundColor(.orange)
                    Text("Не удалось открыть дашборд").font(.title3.bold())
                    Text(err).font(.callout).foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: 460).padding(40)
            } else {
                VStack(spacing: 16) {
                    ProgressView().controlSize(.large)
                    Text(server.status).foregroundColor(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
