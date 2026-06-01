// Лог-панель: вывод stdout/stderr Python-процесса.
import SwiftUI

struct LogPanel: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 1) {
                    ForEach(Array(state.logLines.enumerated()), id: \.offset) { idx, line in
                        Text(line)
                            .font(.system(size: 11, weight: .regular, design: .monospaced))
                            .textSelection(.enabled)
                            .foregroundColor(line.hasPrefix("⚠️") ? .red :
                                             line.hasPrefix("▶︎") ? .accentColor : .primary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .id(idx)
                    }
                }
                .padding(.horizontal, 8).padding(.vertical, 4)
            }
            .background(Color(NSColor.textBackgroundColor))
            .onChange(of: state.logLines.count) { _ in
                if let last = state.logLines.indices.last {
                    withAnimation(.linear(duration: 0.05)) {
                        proxy.scrollTo(last, anchor: .bottom)
                    }
                }
            }
        }
    }
}
