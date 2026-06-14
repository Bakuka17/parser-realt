/* Консоль обзвона — клиентская логика (vanilla, без зависимостей). */
(() => {
  "use strict";

  const DATA = (window.LISTINGS || []).map((x, i) => ({ ...x, _i: i }));
  const META = window.META || {};
  const PAGE = 48;

  const ICON = {
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>',
    phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3-8.6A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.6a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.5-1.1a2 2 0 0 1 2.1-.5c.8.3 1.7.5 2.6.6a2 2 0 0 1 1.7 2Z"/></svg>',
    copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
    ext: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>',
    pin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>',
    building: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="1.5"/><path d="M9 8h.01M15 8h.01M9 12h.01M15 12h.01M9 16h.01M15 16h.01"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></svg>',
    save: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>',
    table: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/></svg>',
    chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 16v-4M12 16V8M17 16v-7"/></svg>',
    spinner: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.2-8.6"/></svg>',
    gavel: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m14 13-7.5 7.5a2.1 2.1 0 0 1-3-3L11 10"/><path d="m16 16 6-6"/><path d="m8 8 6-6"/><path d="m9 7 8 8"/><path d="m21 11-8-8"/></svg>',
  };

  const $ = (s) => document.querySelector(s);
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "");
  const nf = new Intl.NumberFormat("ru-RU");

  async function postJSON(path, body) {
    const r = await fetch(path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    return r.json();
  }
  const hasBackend = location.protocol.startsWith("http"); // file:// → API недоступен

  // Страницу открыли как файл (двойной клик по index.html / старая вкладка)?
  // Ищем работающий сервер и перепрыгиваем на него; иначе показываем баннер.
  async function findServer() {
    for (let p = 8765; p < 8775; p++) {
      try {
        const ctl = new AbortController();
        const t = setTimeout(() => ctl.abort(), 600);
        const r = await fetch(`http://localhost:${p}/api/ping`, { signal: ctl.signal });
        clearTimeout(t);
        if (r.ok && (await r.json()).app === "realty-dashboard") return p;
      } catch { /* порт молчит — пробуем следующий */ }
    }
    return null;
  }
  function showFileBanner() {
    if (document.querySelector(".notice")) return;
    const el = document.createElement("div");
    el.className = "notice";
    el.innerHTML = `<b>Страница открыта как файл — кнопки «Сохранить», «Excel» и
      «Обновить базу» не работают.</b> Запустите <b>Дашборд.command</b> двойным кликом
      (в папке realty_env): он поднимет сервер и откроет рабочую версию.
      <button type="button" class="reset" id="noticeClose">Понятно</button>`;
    document.body.prepend(el);
    el.querySelector("#noticeClose").addEventListener("click", () => el.remove());
  }
  if (!hasBackend) {
    findServer().then((p) => {
      if (p) location.replace(`http://localhost:${p}/index.html`);
      else showFileBanner();
    });
  }

  function plural(n, forms) {
    const a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return forms[2];
    if (b > 1 && b < 5) return forms[1];
    if (b === 1) return forms[0];
    return forms[2];
  }

  // ---------- state ----------
  const state = { q: "", deals: new Set(), city: "", type: "", source: "", sort: "date",
                  phoneOnly: false, photoOnly: false, auctionPast: false };
  let filtered = DATA;
  let shown = 0;
  const savedSet = new Set(); // хэши уже сохранённых (сервер знает; кнопка сразу зелёная)

  // ---------- facets ----------
  function facet(key) {
    const m = new Map();
    for (const x of DATA) {
      const v = x[key];
      if (v) m.set(v, (m.get(v) || 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }
  function fillSelect(id, entries, allLabel) {
    const sel = $("#" + id);
    sel.innerHTML =
      `<option value="">${allLabel}</option>` +
      entries.map(([v, n]) => `<option value="${esc(v)}">${esc(v)} (${nf.format(n)})</option>`).join("");
  }

  // ---------- filtering ----------
  function dateKey(s) {
    // "08.06.2026" -> 20260608 ; иначе 0
    const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(s || "");
    return m ? +(m[3] + m[2] + m[1]) : 0;
  }
  function apply() {
    const q = state.q.trim().toLowerCase();
    filtered = DATA.filter((x) => {
      if (state.deals.size && !state.deals.has(x.deal)) return false;
      if (state.city && x.city !== state.city) return false;
      if (state.type && x.type !== state.type) return false;
      if (state.source && x.source !== state.source) return false;
      if (state.phoneOnly && !x.phone) return false;
      if (state.photoOnly && !x.photo) return false;
      // аукционы: по умолчанию скрываем прошедшие (дата уже прошла)
      if (x.deal === "auction" && !state.auctionPast && x.future === false) return false;
      if (q) {
        const hay = (x.addr + " " + x.city + " " + x.type + " " + x.phone + " " +
                     x.source + " " + x.desc + " " + (x.title || "") + " " +
                     (x.org || "")).toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    const s = state.sort;
    filtered.sort((a, b) => {
      if (s === "usd_desc") return (b.usd || -1) - (a.usd || -1);
      if (s === "usd_asc") return (a.usd ?? Infinity) - (b.usd ?? Infinity);
      if (s === "area_desc") return (b.area || 0) - (a.area || 0);
      return dateKey(b.date) - dateKey(a.date);
    });
    render(true);
  }

  // ---------- rendering ----------
  const grid = $("#grid");
  function priceHtml(x) {
    if (x.usd != null) {
      const per = x.deal === "rent" ? '<span class="per">/мес</span>' : "";
      return `<b>$${nf.format(x.usd)}</b>${per}`;
    }
    if (x.price) return `<span class="noprice">${esc(x.price)}</span>`;
    return `<span class="noprice">Цена не указана</span>`;
  }
  function metaHtml(x) {
    const bits = [];
    if (x.area) bits.push(`${nf.format(x.area)} м²`);
    if (x.floor) bits.push(`эт. ${esc(x.floor)}`);
    if (x.date) bits.push(esc(x.date));
    return bits.map((b) => `<span>${b}</span>`).join("");
  }
  function fmtPhone(c) {
    // канон +375XXXXXXXXX -> +375 (29) 145-13-87; чужое/пустое отдаём как есть
    const m = /^\+375(\d\d)(\d{3})(\d{2})(\d{2})$/.exec(c || "");
    return m ? `+375 (${m[1]}) ${m[2]}-${m[3]}-${m[4]}` : (c || "");
  }
  function auctionCard(x) {
    const media = x.photo
      ? `<img src="${esc(x.photo)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="window.__imgFail(this)">`
      : `<div class="lead__ph">${ICON.gavel}<span>${esc(x.type || "Лот")}</span></div>`;
    const phone = x.phone ? x.phone.split(/[,;]/)[0].trim() : "";
    const callBtn = phone
      ? `<button type="button" class="btn btn--call" data-phone="${esc(phone)}" title="Скопировать ${esc(fmtPhone(phone))}">${ICON.copy}<span class="num">${esc(fmtPhone(phone))}</span></button>`
      : `<span class="btn btn--nophone">${ICON.gavel}торги через площадку</span>`;
    const url = safeUrl(x.url);
    const ext = url
      ? `<a class="btn btn--ghost btn--icon" href="${esc(url)}" target="_blank" rel="noopener noreferrer" title="Открыть лот на площадке" aria-label="Открыть лот">${ICON.ext}</a>` : "";
    const mapQ = (x.addr || x.city) ? `https://yandex.ru/maps/?text=${encodeURIComponent(((x.city || "") + " " + (x.addr || "")).trim())}` : "";
    const map = mapQ
      ? `<a class="btn btn--ghost btn--icon" href="${esc(mapQ)}" target="_blank" rel="noopener noreferrer" title="Открыть на Яндекс.Картах" aria-label="Карта">${ICON.pin}</a>` : "";
    const excel = `<button type="button" class="btn btn--ghost btn--icon btn--excel" data-hash="${esc(x.hash)}" title="Открыть в Excel (Аукционы, строка ${x.row || "?"})" aria-label="Открыть в Excel">${ICON.table}</button>`;
    const dateLine = x.date
      ? `<div class="auc-date${x.future === false ? " past" : ""}">${ICON.gavel}<span>${esc(x.date)}${x.future === false ? " · прошёл" : (x.future ? " · ожидается" : "")}</span></div>`
      : "";
    const bits = [];
    if (x.area) bits.push(`${nf.format(x.area)} м²`);
    if (x.deposit) bits.push(`задаток ${esc(x.deposit)}`);
    return `<article class="lead lead--auc" data-hash="${esc(x.hash)}">
      <div class="lead__media"><span class="badge badge--auction">Аукцион</span>${media}</div>
      <div class="lead__body">
        <div class="lead__top"><span class="lead__kind">${esc(x.type || "Лот")}</span>
          ${x.source ? `<span class="lead__src">${esc(x.source)}</span>` : ""}</div>
        ${x.title ? `<div class="auc-title">${esc(x.title)}</div>` : ""}
        <div class="lead__price">${x.price ? `<b>${esc(x.price)}</b>` : '<span class="noprice">Цена по запросу</span>'}</div>
        ${dateLine}
        <div class="lead__meta">${bits.map((b) => `<span>${b}</span>`).join("")}</div>
        <div class="lead__addr">${x.city ? `<span class="city">${esc(x.city)}</span>` : ""}${x.city && x.addr ? ", " : ""}${esc(x.addr)}${x.org ? ` · ${esc(x.org)}` : ""}</div>
      </div>
      <div class="lead__actions">${callBtn}</div>
      <div class="lead__actions2">${map}${ext}${excel}</div>
    </article>`;
  }

  function cardHtml(x) {
    if (x.deal === "auction") return auctionCard(x);
    const dealLabel = x.deal === "sale" ? "Продажа" : "Аренда";
    const media = x.photo
      ? `<img src="${esc(x.photo)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="window.__imgFail(this)">`
      : `<div class="lead__ph"${hasBackend && x.url ? ` data-lazyphoto="${esc(x.hash)}"` : ""}>${ICON.building}<span>${esc(x.type || "Объект")}</span></div>`;
    const phone = x.phone ? x.phone.split(/[,;]/)[0].trim() : "";
    const callBtn = phone
      ? `<button type="button" class="btn btn--call" data-phone="${esc(phone)}" title="Скопировать ${esc(fmtPhone(phone))}">
           ${ICON.copy}<span class="num">${esc(fmtPhone(phone))}</span></button>`
      : `<span class="btn btn--nophone">${ICON.phone}нет телефона</span>`;
    const url = safeUrl(x.url);
    const ext = url
      ? `<a class="btn btn--ghost btn--icon" href="${esc(url)}" target="_blank" rel="noopener noreferrer" title="Открыть первоисточник" aria-label="Открыть первоисточник">${ICON.ext}</a>`
      : "";
    // Яндекс.Карты: по координатам — метка; иначе поиск по адресу (карта есть почти у всех)
    let mapHref = "";
    if (x.coords) {
      mapHref = `https://yandex.ru/maps/?ll=${x.coords[1]},${x.coords[0]}&z=17&pt=${x.coords[1]},${x.coords[0]}`;
    } else if (x.addr || x.city) {
      // адрес realt уже содержит город ("г. Минск, …") → не дублируем; у kufar/megapolis добавляем
      const a = x.addr || "";
      const q = (!x.city || /(^|\s)(г\.|город|обл|р-н)/i.test(a)) ? (a || x.city) : `${x.city}, ${a}`;
      mapHref = `https://yandex.ru/maps/?text=${encodeURIComponent(q.trim())}`;
    }
    const map = mapHref
      ? `<a class="btn btn--ghost btn--icon" href="${esc(mapHref)}" target="_blank" rel="noopener noreferrer" title="Открыть на Яндекс.Картах" aria-label="Открыть на Яндекс.Картах">${ICON.pin}</a>`
      : "";
    const save = savedSet.has(x.hash)
      ? `<a class="btn btn--mini btn--saved" href="/saved/${esc(x.hash)}/index.html" target="_blank" rel="noopener" title="Открыть сохранённую копию">${ICON.check}<span>Сохранено</span></a>`
      : `<button type="button" class="btn btn--ghost btn--mini btn--save" data-hash="${esc(x.hash)}" title="Сохранить объявление офлайн (текст + фото)">${ICON.save}<span>Сохранить</span></button>`;
    const excel = `<button type="button" class="btn btn--ghost btn--icon btn--excel" data-hash="${esc(x.hash)}" title="Открыть в Excel (${esc(x.sheet || "")}, строка ${x.row || "?"})" aria-label="Открыть в Excel">${ICON.table}</button>`;
    const ana = `<button type="button" class="btn btn--ghost btn--mini btn--ana" data-hash="${esc(x.hash)}" title="Сравнить с похожими: цена/м², окупаемость">${ICON.chart}<span>Анализ</span></button>`;
    return `<article class="lead" data-hash="${esc(x.hash)}">
      <div class="lead__media"><span class="badge badge--${x.deal}">${dealLabel}</span>${media}</div>
      <div class="lead__body">
        <div class="lead__top"><span class="lead__kind">${esc(x.type || "—")}</span>
          ${x.source ? `<span class="lead__src">${esc(x.source)}</span>` : ""}</div>
        <div class="lead__price">${priceHtml(x)}</div>
        <div class="lead__meta">${metaHtml(x)}</div>
        <div class="lead__addr">${x.city ? `<span class="city">${esc(x.city)}</span>` : ""}${x.city && x.addr ? ", " : ""}${esc(x.addr)}</div>
      </div>
      <div class="lead__actions">${callBtn}</div>
      <div class="lead__actions2">${ana}${save}${excel}${map}${ext}</div>
    </article>`;
  }

  function render(reset) {
    if (reset) { grid.innerHTML = ""; shown = 0; }
    const total = filtered.length;
    $("#empty").hidden = total !== 0;
    grid.hidden = total === 0;
    const next = filtered.slice(shown, shown + PAGE);
    if (next.length) {
      grid.insertAdjacentHTML("beforeend", next.map(cardHtml).join(""));
      shown += next.length;
      hookLazyPhotos();
    }
    const word = plural(total, ["лид", "лида", "лидов"]);
    $("#count").innerHTML = total
      ? `Найдено <b>${nf.format(total)}</b> ${word}` +
        (shown < total ? ` · показано ${nf.format(shown)}` : "")
      : "";
    const dirty = state.q || state.deals.size || state.city || state.type ||
                  state.source || state.phoneOnly || state.photoOnly;
    $("#reset").hidden = !dirty;
  }

  // ---------- анализ объекта: сравнение с похожими (чистый JS на данных дашборда) ----------
  function median(nums) {
    const a = nums.filter((n) => n != null && isFinite(n)).sort((p, q) => p - q);
    if (!a.length) return null;
    const m = Math.floor(a.length / 2);
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }
  const ppmOf = (o) => (o.usd && o.area) ? o.usd / o.area : null;   // $/м² (у аренды — $/м²/мес)
  function totalAny(o) {            // числовой итог объекта: $ (usd) либо BYN из строки цены
    if (o.usd) return { v: o.usd, cur: "$" };
    if (o.price && /р/.test(o.price)) {
      const n = +o.price.split("р")[0].replace(/\D/g, "");   // цифры до «р.»
      if (n > 0) return { v: n, cur: "р." };
    }
    return null;
  }
  function kmDist(a, b) {                                           // расстояние по координатам [lat,lng]
    if (!a || !b) return null;
    const R = 6371, r = (d) => d * Math.PI / 180;
    const dLa = r(b[0] - a[0]), dLo = r(b[1] - a[1]);
    const h = Math.sin(dLa / 2) ** 2 + Math.cos(r(a[0])) * Math.cos(r(b[0])) * Math.sin(dLo / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  const TENANTS = {
    "Офис": "компании, ИТ, услуги, представительства, коворкинг",
    "Торговое": "магазин, кафе, аптека, салон красоты, пункт выдачи заказов",
    "Склад": "логистика, хранение, дистрибуция, e-commerce",
    "Производство": "лёгкое производство, мастерские, цех",
  };
  const tenantHint = (t) => TENANTS[t] || "розница, услуги, общепит или офис — зависит от локации и трафика";
  // нормы Минска для доходного метода (из методички): вакансия ~11%, операц. расходы ~30%, торг ~4%
  const VACANCY = 0.11, OPEX = 0.30, TORG = 0.04;

  // умная нормализация адреса: «г. Минск, ул. Кульман, 1/1» и «Кульман ул, 1к1, Минск» → одно
  const ADDR_NOISE = new Set(["г", "город", "обл", "область", "рн", "район", "ул", "улица",
    "пр", "проспект", "просп", "пер", "переулок", "пл", "площадь", "бр", "бульвар", "наб",
    "набережная", "ш", "шоссе", "д", "дом", "стр", "строение", "к", "корп", "корпус", "минск"]);
  function normAddr(s) {
    const a = (s || "").toLowerCase().replace(/(\d)\s*(?:\/|к|корп|корпус)\s*(\d)/g, "$1к$2");
    return a.split(/[^a-zа-я0-9]+/).filter((t) => t && !ADDR_NOISE.has(t)).sort().join("");
  }
  // дубль = ТОЧНОЕ совпадение адреса+площади+ЭТАЖА+цены. Разные единицы в одном доме
  // (другой этаж / другая точная площадь / другая цена) НЕ схлопываются — остаются обе.
  const dedupKey = (o) => `${normAddr(o.addr)}|${o.area}|${o.floor || ""}|${o.usd || o.price || ""}`;

  function comps(x, deal, tol) {  // похожие: та же сделка+тип+город, площадь ±tol; сам объект исключён
    if (!x.area) return [];
    const lo = x.area * (1 - tol), hi = x.area * (1 + tol);
    const list = DATA.filter((o) => o.hash !== x.hash && o.deal === deal && o.type === x.type &&
      o.city === x.city && o.area && o.area >= lo && o.area <= hi);
    // схлопнуть дубли (адрес+площадь+цена): один объект, разные источники → одна запись
    const seen = new Set(x.addr ? [dedupKey(x)] : []);   // исключаем и копии самого объекта
    return list.filter((o) => { const k = dedupKey(o); return seen.has(k) ? false : seen.add(k); });
  }

  function analyze(x) {
    const same = comps(x, x.deal, 0.25);
    const near = x.coords ? same.filter((o) => {
      const d = kmDist(x.coords, o.coords); return d != null && d <= 2;
    }) : [];
    let rate = null, gross = null, noi = null, capRate = null, payback = null, rentN = 0;
    if (x.deal === "sale" && x.usd && x.area) {       // доходность: ставка из похожих АРЕНДНЫХ
      const rc = comps(x, "rent", 0.35).map(ppmOf).filter((n) => n);
      rentN = rc.length; rate = median(rc);
      if (rate) {
        gross = rate * x.area * 12;                   // валовый годовой доход
        noi = gross * (1 - VACANCY) * (1 - OPEX);     // чистый (NOI): −вакансия −расходы
        capRate = noi / x.usd * 100;                  // доходность (cap rate), %
        payback = x.usd / noi;                        // окупаемость по NOI (честнее, чем по валу)
      }
    }
    return { x, same, near, ppmSelf: ppmOf(x), medCity: median(same.map(ppmOf)),
             medNear: median(near.map(ppmOf)), rate, gross, noi, capRate, payback, rentN };
  }

  function openAnalysis(btn) {
    const x = byHash.get(btn.dataset.hash);
    if (!x) return;
    $("#anaTitle").textContent =
      `Анализ: ${x.type || "объект"}${x.area ? ", " + nf.format(x.area) + " м²" : ""}`;
    $("#anaBody").innerHTML = analysisHtml(analyze(x));
    $("#anaModal").hidden = false;
  }

  function analysisHtml(a) {
    const x = a.x, money = (n) => n == null ? "—" : "$" + nf.format(Math.round(n));
    const head = (x.addr || x.city)
      ? `<div class="ana-self">${ICON.pin}<span>${esc(x.addr || x.city)}</span></div>` : "";
    const pos = (self, med) => {
      if (!self || !med) return "";
      const p = Math.round((self - med) / med * 100);
      const cls = p > 3 ? "up" : p < -3 ? "down" : "mid";
      const txt = p > 3 ? `на ${p}% дороже` : p < -3 ? `на ${-p}% дешевле` : "на уровне рынка";
      return `<span class="ana-pos ana-pos--${cls}">${txt}</span>`;
    };
    if (!x.area || !a.same.length) {
      return head + `<p class="ana-empty">Недостаточно похожих объектов для анализа${x.area ? "" : " (у объекта нет площади)"}.
        Сравнение работает там, где есть несколько объектов того же типа в том же городе.</p>`;
    }
    const unit = x.deal === "rent" ? "/м²/мес" : "/м²";
    const fmtCur = (v, cur) => cur === "$" ? "$" + nf.format(Math.round(v)) : nf.format(Math.round(v)) + " р.";
    const tot = totalAny(x);                                  // {v, cur} — $ или BYN
    const ppmSelf2 = (tot && x.area) ? tot.v / x.area : null; // цена/м² = итог ÷ площадь
    const sane = ppmSelf2 && (tot.cur === "$" ? ppmSelf2 < 30000 : ppmSelf2 < 100000); // отсечь битые
    const totalStr = tot ? fmtCur(tot.v, tot.cur) + (x.deal === "rent" ? "/мес" : "")
                         : (x.price || "цена не указана");
    const perM2 = sane ? ` · ${fmtCur(ppmSelf2, tot.cur)}${unit}` : "";
    const rows = [
      `<div class="ana-row"><span>Цена этого объекта</span><b>${esc(totalStr)}${perM2}</b></div>`,
      `<div class="ana-row"><span>Медиана по городу (${esc(x.city)}) · ${a.same.length} похож.</span>
        <b>${money(a.medCity)}${unit} ${pos(a.ppmSelf, a.medCity)}</b></div>`,
    ];
    if (a.near.length) rows.push(
      `<div class="ana-row"><span>Рядом (≤2 км) · ${a.near.length}</span>
        <b>${money(a.medNear)}${unit} ${pos(a.ppmSelf, a.medNear)}</b></div>`);
    if (x.deal === "sale" && tot) rows.push(
      `<div class="ana-row"><span>Ориентир с торгом (−${Math.round(TORG * 100)}%)</span>
        <b>${fmtCur(tot.v * (1 - TORG), tot.cur)}</b></div>`);

    let invest = "";
    if (x.deal === "sale") {
      invest = a.payback
        ? `<div class="ana-box ana-box--invest">
            <div class="ana-box__t">Если сдавать в аренду</div>
            <div class="ana-row"><span>Ожидаемая ставка</span><b>${money(a.rate)}/м²/мес</b></div>
            <div class="ana-row"><span>Валовый доход</span><b>${money(a.gross)}/год</b></div>
            <div class="ana-row"><span>Чистый доход (NOI)</span><b>${money(a.noi)}/год</b></div>
            <div class="ana-row"><span>Доходность (cap rate)</span><b class="ana-big">${a.capRate.toFixed(1)}%</b></div>
            <div class="ana-row"><span>Окупаемость</span><b class="ana-big">${a.payback.toFixed(1)} лет</b></div>
            <div class="ana-note">NOI — оценка: −вакансия 11%, −расходы 30% (нормы Минска); по ${a.rentN} аренд. аналогам.</div>
          </div>`
        : `<div class="ana-box"><div class="ana-note">Доходность: мало похожих арендных объектов для оценки ставки.</div></div>`;
    }
    const tenants = `<div class="ana-box">
      <div class="ana-box__t">Вероятные арендаторы</div>
      <div class="ana-tenants">${esc(tenantHint(x.type))}</div>
      <div class="ana-note">базовая подсказка по типу; «умную» оценку с учётом локации добавим в v2</div></div>`;

    const top = a.same.slice()
      .sort((p, q) => Math.abs(p.area - x.area) - Math.abs(q.area - x.area)).slice(0, 5);
    const list = top.map((o) => {
      const u = safeUrl(o.url);
      const name = `${esc(o.type || "")}, ${nf.format(o.area)} м²`;
      const addr = esc(o.addr || o.city || "");
      const nameHtml = u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${name}</a>` : name;
      return `<li><span class="ana-an">${nameHtml}${addr ? `<span class="ana-addr">${addr}</span>` : ""}</span>
        <b>${money(ppmOf(o))}${unit}</b></li>`;
    }).join("");

    return head + `<div class="ana-rows">${rows.join("")}</div>${invest}${tenants}
      <div class="ana-box"><div class="ana-box__t">Ближайшие аналоги</div>
      <ul class="ana-list">${list}</ul></div>`;
  }

  window.__imgFail = (img) => {
    const m = img.closest(".lead__media");
    if (m) m.innerHTML = m.querySelector(".badge").outerHTML +
      `<div class="lead__ph">${ICON.building}<span>фото недоступно</span></div>`;
  };

  // ---------- ленивые превью (realt не отдаёт фото в листинге) ----------
  const byHash = new Map(DATA.map((x) => [x.hash, x]));
  const photoIO = hasBackend
    ? new IntersectionObserver((ents) => {
        for (const en of ents) {
          if (!en.isIntersecting) continue;
          photoIO.unobserve(en.target);
          lazyPhoto(en.target);
        }
      }, { rootMargin: "400px" })
    : null;

  function hookLazyPhotos() {
    if (!photoIO) return;
    grid.querySelectorAll("[data-lazyphoto]:not([data-obs])").forEach((el) => {
      el.dataset.obs = "1";
      photoIO.observe(el);
    });
  }

  async function lazyPhoto(el) {
    const hash = el.dataset.lazyphoto;
    let res = null;
    try { res = await (await fetch(`/api/photo?hash=${encodeURIComponent(hash)}`)).json(); }
    catch { /* сервер занят/упал — оставим заглушку */ }
    const item = byHash.get(hash);
    if (res && res.ok && res.photo) {
      if (item) item.photo = res.photo;     // повторный рендер покажет сразу
      const media = el.closest(".lead__media");
      if (media) {
        const badge = media.querySelector(".badge");
        media.innerHTML = (badge ? badge.outerHTML : "") +
          `<img src="${esc(res.photo)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="window.__imgFail(this)">`;
      }
    } else {
      const label = el.querySelector("span");
      if (label) label.textContent = "фото недоступно";
    }
  }

  // действия на карточке: копировать телефон / сохранить / в Excel
  grid.addEventListener("click", async (e) => {
    const call = e.target.closest(".btn--call");
    if (call) return copyPhone(call);
    const save = e.target.closest(".btn--save");
    if (save) return saveAd(save);
    const excel = e.target.closest(".btn--excel");
    if (excel) return revealExcel(excel);
    const ana = e.target.closest(".btn--ana");
    if (ana) return openAnalysis(ana);
  });

  async function copyPhone(btn) {
    const num = btn.dataset.phone;
    try { await navigator.clipboard.writeText(num); }
    catch { /* clipboard может быть недоступен на file:// — всё равно показываем */ }
    const span = btn.querySelector(".num");
    const orig = span.textContent;
    btn.classList.add("copied");
    btn.firstChild.replaceWith(buildIcon("check"));
    span.textContent = "Скопировано";
    toast("Телефон скопирован: " + fmtPhone(num));
    setTimeout(() => {
      btn.classList.remove("copied");
      btn.firstChild.replaceWith(buildIcon("copy"));
      span.textContent = orig;
    }, 1500);
  }

  async function saveAd(btn) {
    if (!hasBackend) return toast("Откройте дашборд через Дашборд.command (нужен сервер)");
    if (btn.dataset.busy) return;
    btn.dataset.busy = "1";
    const label = btn.querySelector("span");
    const orig = label.textContent;
    btn.firstChild.replaceWith(spinIcon());
    label.textContent = "Сохраняю…";
    try {
      const res = await postJSON("/api/save", { hash: btn.dataset.hash });
      btn.querySelector("svg").replaceWith(buildIcon(res.ok ? "check" : "save"));
      if (res.url) {
        savedSet.add(btn.dataset.hash);
        // превратим кнопку в ссылку «Открыть сохранённое»
        const a = document.createElement("a");
        a.className = "btn btn--mini btn--saved";
        a.href = res.url; a.target = "_blank"; a.rel = "noopener";
        a.title = "Открыть сохранённую копию";
        a.innerHTML = ICON.check + "<span>Сохранено</span>";
        btn.replaceWith(a);
        toast(res.ok
          ? `Сохранено: ${res.photos} фото, текст ${res.textLen} симв.`
          : `Сохранено частично: ${res.error || "источник за антиботом"}`);
      } else {
        label.textContent = orig; btn.querySelector("svg").replaceWith(buildIcon("save"));
        toast("Не удалось сохранить: " + (res.error || "ошибка"));
      }
    } catch (err) {
      label.textContent = orig; toast("Ошибка сохранения: " + err.message);
    } finally { delete btn.dataset.busy; }
  }

  async function revealExcel(btn) {
    if (!hasBackend) return toast("Откройте дашборд через Дашборд.command (нужен сервер)");
    btn.classList.add("busy");
    try {
      const res = await postJSON("/api/reveal", { hash: btn.dataset.hash });
      toast(res.ok
        ? `Открыто в Excel: ${res.sheet}, строка ${res.row}` + (res.note ? ` (${res.note})` : "")
        : "Не получилось: " + (res.error || "ошибка"));
    } catch (err) { toast("Ошибка: " + err.message); }
    finally { setTimeout(() => btn.classList.remove("busy"), 400); }
  }

  function spinIcon() { const i = buildIcon("spinner"); i.classList.add("spin"); return i; }
  function buildIcon(name) {
    const t = document.createElement("template");
    t.innerHTML = ICON[name];
    return t.content.firstChild;
  }

  // toast
  let toastT;
  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg; el.hidden = false;
    requestAnimationFrame(() => el.classList.add("show"));
    clearTimeout(toastT);
    toastT = setTimeout(() => {
      el.classList.remove("show");
      setTimeout(() => (el.hidden = true), 220);
    }, 1600);
  }

  // ---------- wire up ----------
  function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

  function init() {
    // stats
    const tot = META.total || DATA.length;
    $("#meta-line").textContent =
      `${nf.format(tot)} ${plural(tot, ["объект", "объекта", "объектов"])} · обновлено ${META.generated || "—"}`;
    $("#stats").innerHTML = [
      ["Всего", META.total], ["С телефоном", META.withPhone], ["С фото", META.withPhoto],
    ].filter(([, v]) => v != null)
      .map(([k, v]) => `<div><dt>${k}</dt><dd>${nf.format(v)}</dd></div>`).join("");

    // icons in static markup
    document.querySelectorAll("[data-icon]").forEach((n) => (n.innerHTML = ICON[n.dataset.icon] || ""));

    // facets
    fillSelect("city", facet("city"), "Все города");
    fillSelect("type", facet("type"), "Все типы");
    fillSelect("source", facet("source"), "Все источники");

    // events
    $("#q").addEventListener("input", debounce((e) => { state.q = e.target.value; apply(); }, 130));
    ["city", "type", "source", "sort"].forEach((id) =>
      $("#" + id).addEventListener("change", (e) => { state[id] = e.target.value; apply(); }));
    $("#phoneOnly").addEventListener("change", (e) => { state.phoneOnly = e.target.checked; apply(); });
    $("#photoOnly").addEventListener("change", (e) => { state.photoOnly = e.target.checked; apply(); });
    $("#auctionPast").addEventListener("change", (e) => { state.auctionPast = e.target.checked; apply(); });

    document.querySelectorAll(".dealChk").forEach((cb) => {
      cb.checked = false;  // старт: ничего не выбрано = показаны все сделки (WebKit иначе восстанавливает)
      cb.addEventListener("change", () => {
        if (cb.checked) state.deals.add(cb.value); else state.deals.delete(cb.value);
        $("#pastWrap").hidden = !state.deals.has("auction");  // «прошедшие» — только когда выбраны аукционы
        apply();
      });
    });

    function reset() {
      Object.assign(state, { q: "", city: "", type: "", source: "",
                             sort: "date", phoneOnly: false, photoOnly: false, auctionPast: false });
      state.deals.clear();
      $("#q").value = ""; $("#city").value = ""; $("#type").value = "";
      $("#source").value = ""; $("#sort").value = "date";
      $("#phoneOnly").checked = false; $("#photoOnly").checked = false;
      $("#auctionPast").checked = false; $("#pastWrap").hidden = true;
      document.querySelectorAll(".dealChk").forEach((cb) => (cb.checked = false));
      apply();
    }
    $("#reset").addEventListener("click", reset);
    $("#reset2").addEventListener("click", reset);
    $("#anaClose").addEventListener("click", () => { $("#anaModal").hidden = true; });
    $("#anaModal").addEventListener("click", (e) => { if (e.target === $("#anaModal")) $("#anaModal").hidden = true; });

    // infinite scroll
    new IntersectionObserver((ents) => {
      if (ents[0].isIntersecting && shown < filtered.length) render(false);
    }, { rootMargin: "600px" }).observe($("#sentinel"));

    wireUpdate();

    // подсветить уже сохранённые (сервер хранит их в web/saved/)
    if (hasBackend) {
      fetch("/api/saved").then((r) => r.json()).then((d) => {
        (d.hashes || []).forEach((h) => savedSet.add(h));
        if (savedSet.size) render(true);
      }).catch(() => {});
    }

    apply();
  }

  // ---------- обновление базы ----------
  function wireUpdate() {
    const modal = $("#updModal"), log = $("#updLog"), spin = $("#updSpin");
    const stop = $("#updStop"), close = $("#updClose"), btn = $("#btnUpdate");
    let poll = null, doneReload = false;

    const open = () => { modal.hidden = false; };
    close.addEventListener("click", () => { modal.hidden = true; });
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.hidden = true; });

    async function tick() {
      let s;
      try { s = await (await fetch("/api/update/status")).json(); }
      catch { return; }
      log.textContent = s.log || "";
      log.scrollTop = log.scrollHeight;
      spin.hidden = !s.running;
      stop.hidden = !s.running;
      btn.disabled = s.running;
      if (!s.running && poll) {
        clearInterval(poll); poll = null;
        if (doneReload) {
          doneReload = false;
          toast("База обновлена — перезагружаю данные…");
          setTimeout(() => location.reload(), 1200);
        }
      }
    }

    btn.addEventListener("click", async () => {
      if (!hasBackend) return toast("Запустите дашборд через Дашборд.command (нужен сервер)");
      open();
      const res = await postJSON("/api/update", {});
      if (res.error) { toast(res.error); }
      doneReload = true;
      if (!poll) poll = setInterval(tick, 1500);
      tick();
    });

    stop.addEventListener("click", async () => {
      await postJSON("/api/update/stop", {});
      toast("Останавливаю…");
    });

    // если обновление уже шло (страницу открыли заново) — подхватим статус
    if (hasBackend) {
      fetch("/api/update/status").then((r) => r.json()).then((s) => {
        if (s.running) { open(); doneReload = true; poll = setInterval(tick, 1500); tick(); }
      }).catch(() => {});
    }
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", init);
  else init();
})();
