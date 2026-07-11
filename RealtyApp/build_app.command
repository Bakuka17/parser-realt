#!/bin/bash
# Пересобрать RealtyApp.app (release) после правок кода — двойной клик по этому файлу.
# Делает: swift build -c release → бандл dist/RealtyApp.app (иконка, Info.plist) → ad-hoc подпись.
set -e
cd "$(dirname "$0")"

echo "1/4  Сборка (release)…"
swift build -c release

BIN=".build/release/RealtyApp"
APP="dist/RealtyApp.app"

echo "2/4  Сборка бандла…"
rm -rf dist && mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/RealtyApp"
[ -f AppIcon.icns ] && cp AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>               <string>Axis</string>
  <key>CFBundleDisplayName</key>        <string>Axis</string>
  <key>CFBundleIdentifier</key>         <string>by.realty.dashboard</string>
  <key>CFBundleExecutable</key>         <string>RealtyApp</string>
  <key>CFBundlePackageType</key>        <string>APPL</string>
  <key>CFBundleShortVersionString</key> <string>1.0</string>
  <key>CFBundleVersion</key>            <string>1</string>
  <key>LSMinimumSystemVersion</key>     <string>13.0</string>
  <key>NSHighResolutionCapable</key>    <true/>
  <key>LSApplicationCategoryType</key>  <string>public.app-category.business</string>
  <key>CFBundleIconFile</key>           <string>AppIcon</string>
  <!-- управление Excel (кнопка «Excel» на карточке дёргает AppleScript) -->
  <key>NSAppleEventsUsageDescription</key>
  <string>Приложение открывает строку объекта в Microsoft Excel.</string>
  <!-- localhost-сервер + удалённые фото в WKWebView (как в Safari) -->
  <key>NSAppTransportSecurity</key>
  <dict>
    <key>NSAllowsLocalNetworking</key>          <true/>
    <key>NSAllowsArbitraryLoadsInWebContent</key> <true/>
  </dict>
</dict>
</plist>
PLIST

echo "3/4  Подпись (ad-hoc)…"
codesign --force --deep -s - "$APP" >/dev/null 2>&1

echo "4/4  Готово: $APP"
echo "    Запуск:  open '$PWD/$APP'"
echo "    Установить: перетащи dist/RealtyApp.app в «Программы»."
