// swift-tools-version: 5.9
// macOS-приложение: нативная оболочка (WKWebView) вокруг веб-дашборда обзвона.
// Само поднимает web/server.py и показывает его в окне. Открыть: cd RealtyApp && xed Package.swift
// Min macOS 13. Внешних зависимостей нет (UI = веб-дашборд).
import PackageDescription

let package = Package(
    name: "RealtyApp",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "RealtyApp", targets: ["RealtyApp"])
    ],
    targets: [
        .executableTarget(
            name: "RealtyApp",
            path: "Sources/RealtyApp"
        )
    ]
)
