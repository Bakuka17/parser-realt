// Запуск внешнего процесса (Python) со стримингом stdout/stderr.
// Поток вывода — построчно, через AsyncStream, для отображения в LogPanel.
import Foundation

actor ProcessRunner {

    /// Один запуск процесса. Возвращает поток строк лога + exit code.
    /// Очень важно: при .terminate() корректно завершается.
    static func run(executable: URL, arguments: [String], cwd: URL,
                    onLine: @escaping @Sendable (String) -> Void) async -> Int32 {

        let process = Process()
        process.executableURL = executable
        process.arguments = arguments
        process.currentDirectoryURL = cwd
        // Пробрасываем PATH и базовые env, чтобы Python нашёл бинари.
        process.environment = ProcessInfo.processInfo.environment

        let outPipe = Pipe()
        let errPipe = Pipe()
        process.standardOutput = outPipe
        process.standardError = errPipe

        // Накопитель «полу-строки» (читаем чанками — последний кусок может быть без \n).
        actor LineBuf {
            private var buf = ""
            func feed(_ chunk: String, _ emit: (String) -> Void) {
                buf += chunk
                while let nl = buf.firstIndex(of: "\n") {
                    let line = String(buf[buf.startIndex..<nl])
                    buf.removeSubrange(buf.startIndex...nl)
                    emit(line)
                }
            }
            func flush(_ emit: (String) -> Void) {
                if !buf.isEmpty { emit(buf); buf = "" }
            }
        }
        let outBuf = LineBuf()
        let errBuf = LineBuf()

        outPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            if let s = String(data: data, encoding: .utf8) {
                Task { await outBuf.feed(s) { onLine($0) } }
            }
        }
        errPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            if let s = String(data: data, encoding: .utf8) {
                Task { await errBuf.feed(s) { onLine("⚠️ " + $0) } }
            }
        }

        do {
            try process.run()
        } catch {
            onLine("✖ Не удалось запустить процесс: \(error.localizedDescription)")
            return -1
        }

        // Ждём завершения в фоне.
        return await withCheckedContinuation { (cont: CheckedContinuation<Int32, Never>) in
            process.terminationHandler = { p in
                // Очищаем хвосты буферов.
                outPipe.fileHandleForReading.readabilityHandler = nil
                errPipe.fileHandleForReading.readabilityHandler = nil
                Task {
                    await outBuf.flush { onLine($0) }
                    await errBuf.flush { onLine("⚠️ " + $0) }
                    cont.resume(returning: p.terminationStatus)
                }
            }
        }
    }
}
