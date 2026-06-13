// Нативная обёртка вокруг WKWebView — показывает локальный веб-дашборд.
import SwiftUI
import WebKit

struct WebView: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.defaultWebpagePreferences.allowsContentJavaScript = true
        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.load(URLRequest(url: url))
        return wv
    }

    // URL сервера задаётся один раз (окно создаётся только когда он готов),
    // поэтому навигацию внутри дашборда не перехватываем — no-op.
    func updateNSView(_ nsView: WKWebView, context: Context) {}
}
