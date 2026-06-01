// Модели данных. RealtyItem отражает строку в commercial_realty.xlsx.
// Имена колонок — точно как в Python (realty_parser_v8.COLUMNS).
import Foundation

/// Колонки, в том порядке, в каком их пишет Python (realty_parser_v8.COLUMNS).
/// Имена должны совпадать байт-в-байт с заголовками в xlsx (строка 2 листа).
enum Col {
    static let save        = "Сохранить"
    static let type        = "Тип"
    static let phone       = "Телефон"
    static let link        = "Ссылка"
    static let address     = "Адрес"
    static let district    = "Район / Город"
    static let area        = "Площадь, м²"
    static let priceTotal  = "Цена общая"
    static let pricePerM2  = "Цена за м²"
    static let vat         = "НДС"
    static let floor       = "Этаж / этажность"
    static let year        = "Год постройки"
    static let bClass      = "Класс здания"
    static let condition   = "Состояние"
    static let parking     = "Парковка"
    static let entrance    = "Отдельный вход"
    static let wetZone     = "Мокрая зона"
    static let contact     = "Контакт"
    static let contactName = "Имя контакта"
    static let pubDate     = "Дата публикации"
    static let source      = "Источник"
    static let ceiling     = "Высота потолков, м"
    static let ramp        = "Грузовая рампа / ворота"
    static let power       = "Электр. мощность, кВт"
    static let showcase    = "Витринные окна / 1-я линия"
    static let minRent     = "Мин. срок аренды"
    static let wallMat     = "Материал стен"
    static let photoURL    = "Фото URL"
    static let coords      = "Координаты"
    static let hash        = "Хэш"

    // дополнительные колонки saved_realty.xlsx
    static let photoFiles  = "Фото (файлы)"
    static let activity    = "Активность локации"
    static let poiNearby   = "POI рядом (300м)"
    static let toTransit   = "До транспорта, м"
}

/// Строка из commercial_realty.xlsx. Все поля — String для простоты.
struct RealtyItem: Identifiable, Hashable {
    /// id = хэш (стабильный между прогонами).
    var id: String { hash.isEmpty ? "\(source)|\(link)" : hash }

    var dealSheet: String           // "Продажа" | "Аренда" (имя листа)
    var raw: [String: String]       // все колонки как строки

    var type: String        { raw[Col.type] ?? "" }
    var phone: String       { raw[Col.phone] ?? "" }
    var link: String        { raw[Col.link] ?? "" }
    var address: String     { raw[Col.address] ?? "" }
    var district: String    { raw[Col.district] ?? "" }
    var area: String        { raw[Col.area] ?? "" }
    var priceTotal: String  { raw[Col.priceTotal] ?? "" }
    var phoneClean: String  { phone.replacingOccurrences(of: " ", with: "") }
    var pubDate: String     { raw[Col.pubDate] ?? "" }
    var source: String      { raw[Col.source] ?? "" }
    var photoURL: String    { raw[Col.photoURL] ?? "" }
    var coords: String      { raw[Col.coords] ?? "" }
    var hash: String        { raw[Col.hash] ?? "" }
    var savedMark: String   { raw[Col.save] ?? "" }

    /// Универсальный поиск по полям.
    func matches(_ query: String) -> Bool {
        if query.isEmpty { return true }
        let q = query.lowercased()
        for v in raw.values where v.lowercased().contains(q) { return true }
        return false
    }
}

/// Строка из saved_realty.xlsx (тот же RealtyItem + доп. поля).
struct SavedItem: Identifiable, Hashable {
    var id: String { hash.isEmpty ? UUID().uuidString : hash }
    var raw: [String: String]

    var type: String        { raw[Col.type] ?? "" }
    var address: String     { raw[Col.address] ?? "" }
    var priceTotal: String  { raw[Col.priceTotal] ?? "" }
    var phone: String       { raw[Col.phone] ?? "" }
    var link: String        { raw[Col.link] ?? "" }
    var photoFiles: String  { raw[Col.photoFiles] ?? "" }
    var activity: String    { raw[Col.activity] ?? "" }
    var toTransit: String   { raw[Col.toTransit] ?? "" }
    var hash: String        { raw[Col.hash] ?? "" }
}
