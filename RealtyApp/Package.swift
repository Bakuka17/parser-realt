// swift-tools-version: 5.9
// macOS-приложение, фронтенд для Python-парсера коммерческой недвижимости.
// Открыть в Xcode: cd RealtyApp && xed Package.swift
// Min macOS 13. Зависимость: CoreXLSX (https://github.com/CoreOffice/CoreXLSX).
import PackageDescription

let package = Package(
    name: "RealtyApp",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "RealtyApp", targets: ["RealtyApp"])
    ],
    dependencies: [
        .package(url: "https://github.com/CoreOffice/CoreXLSX", from: "0.14.2"),
    ],
    targets: [
        .executableTarget(
            name: "RealtyApp",
            dependencies: [
                .product(name: "CoreXLSX", package: "CoreXLSX"),
            ],
            path: "Sources/RealtyApp"
        )
    ]
)
