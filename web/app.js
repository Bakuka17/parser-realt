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
  const state = { q: "", deals: new Set(), city: new Set(), type: new Set(), source: new Set(),
                  sort: "date", auctionPast: false, areaMin: null, areaMax: null, ownersOnly: false };
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
  // мультиселект: кнопка + попап с чекбоксами; пустой выбор = «все»
  const MSELS = [];
  function makeMulti(id, key, entries, allLabel) {
    const root = $("#" + id), btn = root.querySelector(".msel__btn"),
          pop = root.querySelector(".msel__pop"), sel = state[key];
    pop.innerHTML =
      `<button type="button" class="msel__all">${esc(allLabel)}</button>` +
      entries.map(([v, n]) =>
        `<label class="msel__opt"><input type="checkbox" value="${esc(v)}"><span>${esc(v)}</span><i>${nf.format(n)}</i></label>`).join("");
    const relabel = () => {
      const a = [...sel];
      btn.textContent = !a.length ? allLabel : a.length === 1 ? a[0] : `${a[0]} +${a.length - 1}`;
      btn.classList.toggle("on", a.length > 0);
    };
    const clear = () => {
      sel.clear();
      pop.querySelectorAll("input").forEach((c) => (c.checked = false));
      relabel();
    };
    pop.addEventListener("change", (e) => {
      if (e.target.checked) sel.add(e.target.value); else sel.delete(e.target.value);
      relabel(); apply();
    });
    pop.querySelector(".msel__all").addEventListener("click", () => { clear(); apply(); });
    btn.addEventListener("click", () => {
      const willOpen = pop.hidden;
      closeMsels();
      pop.hidden = !willOpen;
      btn.setAttribute("aria-expanded", String(willOpen));
    });
    MSELS.push({ pop, btn, clear });
    relabel();
  }
  function closeMsels() {
    MSELS.forEach((m) => { m.pop.hidden = true; m.btn.setAttribute("aria-expanded", "false"); });
  }
  document.addEventListener("click", (e) => { if (!e.target.closest(".msel")) closeMsels(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMsels(); });

  // ---------- filtering ----------
  function dateKey(s) {
    // "08.06.2026" -> 20260608 ; иначе 0
    const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(s || "");
    return m ? +(m[3] + m[2] + m[1]) : 0;
  }
  function apply() {
    const q = state.q.trim().toLowerCase();
    filtered = DATA.filter((x) => {
      if (state.deals.size && !state.deals.has(x.deal)) {
        // «За 1 БВ» — виртуальный сегмент: аукционы госимущества с ценой в 1 базовую
        const onebv = state.deals.has("onebv") && x.deal === "auction" && (x.dealKind || "").includes("1 БВ");
        if (!onebv) return false;
      }
      if (state.city.size && !state.city.has(x.city)) return false;
      if (state.type.size && !state.type.has(x.type)) return false;
      if (state.source.size && !state.source.has(x.source)) return false;
      if (state.areaMin != null && !(x.area >= state.areaMin)) return false;
      if (state.areaMax != null && !(x.area <= state.areaMax)) return false;
      // аукционы: по умолчанию скрываем прошедшие (дата уже прошла)
      if (x.deal === "auction" && !state.auctionPast && x.future === false) return false;
      // «Только собственники»: прячем агентства (who='agency'). owner/gov/'' (не размечено) — показываем.
      if (state.ownersOnly && x.who === "agency") return false;
      if (q) {
        const hay = (x.addr + " " + x.city + " " + x.type + " " + x.phone + " " +
                     x.source + " " + x.desc + " " + (x.title || "") + " " +
                     (x.org || "") + " " + (x.dealKind || "")).toLowerCase();
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
  // бейдж изменения цены (из price_history.json через export_data)
  function pchHtml(x) {
    if (!x.pch) return "";
    const down = x.pch.dir === "down";
    return `<span class="pch ${down ? "pch--down" : "pch--up"}" title="Было: ${esc(x.pch.old)} · изменение ${esc(x.pch.date)}">${down ? "↓ цена снижена" : "↑ цена выросла"}</span>`;
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
  // Фото карточки. С бэкендом — всегда через /img?hash (локальный сервер: полноразмер,
  // докачивает и кэширует на диск; не зависит от бел-CDN/VPN, нет недогруза/«обрезки»).
  // Без бэкенда (file://) — прямой CDN-URL из данных или плейсхолдер.
  function photoTag(x, icon, label) {
    if (hasBackend) {
      return `<img src="/img?hash=${esc(x.hash)}" alt="" loading="lazy" decoding="async" onerror="window.__imgFail(this)">`;
    }
    return x.photo
      ? `<img src="${esc(x.photo)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="window.__imgFail(this)">`
      : `<div class="lead__ph">${icon}<span>${esc(x.type || label)}</span></div>`;
  }

  function addrHtml(x) {
    // город не показываем отдельно, если он уже в начале/внутри адреса (гос-лоты: «Гомельская область, Гомельская область, …»)
    const dup = x.city && (x.addr || "").toLowerCase().includes(x.city.toLowerCase());
    const showCity = x.city && !dup;
    return `${showCity ? `<span class="city">${esc(x.city)}</span>` : ""}${showCity && x.addr ? ", " : ""}${esc(x.addr)}`;
  }

  function auctionCard(x) {
    const media = photoTag(x, ICON.gavel, "Лот");
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
      <div class="lead__media"><span class="badge badge--auction">${esc(x.dealKind && x.dealKind.includes("1 БВ") ? "За 1 БВ" : x.dealKind && x.dealKind.includes("Аренда") ? x.dealKind : "Аукцион")}</span>${media}</div>
      <div class="lead__body">
        <div class="lead__top"><span class="lead__kind">${esc(x.type || "Лот")}</span>
          ${x.source ? `<span class="lead__src">${esc(x.source)}</span>` : ""}</div>
        ${x.title ? `<div class="auc-title">${esc(x.title)}</div>` : ""}
        <div class="lead__price">${x.price ? `<b>${esc(x.price)}</b>` : '<span class="noprice">Цена по запросу</span>'}</div>
        ${dateLine}
        <div class="lead__meta">${bits.map((b) => `<span>${b}</span>`).join("")}</div>
        <div class="lead__addr">${addrHtml(x)}${x.org ? ` · ${esc(x.org)}` : ""}</div>
      </div>
      <div class="lead__actions">${callBtn}</div>
      <div class="lead__actions2">${map}${ext}${excel}</div>
    </article>`;
  }

  function belretailCard(x) {
    const phone = x.phone ? x.phone.split(/[,;]/)[0].trim() : "";
    const callBtn = phone
      ? `<button type="button" class="btn btn--call" data-phone="${esc(phone)}" title="Скопировать ${esc(fmtPhone(phone))}">${ICON.copy}<span class="num">${esc(fmtPhone(phone))}</span></button>`
      : `<span class="btn btn--nophone">${ICON.phone}нет телефона</span>`;
    const url = safeUrl(x.url);
    const ext = url
      ? `<a class="btn btn--ghost btn--icon" href="${esc(url)}" target="_blank" rel="noopener noreferrer" title="Открыть на belretail" aria-label="Открыть на belretail">${ICON.ext}</a>` : "";
    return `<article class="lead lead--company" data-hash="${esc(x.hash)}">
      <div class="lead__body">
        <div class="lead__top"><span class="lead__kind">${esc(x.type || "Компания")}</span>
          <span class="lead__src">belretail.by</span></div>
        <div class="company-name">${esc(x.title || "—")}</div>
      </div>
      <div class="lead__actions">${callBtn}</div>
      <div class="lead__actions2">${ext}</div>
    </article>`;
  }

  function bankCard(x) {
    const media = photoTag(x, ICON.building, "Объект");
    const phone = x.phone ? x.phone.split(/[,;]/)[0].trim() : "";
    const callBtn = phone
      ? `<button type="button" class="btn btn--call" data-phone="${esc(phone)}" title="Скопировать ${esc(fmtPhone(phone))}">${ICON.copy}<span class="num">${esc(fmtPhone(phone))}</span></button>`
      : `<span class="btn btn--nophone">${ICON.phone}нет телефона</span>`;
    const url = safeUrl(x.url);
    const ext = url
      ? `<a class="btn btn--ghost btn--icon" href="${esc(url)}" target="_blank" rel="noopener noreferrer" title="Открыть на сайте банка" aria-label="Открыть на сайте банка">${ICON.ext}</a>` : "";
    const mapQ = (x.addr || x.city) ? `https://yandex.ru/maps/?text=${encodeURIComponent(((x.city || "") + " " + (x.addr || "")).trim())}` : "";
    const map = mapQ
      ? `<a class="btn btn--ghost btn--icon" href="${esc(mapQ)}" target="_blank" rel="noopener noreferrer" title="Открыть на Яндекс.Картах" aria-label="Карта">${ICON.pin}</a>` : "";
    const bits = [];
    if (x.area) bits.push(`${nf.format(x.area)} м²`);
    return `<article class="lead lead--auc" data-hash="${esc(x.hash)}">
      <div class="lead__media"><span class="badge badge--bank">Банк</span>${media}</div>
      <div class="lead__body">
        <div class="lead__top"><span class="lead__kind">${esc(x.type || "Объект")}</span>
          ${x.source ? `<span class="lead__src">${esc(x.source)}</span>` : ""}</div>
        ${x.title ? `<div class="auc-title">${esc(x.title)}</div>` : ""}
        <div class="lead__price">${x.price ? `<b>${esc(x.price)}</b>` : '<span class="noprice">Цена по запросу</span>'}</div>
        <div class="lead__meta">${bits.map((b) => `<span>${b}</span>`).join("")}</div>
        <div class="lead__addr">${addrHtml(x)}</div>
      </div>
      <div class="lead__actions">${callBtn}</div>
      <div class="lead__actions2">${map}${ext}</div>
    </article>`;
  }

  function cardHtml(x) {
    if (x.deal === "auction") return auctionCard(x);
    if (x.deal === "belretail") return belretailCard(x);
    if (x.deal === "bank") return bankCard(x);
    const dealLabel = x.deal === "sale" ? "Продажа" : "Аренда";
    const media = photoTag(x, ICON.building, "Объект");
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
        <div class="lead__price">${priceHtml(x)}${pchHtml(x)}</div>
        <div class="lead__meta">${metaHtml(x)}</div>
        <div class="lead__addr">${addrHtml(x)}</div>
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
    }
    const word = plural(total, ["лид", "лида", "лидов"]);
    $("#count").innerHTML = total
      ? `Найдено <b>${nf.format(total)}</b> ${word}` +
        (shown < total ? ` · показано ${nf.format(shown)}` : "")
      : "";
    const dirty = state.q || state.deals.size || state.city.size || state.type.size ||
                  state.source.size || state.areaMin != null || state.areaMax != null;
    $("#reset").hidden = !dirty;
  }

  // ---------- анализ объекта: сравнение с похожими (чистый JS на данных дашборда) ----------
  function quantile(nums, q) {
    const a = nums.filter((n) => n != null && isFinite(n)).sort((p, w) => p - w);
    if (!a.length) return null;
    const i = (a.length - 1) * q, f = Math.floor(i);
    return a[f] + ((a[f + 1] ?? a[f]) - a[f]) * (i - f);
  }
  const median = (nums) => quantile(nums, 0.5);
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
  // дубль = совпадение адреса+точной площади. Этаж и цена в ключ НЕ входят: источники
  // заполняют этаж по-разному (realt «3/4», kufar пусто), а тот же объект с потерянной
  // ценой — один объект. Разные единицы в доме различаются точной площадью.
  const dedupKey = (o) => `${normAddr(o.addr)}|${o.area}`;

  function comps(x, deal, tol) {  // похожие: та же сделка+тип+город, площадь ±tol; сам объект исключён
    if (!x.area) return [];
    const lo = x.area * (1 - tol), hi = x.area * (1 + tol);
    const [pLo, pHi] = deal === "rent" ? [0.5, 200] : [50, 20000];  // санити $/м²: битые цены — вон
    const list = DATA.filter((o) => {
      if (o.hash === x.hash || o.deal !== deal || o.type !== x.type || o.city !== x.city) return false;
      if (!o.area || o.area < lo || o.area > hi) return false;
      const p = ppmOf(o);
      return p == null || (p >= pLo && p <= pHi);
    });
    // схлопнуть дубли: с ценой — вперёд, чтобы при схлопывании выживала запись с ценой
    list.sort((p, q) => (q.usd != null) - (p.usd != null));
    const seen = new Set(x.addr ? [dedupKey(x)] : []);   // исключаем и копии самого объекта
    return list.filter((o) => { const k = dedupKey(o); return seen.has(k) ? false : seen.add(k); });
  }

  function analyze(x) {
    let tol = 0.25;
    let same = comps(x, x.deal, tol);
    if (same.length < 6) { tol = 0.5; same = comps(x, x.deal, tol); }  // мало аналогов → шире допуск
    const near = x.coords ? same.filter((o) => {
      const d = kmDist(x.coords, o.coords); return d != null && d <= 3;
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
    const ppms = same.map(ppmOf);
    return { x, same, near, tol, ppmSelf: ppmOf(x), medCity: median(ppms),
             p25: quantile(ppms, 0.25), p75: quantile(ppms, 0.75),
             medNear: median(near.map(ppmOf)), rate, gross, noi, capRate, payback, rentN };
  }

  let anaCur = null, anaStats = null;   // текущий объект модалки — гео/вердикт приходят асинхронно

  function openAnalysis(btn) {
    const x = byHash.get(btn.dataset.hash);
    if (!x) return;
    const a = analyze(x);
    anaCur = x.hash;
    // готовый вывод для AI: модели ошибаются, сравнивая числа сами (проверено на GLM и Groq)
    const posTxt = (self, med) => {
      if (!self || !med) return null;
      const p = Math.round((self - med) / med * 100);
      return p > 3 ? `объект на ${p}% дороже медианы` : p < -3 ? `объект на ${-p}% дешевле медианы`
        : "объект на уровне рынка";
    };
    anaStats = {                                     // рыночная сводка — уйдёт в AI-вердикт
      "аналогов": a.same.length,
      "позиция_к_медиане": posTxt(a.ppmSelf, a.medCity),
      "медиана_город_за_м2_usd": a.medCity && Math.round(a.medCity),
      "вилка_25_75_за_м2_usd": a.p25 != null ? [Math.round(a.p25), Math.round(a.p75)] : null,
      "объект_за_м2_usd": a.ppmSelf && Math.round(a.ppmSelf),
      "cap_rate_проц": a.capRate && +a.capRate.toFixed(1),
      "cap_rate_оценка": a.capRate == null ? null
        : a.capRate >= 10 ? "выше нормы Минска 8–10%" : a.capRate >= 8 ? "в норме Минска 8–10%"
        : "ниже нормы Минска 8–10%",
      "окупаемость_лет": a.payback && +a.payback.toFixed(1),
      "ожид_ставка_аренды_м2_мес_usd": a.rate && Math.round(a.rate),
    };
    $("#anaTitle").textContent =
      `Анализ: ${x.type || "объект"}${x.area ? ", " + nf.format(x.area) + " м²" : ""}`;
    $("#anaBody").innerHTML = analysisHtml(a);
    $("#anaModal").hidden = false;
    loadGeo(x);
  }

  // подсказки по локации поверх базового списка арендаторов (простые правила на OSM-цифрах)
  function tenantTips(x, g) {
    const tips = [];
    if (x.type === "Торговое") {
      if (!g.pharmacies) tips.push("аптек в 300 м нет — сильная точка под аптеку");
      if (g.food <= 1 && g.poi >= 12) tips.push("окружение живое, а общепита мало — ниша для кафе/пекарни");
      if (g.shops >= 15) tips.push("плотная розница рядом — трафик есть, конкуренция высокая");
      if (g.schools) tips.push("рядом школа/сад — детские товары, канцелярия, кружки");
    }
    if (x.type === "Офис" && !g.food) tips.push("общепита рядом нет — минус для сотрудников, плюс для столовой/кофейни на 1-м этаже");
    if (g.transit_m != null && g.transit_m <= 250) tips.push(`остановка в ${g.transit_m} м — удобно без машины`);
    if (g.transit_m == null) tips.push("транспорта в 800 м нет — рассчитывать только на автомобилистов");
    if (g.activity === "очень низкая" && x.type !== "Склад" && x.type !== "Производство")
      tips.push("вокруг пусто — скорее склад, мастерская или шоурум «по записи»");
    return tips;
  }

  function loadGeo(x) {
    if (!$("#geoBox")) return;
    fetch(`/api/geo?hash=${encodeURIComponent(x.hash)}`).then((r) => r.json()).then((g) => {
      if (anaCur !== x.hash) return;                 // модалку уже переоткрыли на другом объекте
      const el = $("#geoBox");
      if (!el) return;
      if (!g.ok) {
        el.querySelector(".ana-note").textContent = `локация: ${g.error || "нет данных"}`;
        return;
      }
      const row = (l, v) => `<div class="ana-row"><span>${l}</span><b>${v}</b></div>`;
      el.innerHTML = `<div class="ana-box__t">Локация (OSM, радиус 300 м)</div>` +
        row("Активность вокруг", `${esc(g.activity)} · ${g.poi} точек`) +
        row("Магазины / общепит / аптеки", `${g.shops} / ${g.food} / ${g.pharmacies}`) +
        row("До транспорта", g.transit_m != null ? `${g.transit_m} м` : "нет в 800 м") +
        (g.geocoded ? `<div class="ana-note">координаты найдены по адресу (менее точно)</div>` : "");
      const tips = tenantTips(x, g);
      const th = $("#tenantsHint");
      if (th && tips.length) th.innerHTML =
        `<div class="ana-note">по локации: ${esc(tips.join("; "))}</div>`;
    }).catch(() => {});
  }

  function aiVerdict(btn) {
    const h = anaCur;
    if (!h) return;
    btn.disabled = true;
    btn.textContent = "GLM думает…";
    postJSON("/api/verdict", { hash: h, stats: anaStats }).then((v) => {
      if (anaCur !== h) return;
      const box = $("#aiBox");
      if (!box) return;
      box.innerHTML = v.ok
        ? `<div class="ana-box__t">AI-вердикт (${esc(v.model || "AI")}, бесплатно)</div><div class="ana-verdict">${esc(v.text)}</div>`
        : `<div class="ana-note">AI-вердикт: ${esc(v.error || "не получился")}</div>`;
    }).catch(() => {
      btn.disabled = false;
      btn.textContent = "AI-вердикт";
    });
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
    const geoBox = `<div class="ana-box" id="geoBox">
      <div class="ana-box__t">Локация (OSM, радиус 300 м)</div>
      <div class="ana-note">оцениваю окружение…</div></div>`;
    const aiBox = `<div class="ana-box" id="aiBox">
      <button type="button" class="btn btn--ghost btn--mini" id="aiBtn">${ICON.chart}<span>AI-вердикт</span></button>
      <div class="ana-note">короткая сводка от бесплатной нейросети (Groq, ~5 с)</div></div>`;
    if (!x.area || !a.same.length) {
      return head + `<p class="ana-empty">Недостаточно похожих объектов для анализа${x.area ? "" : " (у объекта нет площади)"}.
        Сравнение работает там, где есть несколько объектов того же типа в том же городе.</p>` + geoBox + aiBox;
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
    ];
    if (a.near.length) rows.push(
      `<div class="ana-row"><span>Ближайшие (≤3 км) · ${a.near.length}</span>
        <b>${money(a.medNear)}${unit} ${pos(a.ppmSelf, a.medNear)}</b></div>`);
    rows.push(
      `<div class="ana-row"><span>По всему городу (${esc(x.city)}) · ${a.same.length} похож.${a.tol > 0.25 ? " (площадь ±50%)" : ""}</span>
        <b>${money(a.medCity)}${unit} ${pos(a.ppmSelf, a.medCity)}</b></div>`);
    if (a.p25 != null && a.p75 != null && a.same.length >= 4) rows.push(
      `<div class="ana-row"><span>Рыночная вилка (25–75% аналогов)</span>
        <b>${money(a.p25)}–${money(a.p75)}${unit}</b></div>`);
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
            <div class="ana-row"><span>Доходность (cap rate)</span><b class="ana-big">${a.capRate.toFixed(1)}%
              ${a.capRate >= 10 ? '<span class="ana-pos ana-pos--good">выше нормы 8–10%</span>'
                : a.capRate >= 8 ? '<span class="ana-pos ana-pos--mid">в норме 8–10%</span>'
                : '<span class="ana-pos ana-pos--bad">ниже нормы 8–10%</span>'}</b></div>
            <div class="ana-row"><span>Окупаемость</span><b class="ana-big">${a.payback.toFixed(1)} лет</b></div>
            <div class="ana-note">NOI — оценка: −вакансия 11%, −расходы 30% (нормы Минска); по ${a.rentN} аренд. аналогам.</div>
          </div>`
        : `<div class="ana-box"><div class="ana-note">Доходность: мало похожих арендных объектов для оценки ставки.</div></div>`;
    }
    const tenants = `<div class="ana-box">
      <div class="ana-box__t">Вероятные арендаторы</div>
      <div class="ana-tenants">${esc(tenantHint(x.type))}</div>
      <div id="tenantsHint"><div class="ana-note">базовая подсказка по типу; уточнения по локации появятся ниже</div></div></div>`;

    // список аналогов: СНАЧАЛА ближайшие (≤2 км, по расстоянию), потом остальные по городу
    const distTo = (o) => (x.coords && o.coords) ? kmDist(x.coords, o.coords) : null;
    const nearSet = new Set(a.near.map((o) => o.hash));
    const top = a.same.slice().sort((p, q) => {
      const pn = nearSet.has(p.hash), qn = nearSet.has(q.hash);
      if (pn !== qn) return pn ? -1 : 1;                                    // ближайшие — вперёд
      if (pn && qn) { const d = (distTo(p) ?? 9) - (distTo(q) ?? 9); if (d) return d; }  // среди них — по расстоянию
      return Math.abs(p.area - x.area) - Math.abs(q.area - x.area);         // прочие — по близости площади
    }).slice(0, 8);
    const list = top.map((o) => {
      const u = safeUrl(o.url);
      const name = `${esc(o.type || "")}, ${nf.format(o.area)} м²`;
      const nameHtml = u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${name}</a>` : name;
      const d = nearSet.has(o.hash) ? distTo(o) : null;
      const distStr = d != null ? `<span class="ana-near">${d < 1 ? Math.round(d * 1000) + " м" : d.toFixed(1) + " км"}</span>` : "";
      const addr = esc(o.addr || o.city || "");
      const meta = [distStr, addr].filter(Boolean).join(" · ");
      return `<li><span class="ana-an">${nameHtml}${meta ? `<span class="ana-addr">${meta}</span>` : ""}</span>
        <b>${money(ppmOf(o))}${unit}</b></li>`;
    }).join("");

    const fewNote = a.same.length < 4
      ? `<div class="ana-note">⚠ аналогов всего ${a.same.length} — оценка приблизительная</div>` : "";
    return head + `<div class="ana-rows">${rows.join("")}</div>${fewNote}${invest}${geoBox}${tenants}${aiBox}
      <div class="ana-box"><div class="ana-box__t">Ближайшие аналоги</div>
      <ul class="ana-list">${list}</ul></div>`;
  }

  window.__imgFail = (img) => {
    const m = img.closest(".lead__media");
    if (m) m.innerHTML = m.querySelector(".badge").outerHTML +
      `<div class="lead__ph">${ICON.building}<span>фото недоступно</span></div>`;
  };

  // фото карточек теперь идут через /img?hash (см. photoTag) — отдельный ленивый
  // догрузчик realt-превью больше не нужен. byHash — для блока «Анализ».
  const byHash = new Map(DATA.map((x) => [x.hash, x]));

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

  // кнопка AI-вердикта живёт в модалке анализа — grid-обработчик её не видит
  $("#anaBody").addEventListener("click", (e) => {
    const ai = e.target.closest("#aiBtn");
    if (ai) aiVerdict(ai);
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
    makeMulti("cityMsel", "city", facet("city"), "Все города");
    makeMulti("typeMsel", "type", facet("type"), "Все типы");
    makeMulti("sourceMsel", "source", facet("source"), "Все источники");

    // events
    $("#q").addEventListener("input", debounce((e) => { state.q = e.target.value; apply(); }, 130));
    $("#sort").addEventListener("change", (e) => { state.sort = e.target.value; apply(); });
    ["areaMin", "areaMax"].forEach((id) =>
      $("#" + id).addEventListener("input", debounce((e) => {
        const v = parseFloat(e.target.value); state[id] = isFinite(v) ? v : null; apply();
      }, 200)));
    $("#auctionPast").addEventListener("change", (e) => { state.auctionPast = e.target.checked; apply(); });
    $("#ownersOnly").addEventListener("change", (e) => { state.ownersOnly = e.target.checked; apply(); });

    document.querySelectorAll(".dealChk").forEach((cb) => {
      cb.checked = false;  // старт: ничего не выбрано = показаны все сделки (WebKit иначе восстанавливает)
      cb.addEventListener("change", () => {
        if (cb.checked) state.deals.add(cb.value); else state.deals.delete(cb.value);
        $("#pastWrap").hidden = !state.deals.has("auction") && !state.deals.has("onebv");  // «прошедшие» — только когда выбраны аукционы/1 БВ
        apply();
      });
    });

    function reset() {
      Object.assign(state, { q: "", sort: "date", auctionPast: false,
                             areaMin: null, areaMax: null, ownersOnly: false });
      state.deals.clear();
      MSELS.forEach((m) => m.clear());
      $("#q").value = ""; $("#sort").value = "date";
      $("#areaMin").value = ""; $("#areaMax").value = "";
      $("#auctionPast").checked = false; $("#pastWrap").hidden = true;
      $("#ownersOnly").checked = false;
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

  // ---------- обновление базы / аукционов ----------
  function wireUpdate() {
    const modal = $("#updModal"), log = $("#updLog"), spin = $("#updSpin");
    const stop = $("#updStop"), close = $("#updClose");
    const btnBase = $("#btnUpdate");
    const btnAuc = $("#btnUpdateAuctions"), btnBanks = $("#btnUpdateBanks");
    const title = $("#updTitle"), hint = modal.querySelector(".modal__hint");
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
      btnBase.disabled = btnAuc.disabled = btnBanks.disabled = s.running;
      if (!s.running && poll) {
        clearInterval(poll); poll = null;
        if (doneReload) {
          doneReload = false;
          toast("Готово — перезагружаю данные…");
          setTimeout(() => location.reload(), 1200);
        }
      }
    }

    async function start(target, titleText, hintText) {
      if (!hasBackend) return toast("Запустите дашборд через Дашборд.command (нужен сервер)");
      title.textContent = titleText;
      hint.textContent = hintText;
      open();
      const res = await postJSON("/api/update", { target });
      if (res.error) { toast(res.error); }
      doneReload = true;
      if (!poll) poll = setInterval(tick, 1500);
      tick();
    }

    btnBase.addEventListener("click", () => start("all", "Обновление базы",
      "Собирает всё разом: объявления (realt/megapolis/kufar/gohome/byrealty) + телефоны kufar + "
      + "гео-источники (domovita, edc) + аукционы + банки → обновление дашборда. "
      + "Гео-источники и телефоны kufar соберутся, только если VPN выключен (белорусский IP); "
      + "иначе шаг сам пропустится. Может занять много минут; окно можно закрыть, процесс идёт в фоне."));

    btnAuc.addEventListener("click", () => start("auctions", "Обновление аукционов",
      "Только аукционы: 14 площадок (mgcn, ipmtorgi, torgi.gov, «За 1 БВ» и др.) → свод → "
      + "обновление дашборда. Обычно 10–20 минут; окно можно закрыть, процесс идёт в фоне."));

    btnBanks.addEventListener("click", () => start("banks", "Обновление банков",
      "Только недвижимость банков (Белинвест, Белагропром, ТК, Цептер и др.) + телефоны belretail "
      + "(нужен бел. IP — иначе шаг пропустится) → обновление дашборда. Обычно несколько минут."));

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
