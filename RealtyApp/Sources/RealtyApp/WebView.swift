// Нативная обёртка вокруг WKWebView — показывает локальный веб-дашборд.
import SwiftUI
import WebKit
import AppKit

struct WebView: NSViewRepresentable {
    let url: URL

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.defaultWebpagePreferences.allowsContentJavaScript = true
        // без персистентного кэша: дашборд меняется после «Обновить базу» — всегда свежий
        cfg.websiteDataStore = .nonPersistent()
        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.wantsLayer = true
        wv.navigationDelegate = context.coordinator
        wv.uiDelegate = context.coordinator
        wv.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
        return wv
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        // Ссылки target="_blank" (объект на сайте-источнике, Яндекс.Карты): WKWebView сам
        // новые окна не открывает — отправляем во внешний браузер по умолчанию.
        func webView(_ wv: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for navigationAction: WKNavigationAction,
                     windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let url = navigationAction.request.url { NSWorkspace.shared.open(url) }
            return nil
        }

        // Клики по внешним ссылкам без _blank — тоже в браузер; дашборд держим на localhost.
        func webView(_ wv: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if navigationAction.navigationType == .linkActivated,
               let url = navigationAction.request.url,
               let host = url.host, host != "localhost", host != "127.0.0.1" {
                NSWorkspace.shared.open(url)
                decisionHandler(.cancel)
                return
            }
            decisionHandler(.allow)
        }

        // WKWebView в SwiftUI порой не композитит контент после загрузки: вёрстка готова
        // (getBoundingClientRect корректен), но на экран не нарисована. Лёгкий сдвиг кадра
        // форсит перерисовку. Дважды (сразу и с задержкой) — вдруг SwiftUI ещё не выставил размер.
        func webView(_ wv: WKWebView, didFinish navigation: WKNavigation!) {
            let nudge = {
                let s = wv.frame.size
                guard s.width > 0, s.height > 0 else { return }
                wv.setFrameSize(NSSize(width: s.width, height: s.height + 1))
                wv.setFrameSize(s)
            }
            DispatchQueue.main.async(execute: nudge)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25, execute: nudge)
        }
    }
}
