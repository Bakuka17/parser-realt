# RealtyApp — SwiftUI-фронтенд для Python-парсера

Нативное macOS-приложение (SwiftUI, min macOS 13), GUI для `collect_realty.py` и `save_marked.py`.

## Открыть проект в Xcode

```bash
cd ~/realty_env/RealtyApp
xed Package.swift
```
Xcode откроет SPM-проект, автоматически подтянет зависимость `CoreXLSX` (первое разрешение пакетов — секунд 30-60). Затем ⌘R — собрать и запустить.

## Возможности

1. **Запуск сбора** (`collect_realty.py`) с опциями `--full`, `--sources`, `--city`, `--max-pages` через меню.
2. **Просмотр** `commercial_realty.xlsx` в нативной таблице, вкладки «Продажа» / «Аренда», поиск, сортировка, кликабельные ссылки.
3. **Чекбокс «✓»** в каждой строке — выделение объектов для сохранения (в памяти приложения).
4. **«Сохранить выбранное»** → запускает `save_marked.py --hashes ...`, который качает фото и считает гео-анализ через OSM.
5. **Вкладка «Сохранённые»** — таблица `saved_realty.xlsx` с фото, активностью локации и расстоянием до транспорта. Удаление выбранного.
6. **Лог-панель** внизу — стриминг stdout/stderr Python-процесса в реальном времени.

## Важное при сборке

**Отключи App Sandbox** для target в Xcode:
- Project → Signing & Capabilities → удали «App Sandbox» (или поставь None).
Иначе sandbox блокирует и запуск внешнего Python, и доступ к `~/realty_env/`.

## Настройки

Меню → **RealtyApp → Settings…** — путь к папке Python-проекта. По умолчанию `~/realty_env`. Можно указать произвольный путь.

## Архитектура

- `RealtyAppApp.swift` — точка входа, scene.
- `Models.swift` — `RealtyItem`, `SavedItem`, имена колонок.
- `AppState.swift` — `@MainActor ObservableObject`, держит все данные и состояние.
- `XLSXService.swift` — чтение `commercial_realty.xlsx` и `saved_realty.xlsx` через CoreXLSX.
- `ProcessRunner.swift` — запуск Python с стримингом вывода.
- `Settings.swift` — путь к папке Python через `UserDefaults`, валидация.
- `ContentView.swift` — главный экран, тулбар, переключатель вкладок.
- `MainTableView.swift` — таблица «Продажа»/«Аренда».
- `SavedView.swift` — таблица «Сохранённые», удаление.
- `LogPanel.swift` — лог-вывод парсера.

## Ограничения / Известное

- **CoreXLSX — только чтение.** Удаление сохранённых идёт через тонкий Python-помощник (генерируется в `/tmp/` и запускается через тот же venv).
- **Отметка «Сохранить»** в приложении — это in-memory выбор. Парсер не пишет «x» в xlsx; для save_marked используется флаг `--hashes`. Колонка «Сохранить» в Excel остаётся рабочей для тех, кто марикает вручную.
- **Без подписи** — для распространения «в облако» нужно подписать приложение Developer-сертификатом. Для личного использования достаточно собрать локально.
