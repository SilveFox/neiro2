(() => {
  const $ = (id) => document.getElementById(id);

  const reportDate = $("reportDate");
  const extraPrompt = $("extraPrompt");
  const reportText = $("reportText");
  const jsonEditor = $("jsonEditor");
  const logOut = $("logOut");
  const status = $("status");
  const statusText = $("statusText");
  const btnParse = $("btnParse");
  const btnCalc = $("btnCalc");
  const btnSaveDb = $("btnSaveDb");
  const dbSaveStatus = $("dbSaveStatus");
  const btnExcel = $("btnExcel");
  const btnCancelPreview = $("btnCancelPreview");
  const btnSelectFile = $("btnSelectFile");
  const btnPaste = $("btnPaste");
  const fileInput = $("fileInput");
  const dropzone = $("dropzone");
  const previewBody = $("previewBody");
  const previewMeta = $("previewMeta");
  const previewTotal = $("previewTotal");
  const problemList = $("problemList");
  const sessionHistory = $("sessionHistory");
  const newMonth = $("newMonth");
  const newWorkbookTitle = $("newWorkbookTitle");
  const monthSelect = $("monthSelect");
  const monthSelectSettings = $("monthSelectSettings");
  const activeWorkbookLabel = $("activeWorkbookLabel");
  const reportWorkbookHint = $("reportWorkbookHint");
  const btnNewMonth = $("btnNewMonth");
  const btnActivateMonth = $("btnActivateMonth");
  const btnEditTable = $("btnEditTable");
  /** Cache of listed workbooks by select value (filename). */
  let workbookItemsByName = {};
  const priceBody = $("priceBody");
  const priceSearch = $("priceSearch");
  const priceStatus = $("priceStatus");
  const aliasBody = $("aliasBody");
  const aliasStatus = $("aliasStatus");
  const aliasSearch = $("aliasSearch");
  const employeesEditor = $("employeesEditor");
  const employeesStatus = $("employeesStatus");
  const modelInfo = $("modelInfo");
  const modelSelect = $("modelSelect");
  const modelCustom = $("modelCustom");
  const modelStatus = $("modelStatus");
  const btnModelSave = $("btnModelSave");
  const btnModelRefresh = $("btnModelRefresh");
  const excelLogBody = $("excelLogBody");

  let timerId = null;
  let startedAt = 0;
  let currentReport = null;
  let currentCalc = null;
  let priceItems = [];
  let priceDirty = false;
  let aliasesDoc = { aliases: [] };

  const today = new Date();
  reportDate.value = today.toISOString().slice(0, 10);
  newMonth.value = today.toISOString().slice(0, 7);

  function log(msg) {
    const ts = new Date().toLocaleTimeString("ru-RU", { hour12: false });
    logOut.hidden = false;
    logOut.textContent += `[${ts}] ${msg}\n`;
    const li = document.createElement("li");
    const dateLabel = today.toLocaleDateString("ru-RU");
    li.innerHTML = `<span>${dateLabel}</span><span>${escapeHtml(msg)}</span>`;
    if (sessionHistory.querySelector(".muted")) sessionHistory.innerHTML = "";
    sessionHistory.prepend(li);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatMoney(n) {
    const v = Number(n) || 0;
    return v.toLocaleString("ru-RU", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }

  function formatElapsed(ms) {
    const total = Math.floor(ms / 1000);
    const m = String(Math.floor(total / 60)).padStart(2, "0");
    const s = String(total % 60).padStart(2, "0");
    return `${m}:${s}`;
  }

  function startTimer() {
    startedAt = Date.now();
    status.hidden = false;
    statusText.textContent = "Обработка... 00:00";
    clearInterval(timerId);
    timerId = setInterval(() => {
      statusText.textContent = `Обработка... ${formatElapsed(Date.now() - startedAt)}`;
    }, 250);
  }

  function stopTimer() {
    clearInterval(timerId);
    timerId = null;
    const elapsed = formatElapsed(Date.now() - startedAt);
    status.hidden = true;
    return elapsed;
  }

  function setBusy(busy) {
    [btnParse, btnCalc, btnSaveDb, btnExcel, btnNewMonth, btnActivateMonth, btnEditTable, btnSelectFile, btnPaste, monthSelect, monthSelectSettings].forEach((b) => {
      if (b) b.disabled = busy;
    });
    if (!busy && currentCalc) btnExcel.disabled = false;
    if (!currentCalc) btnExcel.disabled = true;
  }

  function setStep(n) {
    document.querySelectorAll(".step").forEach((el) => {
      const s = Number(el.dataset.step);
      el.classList.toggle("active", s === n);
      el.classList.toggle("done", s < n);
    });
  }

  /* -------- navigation -------- */
  const navToggle = $("navToggle");
  const mainNav = $("mainNav");
  const workbookCreateStatus = $("workbookCreateStatus");
  const workbookEditStatus = $("workbookEditStatus");
  const btnRefreshWorkbooks = $("btnRefreshWorkbooks");
  let suppressMonthChange = false;

  function closeMobileNav() {
    if (mainNav) mainNav.classList.remove("open");
    if (navToggle) navToggle.setAttribute("aria-expanded", "false");
  }

  function showView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    document.querySelectorAll(".nav-link").forEach((a) => {
      a.classList.toggle("active", a.dataset.nav === name);
    });
    const view = document.getElementById(`view-${name}`);
    if (view) view.classList.add("active");
    if (name === "report") refreshWorkbooks();
    if (name === "price") loadPrice();
    if (name === "aliases") loadAliases();
    if (name === "settings") {
      refreshWorkbooks();
      loadEmployees();
      loadHealth();
      loadModelSettings();
    }
    if (name === "excel-log") loadExcelLog();
    location.hash = name;
    closeMobileNav();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  document.querySelectorAll("[data-nav]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      showView(el.dataset.nav);
    });
  });

  if (navToggle && mainNav) {
    navToggle.addEventListener("click", () => {
      const open = mainNav.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  document.querySelectorAll("[data-help-anchor]").forEach((el) => {
    el.addEventListener("click", () => {
      const target = document.getElementById(el.dataset.helpAnchor);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  document.querySelectorAll(".subtab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".subtab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".subpanel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      const panel = document.getElementById(`sub-${tab.dataset.subtab}`);
      if (panel) panel.classList.add("active");
    });
  });

  /* -------- preview from calculation JSON -------- */
  function showCalc(calculation) {
    currentCalc = calculation || null;
    previewBody.innerHTML = "";
    problemList.innerHTML = "";

    if (!calculation || !(calculation.workers || []).length) {
      previewBody.innerHTML = `<tr class="empty-row"><td colspan="5">Нет данных расчёта</td></tr>`;
      previewMeta.textContent = "Нет данных — загрузите отчёт";
      previewTotal.textContent = "";
      problemList.innerHTML = `<li class="muted">Пока нет проблемных работ</li>`;
      btnExcel.disabled = true;
      return;
    }

    const rows = [];
    const unmatched = [];

    for (const w of calculation.workers || []) {
      const fio = (w.members && w.members.length ? w.members.join(", ") : w.raw_worker_name) || "—";
      // jobs уже содержит и найденные, и проблемные; unmatched — дубликат для отчёта
      const jobs = w.jobs || [];
      if (!jobs.length) {
        rows.push({ fio, name: "—", qty: "—", tariff: "—", amount: "—", unmatched: false });
        continue;
      }
      for (const j of jobs) {
        const name = j.matched_name || j.job_description || j.raw_task_name || "—";
        const isUnmatched = j.matched === false || !j.matched_name;
        rows.push({
          fio,
          name,
          qty: j.volume ?? "—",
          tariff: isUnmatched ? "—" : formatMoney(j.unit_price),
          amount: isUnmatched ? "—" : formatMoney(j.amount),
          unmatched: isUnmatched,
          raw: j,
        });
        if (isUnmatched) {
          unmatched.push({
            name: j.raw_task_name || j.job_description || "Без названия",
            description: j.job_description || "",
            unit: j.unit || "шт.",
          });
        }
      }
    }

    for (const r of rows) {
      const tr = document.createElement("tr");
      if (r.unmatched) tr.classList.add("unmatched");
      tr.innerHTML = `
        <td>${escapeHtml(r.fio)}</td>
        <td>${escapeHtml(r.name)}</td>
        <td class="num">${escapeHtml(String(r.qty))}</td>
        <td class="num">${escapeHtml(String(r.tariff))}</td>
        <td class="num">${escapeHtml(String(r.amount))}</td>`;
      previewBody.appendChild(tr);
    }

    const date = calculation.report_date || reportDate.value || "—";
    previewMeta.textContent = `Дата ${date} · работ: ${rows.length} · не найдено: ${calculation.unmatched_count || unmatched.length}`;
    previewTotal.textContent = `Итого: ${formatMoney(calculation.grand_total)}`;
    btnExcel.disabled = false;
    setStep(3);

    if (!unmatched.length) {
      problemList.innerHTML = `<li class="muted">Все работы найдены в прайсе</li>`;
    } else {
      const seen = new Set();
      for (const u of unmatched) {
        const key = u.name.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        problemList.appendChild(buildUnmatchedPicker(u));
      }
    }
  }

  function pricePickScore(query, name) {
    const q = String(query || "").toLowerCase();
    const n = String(name || "").toLowerCase();
    if (!q || !n) return 0;
    if (n === q) return 100;
    if (n.includes(q) || q.includes(n)) return 80;
    const qt = q.split(/[^a-zа-яё0-9]+/i).filter((t) => t.length > 2);
    const nt = new Set(n.split(/[^a-zа-яё0-9]+/i).filter((t) => t.length > 2));
    if (!qt.length) return 0;
    const hit = qt.filter((t) => nt.has(t)).length;
    return (hit / qt.length) * 60;
  }

  function rankedPriceNames(query) {
    const items = (priceItems || []).filter((p) => (p.name || "").trim());
    const scored = items.map((p) => ({
      name: p.name,
      score: pricePickScore(query, p.name),
    }));
    scored.sort((a, b) => b.score - a.score || a.name.localeCompare(b.name, "ru"));
    return scored.map((x) => x.name);
  }

  function fillPricePickSelect(select, query, keepValue) {
    const names = rankedPriceNames(query);
    const q = (query || "").trim().toLowerCase();
    const filtered = q
      ? names.filter((n) => n.toLowerCase().includes(q) || pricePickScore(query, n) >= 20)
      : names;
    const current = keepValue || select.value;
    select.innerHTML = `<option value="">Выберите из прайс-листа…</option>`;
    for (const name of filtered) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    }
    if (current && [...select.options].some((o) => o.value === current)) {
      select.value = current;
    } else if (!current && filtered.length && q && pricePickScore(query, filtered[0]) >= 20) {
      select.value = filtered[0];
    }
  }

  function buildUnmatchedPicker(item) {
    const li = document.createElement("li");
    li.className = "problem-item";
    li.innerHTML = `
      <div class="problem-item-head">
        <span class="warn">!</span>
        <span>Не найдено в прайсе: <strong>${escapeHtml(item.name)}</strong></span>
      </div>
      <div class="price-pick">
        <input type="search" class="price-pick-search" placeholder="Поиск в прайсе…" autocomplete="off" />
        <select class="price-pick-select" aria-label="Позиция прайс-листа">
          <option value="">Выберите из прайс-листа…</option>
        </select>
        <button type="button" class="btn primary btn-pick-price">Выбрать</button>
      </div>
      <p class="price-pick-hint muted">Выбор запишет это название в алиасы выбранной позиции.</p>`;
    const search = li.querySelector(".price-pick-search");
    const select = li.querySelector(".price-pick-select");
    const btn = li.querySelector(".btn-pick-price");
    const hint = li.querySelector(".price-pick-hint");

    const refreshOptions = () => fillPricePickSelect(select, search.value || item.name, select.value);
    search.addEventListener("input", refreshOptions);
    btn.addEventListener("click", () => linkUnmatchedToPrice(item, select.value, btn, hint));
    const ready = priceItems.length ? Promise.resolve() : loadPrice(true);
    ready.then(refreshOptions);
    return li;
  }

  async function linkUnmatchedToPrice(item, official, btn, hint) {
    const chosen = (official || "").trim();
    if (!chosen) {
      if (hint) hint.textContent = "Сначала выберите позицию из прайс-листа.";
      return;
    }
    if (btn) btn.disabled = true;
    try {
      const res = await fetch("/api/aliases/link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ synonym: item.name, official: chosen }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || res.statusText);
      }
      aliasesDoc = data;
      log(`Алиас: «${item.name}» → «${chosen}»`);
      if (hint) hint.textContent = `Сохранено в алиасы: «${chosen}». Пересчёт…`;
      await recalculate();
    } catch (e) {
      log(`Не удалось привязать к прайсу: ${e.message}`);
      if (hint) hint.textContent = e.message;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function readEditedReport() {
    try {
      return JSON.parse(jsonEditor.value);
    } catch (e) {
      throw new Error("JSON в редакторе некорректен: " + e.message);
    }
  }

  function reportWithSelectedDate() {
    const report = readEditedReport();
    const selected = (reportDate.value || "").trim();
    if (!selected) throw new Error("Укажите дату отчёта");
    report.report_date = selected;
    try {
      const edited = JSON.parse(jsonEditor.value);
      if (edited.report_date !== selected) {
        edited.report_date = selected;
        jsonEditor.value = JSON.stringify(edited, null, 2);
      }
    } catch (_) { /* ignore */ }
    currentReport = report;
    return report;
  }

  function syncDateIntoEditor() {
    if (!jsonEditor.value.trim()) return;
    try {
      const report = JSON.parse(jsonEditor.value);
      const selected = (reportDate.value || "").trim();
      if (!selected || report.report_date === selected) return;
      report.report_date = selected;
      jsonEditor.value = JSON.stringify(report, null, 2);
      currentReport = report;
    } catch (_) { /* ignore */ }
  }

  function applyParseResult(data, elapsed) {
    currentReport = data.report;
    jsonEditor.value = JSON.stringify(data.report, null, 2);
    if (data.extracted_text) reportText.value = data.extracted_text;
    showCalc(data.calculation);
    setStep(3);
    const workers = (data.report.workers || []).length;
    log(`Разбор успешен за ${elapsed}. Сотрудников: ${workers}.`);
    if (data.calculation?.unmatched_count) {
      log(`Не сопоставлено с прайсом: ${data.calculation.unmatched_count}`);
    }
  }

  /* -------- parse / calc / excel -------- */
  async function parseReport() {
    const text = reportText.value.trim();
    if (!text) {
      log("Ошибка: пустой текст отчёта");
      return;
    }
    setBusy(true);
    startTimer();
    setStep(2);
    log("Отправка отчёта в модель...");
    try {
      const res = await fetch("/api/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report_text: text,
          extra_prompt: extraPrompt.value.trim(),
          report_date: reportDate.value || null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      const elapsed = stopTimer();
      if (!res.ok) {
        log(`Ошибка (${elapsed}): ${data.detail || res.statusText}`);
        setStep(1);
        return;
      }
      applyParseResult(data, elapsed);
    } catch (e) {
      stopTimer();
      setStep(1);
      log("Сбой сети/сервера: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function parseFile(file) {
    if (!file) return;
    setBusy(true);
    startTimer();
    setStep(2);
    log(`Загрузка файла «${file.name}»...`);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (reportDate.value) fd.append("report_date", reportDate.value);
      if (extraPrompt.value.trim()) fd.append("extra_prompt", extraPrompt.value.trim());
      const res = await fetch("/api/parse-file", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      const elapsed = stopTimer();
      if (!res.ok) {
        log(`Ошибка файла (${elapsed}): ${data.detail || res.statusText}`);
        setStep(1);
        return;
      }
      applyParseResult(data, elapsed);
    } catch (e) {
      stopTimer();
      setStep(1);
      log(e.message);
    } finally {
      setBusy(false);
      fileInput.value = "";
    }
  }

  async function recalculate() {
    setBusy(true);
    try {
      const report = reportWithSelectedDate();
      const res = await fetch("/api/calculate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report, report_date: report.report_date }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        log(`Ошибка расчёта: ${data.detail || res.statusText}`);
        return;
      }
      currentReport = report;
      showCalc(data.calculation);
      log(`Пересчёт готов. Итого: ${data.calculation.grand_total}`);
    } catch (e) {
      log(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveToDb() {
    if (dbSaveStatus) dbSaveStatus.textContent = "";
    if (!jsonEditor.value.trim()) {
      log("Нет JSON отчёта для сохранения в БД");
      if (dbSaveStatus) dbSaveStatus.textContent = "Сначала разберите отчёт";
      return;
    }
    setBusy(true);
    if (dbSaveStatus) dbSaveStatus.textContent = "Сохранение…";
    try {
      const report = reportWithSelectedDate();
      let calculation = currentCalc;
      if (!calculation) {
        const resCalc = await fetch("/api/calculate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ report, report_date: report.report_date }),
        });
        const dataCalc = await resCalc.json().catch(() => ({}));
        if (!resCalc.ok) {
          throw new Error(dataCalc.detail || "Не удалось пересчитать перед сохранением");
        }
        calculation = dataCalc.calculation;
        showCalc(calculation);
      }
      const res = await fetch("/api/reports/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report,
          calculation,
          source_text: reportText.value.trim() || null,
          report_date: report.report_date,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || res.statusText);
      }
      currentReport = report;
      const msg = data.message || `Сохранено в БД id=${data.id}`;
      log(`${msg}. Итого: ${data.grand_total ?? "—"}`);
      if (dbSaveStatus) {
        dbSaveStatus.textContent = `Сохранено · id ${data.id} · ${data.workers_names || data.report_date || ""} · работ ${data.jobs_count ?? "—"} · ${data.grand_total ?? 0} ₽`;
      }
    } catch (e) {
      log(`Ошибка БД: ${e.message}`);
      if (dbSaveStatus) dbSaveStatus.textContent = e.message;
    } finally {
      setBusy(false);
    }
  }

  async function writeExcel() {
    setBusy(true);
    startTimer();
    setStep(4);
    try {
      const report = reportWithSelectedDate();
      log(`Запись в Excel на дату ${report.report_date}...`);
      const res = await fetch("/api/excel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report,
          report_date: report.report_date,
          skip_duplicates: true,
        }),
      });
      const data = await res.json().catch(() => ({}));
      const elapsed = stopTimer();
      if (!res.ok) {
        log(`Ошибка Excel (${elapsed}): ${data.detail || res.statusText}`);
        setStep(3);
        return;
      }
      if (data.calculation) showCalc(data.calculation);
      if (data.duplicate) {
        log(`Пропуск дубликата (${elapsed}): ${data.message}`);
      } else {
        log(
          `Excel обновлён за ${elapsed}. Книга ${data.year_month || ""}${data.workbook_created ? " (создана)" : ""} лист ${data.day_sheet}, сумма ${data.grand_total}`
        );
        if (data.workbook_created) {
          log(`Создан и активирован месяц ${data.year_month}`);
        }
        await refreshWorkbooks();
        const li = document.createElement("li");
        li.innerHTML = `<span>${escapeHtml(report.report_date)}</span><span>Запись на лист ${escapeHtml(String(data.day_sheet))}</span><span class="tag">готово</span>`;
        if (sessionHistory.querySelector(".muted")) sessionHistory.innerHTML = "";
        sessionHistory.prepend(li);
      }
      currentReport = report;
    } catch (e) {
      stopTimer();
      setStep(3);
      log(e.message);
    } finally {
      setBusy(false);
    }
  }

  function cancelPreview() {
    currentCalc = null;
    currentReport = null;
    jsonEditor.value = "";
    showCalc(null);
    setStep(1);
    log("Предпросмотр очищен");
  }

  /* -------- file / clipboard -------- */
  btnSelectFile.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files?.[0]) parseFile(fileInput.files[0]);
  });

  ["dragenter", "dragover"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });
  dropzone.addEventListener("drop", (e) => {
    const f = e.dataTransfer?.files?.[0];
    if (f) parseFile(f);
  });

  btnPaste.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text.trim()) {
        log("Буфер обмена пуст");
        return;
      }
      reportText.value = text;
      log("Текст вставлен из буфера");
    } catch (e) {
      log("Не удалось прочитать буфер: " + e.message);
    }
  });

  /* -------- workbooks / settings -------- */
  function workbookDisplayName(item) {
    if (!item) return "—";
    if (item.label) return String(item.label);
    const ym = String(item.year_month || "").trim();
    const title = String(item.title || "").trim();
    if (/^\d{4}-\d{2}$/.test(ym)) return title ? `${ym} — ${title}` : ym;
    const fromName = String(item.name || item.path || "").match(/(\d{4}-\d{2})(?:\.xlsx)?$/i);
    if (fromName) return title ? `${fromName[1]} — ${title}` : fromName[1];
    return item.name || "—";
  }

  function workbookSelectValue(item) {
    return String(item.name || item.year_month || "").trim();
  }

  function updateReportWorkbookHint(active) {
    if (!reportWorkbookHint) return;
    if (active) {
      const label = workbookDisplayName(active);
      const dateYm = (reportDate.value || "").slice(0, 7);
      const target = /^\d{4}-\d{2}$/.test(dateYm) ? dateYm : label;
      reportWorkbookHint.textContent =
        `Таблица: ${label}. Отчёт попадёт в ${target} (дневной лист по дате ниже).`;
    } else {
      reportWorkbookHint.textContent =
        "Выберите таблицу (формат ГГГГ-ММ). Создание новых — в «Настройках».";
    }
  }

  function fillMonthSelect(select, items, preferred, selectedActive) {
    if (!select) return;
    const prev = preferred || select.value;
    select.innerHTML = "";
    if (!items.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Нет созданных месяцев";
      select.appendChild(opt);
      return;
    }
    for (const item of items) {
      const opt = document.createElement("option");
      const label = workbookDisplayName(item);
      opt.value = workbookSelectValue(item);
      opt.textContent = item.active ? `${label} — активный` : label;
      select.appendChild(opt);
    }
    if (prev && [...select.options].some((o) => o.value === prev)) {
      select.value = prev;
    } else if (selectedActive) {
      select.value = selectedActive;
    }
  }

  function renderWorkbookList(data) {
    const active = data.active;
    if (activeWorkbookLabel) {
      activeWorkbookLabel.textContent = active
        ? `Активная таблица: ${workbookDisplayName(active)}`
        : "Активная таблица: —";
    }
    updateReportWorkbookHint(active);

    const items = data.items || [];
    workbookItemsByName = {};
    for (const item of items) {
      const key = workbookSelectValue(item);
      if (key) workbookItemsByName[key] = item;
    }
    let selectedActive = "";
    for (const item of items) {
      if (item.active) selectedActive = workbookSelectValue(item);
    }
    const preferred = monthSelect?.value || monthSelectSettings?.value || selectedActive;
    suppressMonthChange = true;
    fillMonthSelect(monthSelect, items, preferred, selectedActive);
    fillMonthSelect(monthSelectSettings, items, preferred, selectedActive);
    suppressMonthChange = false;
  }

  function selectedWorkbookKey() {
    return (monthSelect?.value || monthSelectSettings?.value || "").trim();
  }

  function selectedYearMonth() {
    const key = selectedWorkbookKey();
    const item = workbookItemsByName[key];
    if (item?.year_month) return String(item.year_month);
    if (/^\d{4}-\d{2}$/.test(key)) return key;
    const m = key.match(/(\d{4}-\d{2})(?:\.xlsx)?$/i);
    return m ? m[1] : key;
  }

  function setBothMonthSelects(key) {
    suppressMonthChange = true;
    if (monthSelect && [...(monthSelect.options || [])].some((o) => o.value === key)) {
      monthSelect.value = key;
    }
    if (monthSelectSettings && [...(monthSelectSettings.options || [])].some((o) => o.value === key)) {
      monthSelectSettings.value = key;
    }
    suppressMonthChange = false;
  }

  async function refreshWorkbooks() {
    try {
      const res = await fetch("/api/workbook/list");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        log("Не удалось загрузить список книг: " + (data.detail || res.statusText));
        return;
      }
      renderWorkbookList(data);
    } catch (e) {
      log("Сбой списка книг: " + e.message);
    }
  }

  function syncReportDateToMonth(ym) {
    if (!reportDate || !/^\d{4}-\d{2}$/.test(ym || "")) return;
    const current = (reportDate.value || "").trim();
    let day = "01";
    if (/^\d{4}-\d{2}-\d{2}$/.test(current)) {
      day = current.slice(8, 10);
      const maxDay = new Date(Number(ym.slice(0, 4)), Number(ym.slice(5, 7)), 0).getDate();
      day = String(Math.min(Number(day) || 1, maxDay)).padStart(2, "0");
    }
    const next = `${ym}-${day}`;
    if (reportDate.value !== next) {
      reportDate.value = next;
      syncDateIntoEditor();
    }
  }

  function findWorkbookKeyForMonth(ym) {
    if (!/^\d{4}-\d{2}$/.test(ym || "")) return "";
    // Prefer default unnamed book, then any titled for that month
    let titled = "";
    for (const [key, item] of Object.entries(workbookItemsByName)) {
      if (item.year_month !== ym) continue;
      if (!item.title) return key;
      if (!titled) titled = key;
    }
    return titled;
  }

  function syncMonthSelectToReportDate() {
    if (!reportDate) return;
    const d = (reportDate.value || "").trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return;
    const ym = d.slice(0, 7);
    const key = findWorkbookKeyForMonth(ym);
    if (!key) return;
    if (selectedWorkbookKey() === key) return;
    setBothMonthSelects(key);
    activateMonth({ quiet: true, yearMonth: key });
  }

  async function createMonth() {
    const value = newMonth.value;
    if (!value) {
      log("Выберите месяц для создания");
      if (workbookCreateStatus) workbookCreateStatus.textContent = "Укажите месяц новой таблицы";
      return;
    }
    const [y, m] = value.split("-").map(Number);
    const title = (newWorkbookTitle?.value || "").trim();
    setBusy(true);
    const labelHint = title ? `${value} — ${title}` : value;
    if (workbookCreateStatus) workbookCreateStatus.textContent = `Создание таблицы ${labelHint}…`;
    log(`Создание новой таблицы (${labelHint})...`);
    try {
      const payload = { year: y, month: m, activate: true };
      if (title) payload.title = title;
      const res = await fetch("/api/workbook/new", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const err = data.detail || res.statusText;
        log(`Ошибка: ${err}`);
        if (workbookCreateStatus) workbookCreateStatus.textContent = err;
        return;
      }
      const msg = data.message || `Таблица ${labelHint} создана и активна`;
      log(msg);
      if (workbookCreateStatus) workbookCreateStatus.textContent = msg;
      if (newWorkbookTitle) newWorkbookTitle.value = "";
      await refreshWorkbooks();
    } catch (e) {
      log(e.message);
      if (workbookCreateStatus) workbookCreateStatus.textContent = e.message;
    } finally {
      setBusy(false);
    }
  }

  async function activateMonth({ syncDate = false, quiet = false, yearMonth = null } = {}) {
    const key = (yearMonth || selectedWorkbookKey()).trim();
    if (!key) {
      if (!quiet) log("Нет месяца для активации");
      if (workbookEditStatus) workbookEditStatus.textContent = "Выберите таблицу в списке";
      return false;
    }
    const item = workbookItemsByName[key];
    const ym =
      (item && item.year_month) ||
      (/^\d{4}-\d{2}$/.test(key) ? key : (key.match(/(\d{4}-\d{2})(?:\.xlsx)?$/i) || [])[1] || "");
    setBothMonthSelects(key);
    setBusy(true);
    const showLabel = item ? workbookDisplayName(item) : key;
    if (workbookEditStatus) workbookEditStatus.textContent = `Активация ${showLabel}…`;
    try {
      const body =
        item && item.name
          ? { name: item.name }
          : key.toLowerCase().endsWith(".xlsx")
            ? { name: key }
            : { year_month: ym || key };
      const res = await fetch("/api/workbook/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const err = data.detail || res.statusText;
        if (!quiet) log(`Ошибка активации: ${err}`);
        if (workbookEditStatus) workbookEditStatus.textContent = err;
        if (reportWorkbookHint) reportWorkbookHint.textContent = err;
        return false;
      }
      const msg = `Активна таблица: ${workbookDisplayName(data.active) || showLabel}`;
      if (!quiet) log(msg);
      if (workbookEditStatus) workbookEditStatus.textContent = msg;
      if (syncDate && ym) syncReportDateToMonth(ym);
      await refreshWorkbooks();
      return true;
    } catch (e) {
      if (!quiet) log(e.message);
      if (workbookEditStatus) workbookEditStatus.textContent = e.message;
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function editExistingTable() {
    const key = selectedWorkbookKey();
    if (!key) {
      if (workbookEditStatus) workbookEditStatus.textContent = "Выберите таблицу в списке";
      return;
    }
    const label = workbookDisplayName(workbookItemsByName[key]) || key;
    const ok = await activateMonth({ syncDate: true, yearMonth: key });
    if (!ok) return;
    if (workbookEditStatus) {
      workbookEditStatus.textContent =
        `Таблица ${label} активна. Разберите данные и нажмите «Формировать отчёт» для дозаполнения.`;
    }
    showView("report");
  }

  async function loadHealth() {
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      if (res.ok) {
        modelInfo.textContent = `Текущая модель: ${data.model || "—"} · позиций прайса: ${data.price_items ?? "—"}`;
      }
    } catch (_) { /* ignore */ }
  }

  function fillModelSelect(options, active) {
    if (!modelSelect) return;
    modelSelect.innerHTML = "";
    (options || []).forEach((opt) => {
      const o = document.createElement("option");
      o.value = opt.name;
      const mark = opt.installed ? "" : " (не скачана)";
      o.textContent = `${opt.label || opt.name}${mark}`;
      if (opt.name === active) o.selected = true;
      modelSelect.appendChild(o);
    });
  }

  async function loadModelSettings() {
    if (!modelSelect) return;
    try {
      const res = await fetch("/api/model");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (modelStatus) modelStatus.textContent = data.detail || "Не удалось загрузить список моделей";
        return;
      }
      fillModelSelect(data.options || [], data.model);
      if (modelCustom) modelCustom.value = "";
      const ollama = data.ollama_ok ? "Ollama доступна" : "Ollama недоступна или список пуст";
      modelInfo.textContent = `Текущая модель: ${data.model || "—"} · ${ollama}`;
      if (modelStatus) {
        modelStatus.textContent = data.ollama_ok
          ? "Выберите модель и нажмите «Применить»."
          : "Ollama не ответила — можно указать имя вручную и применить.";
      }
    } catch (e) {
      if (modelStatus) modelStatus.textContent = e.message;
    }
  }

  async function saveModel() {
    if (!modelStatus) return;
    const custom = (modelCustom?.value || "").trim();
    const selected = (modelSelect?.value || "").trim();
    const model = custom || selected;
    if (!model) {
      modelStatus.textContent = "Укажите модель";
      return;
    }
    modelStatus.textContent = "Сохранение…";
    try {
      const res = await fetch("/api/model", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        modelStatus.textContent = data.detail || "Ошибка сохранения модели";
        return;
      }
      fillModelSelect(data.options || [], data.model);
      if (modelCustom) modelCustom.value = "";
      modelInfo.textContent = `Текущая модель: ${data.model || "—"} · ${
        data.ollama_ok ? "Ollama доступна" : "Ollama недоступна или список пуст"
      }`;
      modelStatus.textContent = data.message || `Применено: ${data.model}`;
      loadHealth();
    } catch (e) {
      modelStatus.textContent = e.message;
    }
  }

  async function loadEmployees() {
    try {
      const res = await fetch("/api/employees");
      const data = await res.json();
      if (!res.ok) return;
      employeesEditor.value = (data.employees || []).join("\n");
    } catch (_) { /* ignore */ }
  }

  async function saveEmployees() {
    const employees = employeesEditor.value
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      const res = await fetch("/api/employees", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ employees }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        employeesStatus.textContent = data.detail || "Ошибка сохранения";
        return;
      }
      employeesStatus.textContent = `Сохранено: ${data.count} сотрудников`;
    } catch (e) {
      employeesStatus.textContent = e.message;
    }
  }

  /* -------- price editor -------- */
  async function loadPrice(silent) {
    try {
      const res = await fetch("/api/price");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (!silent) priceStatus.textContent = data.detail || "Не удалось загрузить прайс";
        return;
      }
      priceItems = (data.items || []).map((x) => ({ ...x }));
      priceDirty = false;
      renderPriceTable();
      if (!silent) priceStatus.textContent = `Загружено позиций: ${priceItems.length}`;
    } catch (e) {
      if (!silent) priceStatus.textContent = e.message;
    }
  }

  function collectPriceFromDom() {
    const rows = [...priceBody.querySelectorAll("tr")];
    return rows.map((tr, idx) => {
      const name = tr.querySelector('[data-f="name"]')?.value?.trim() || "";
      const price = parseFloat(String(tr.querySelector('[data-f="price"]')?.value || "0").replace(",", "."));
      const unit = tr.querySelector('[data-f="unit"]')?.value?.trim() || "";
      const service_type = tr.querySelector('[data-f="service_type"]')?.value?.trim() || "Общее";
      const rowAttr = tr.dataset.row;
      const row = rowAttr ? Number(rowAttr) : idx + 4;
      return { name, price: Number.isFinite(price) ? price : 0, unit, service_type, row };
    }).filter((x) => x.name);
  }

  function renderPriceTable() {
    const q = (priceSearch.value || "").trim().toLowerCase();
    priceBody.innerHTML = "";
    let n = 0;
    priceItems.forEach((item, idx) => {
      if (q && !(item.name || "").toLowerCase().includes(q)) return;
      n += 1;
      const tr = document.createElement("tr");
      tr.dataset.idx = String(idx);
      if (item.row != null) tr.dataset.row = String(item.row);
      tr.innerHTML = `
        <td class="num">${n}</td>
        <td><input data-f="name" type="text" value="${escapeHtml(item.name || "")}" /></td>
        <td><input data-f="price" type="number" step="0.01" value="${item.price ?? 0}" /></td>
        <td><input data-f="unit" type="text" value="${escapeHtml(item.unit || "")}" /></td>
        <td><input data-f="service_type" type="text" value="${escapeHtml(item.service_type || "Общее")}" /></td>
        <td><button type="button" class="btn danger" title="Удалить">✕</button></td>`;
      tr.querySelector(".btn.danger").addEventListener("click", () => {
        priceItems.splice(idx, 1);
        priceDirty = true;
        renderPriceTable();
      });
      tr.querySelectorAll("input").forEach((inp) => {
        inp.addEventListener("change", () => {
          const i = Number(tr.dataset.idx);
          if (!priceItems[i]) return;
          priceItems[i].name = tr.querySelector('[data-f="name"]').value;
          priceItems[i].price = parseFloat(tr.querySelector('[data-f="price"]').value) || 0;
          priceItems[i].unit = tr.querySelector('[data-f="unit"]').value;
          priceItems[i].service_type = tr.querySelector('[data-f="service_type"]').value || "Общее";
          priceDirty = true;
        });
      });
      priceBody.appendChild(tr);
    });
    if (!n) {
      priceBody.innerHTML = `<tr class="empty-row"><td colspan="6">Нет позиций</td></tr>`;
    }
  }

  async function savePrice() {
    // sync visible edits
    priceBody.querySelectorAll("tr[data-idx]").forEach((tr) => {
      const i = Number(tr.dataset.idx);
      if (!priceItems[i]) return;
      priceItems[i].name = tr.querySelector('[data-f="name"]').value;
      priceItems[i].price = parseFloat(tr.querySelector('[data-f="price"]').value) || 0;
      priceItems[i].unit = tr.querySelector('[data-f="unit"]').value;
      priceItems[i].service_type = tr.querySelector('[data-f="service_type"]').value || "Общее";
    });
    const items = priceItems.filter((x) => (x.name || "").trim());
    try {
      const res = await fetch("/api/price", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        priceStatus.textContent = data.detail || "Ошибка сохранения";
        return;
      }
      priceItems = data.items || items;
      priceDirty = false;
      renderPriceTable();
      priceStatus.textContent = `Сохранено: ${data.count} позиций`;
      log(`Прайс сохранён (${data.count})`);
    } catch (e) {
      priceStatus.textContent = e.message;
    }
  }

  $("btnPriceAdd").addEventListener("click", () => {
    priceItems.push({ name: "Новая позиция", price: 0, unit: "шт.", service_type: "Общее", row: null });
    priceDirty = true;
    priceSearch.value = "";
    renderPriceTable();
    const last = priceBody.querySelector("tr:last-child input[data-f='name']");
    if (last) {
      last.focus();
      last.select();
    }
  });
  $("btnPriceSave").addEventListener("click", savePrice);
  priceSearch.addEventListener("input", renderPriceTable);

  /* -------- aliases -------- */
  async function loadAliases() {
    try {
      const res = await fetch("/api/aliases");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        aliasStatus.textContent = data.detail || "Ошибка загрузки";
        return;
      }
      aliasesDoc = data;
      renderAliases();
    } catch (e) {
      aliasStatus.textContent = e.message;
    }
  }

  function parseSynonymsField(value) {
    return String(value || "")
      .split(";")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function syncVisibleAliases() {
    if (!aliasesDoc.aliases) aliasesDoc.aliases = [];
    aliasBody.querySelectorAll("tr[data-idx]").forEach((tr) => {
      const i = Number(tr.dataset.idx);
      if (!aliasesDoc.aliases[i]) return;
      aliasesDoc.aliases[i].official = tr.querySelector('[data-f="official"]').value;
      aliasesDoc.aliases[i].synonyms = parseSynonymsField(
        tr.querySelector('[data-f="synonyms"]').value
      );
    });
  }

  function aliasMatchesQuery(block, q) {
    if (!q) return true;
    const official = (block.official || "").toLowerCase();
    if (official.includes(q)) return true;
    return (block.synonyms || []).some((s) => String(s).toLowerCase().includes(q));
  }

  function updateAliasStatus(shown, total) {
    if (!total) {
      aliasStatus.textContent = "Записей: 0";
      return;
    }
    const q = (aliasSearch.value || "").trim();
    aliasStatus.textContent = q
      ? `Показано ${shown} из ${total}`
      : `Записей: ${total}`;
  }

  function renderAliases() {
    syncVisibleAliases();
    aliasBody.innerHTML = "";
    const list = aliasesDoc.aliases || [];
    const q = (aliasSearch.value || "").trim().toLowerCase();
    const visible = [];
    list.forEach((block, idx) => {
      if (aliasMatchesQuery(block, q)) visible.push(idx);
    });

    if (!list.length) {
      aliasBody.innerHTML = `<tr class="empty-row"><td colspan="3">Нет алиасов</td></tr>`;
      updateAliasStatus(0, 0);
      return;
    }
    if (!visible.length) {
      aliasBody.innerHTML = `<tr class="empty-row"><td colspan="3">Ничего не найдено. Измените запрос или очистите поиск.</td></tr>`;
      updateAliasStatus(0, list.length);
      return;
    }

    for (const idx of visible) {
      const block = list[idx];
      const tr = document.createElement("tr");
      tr.dataset.idx = String(idx);
      const syn = (block.synonyms || []).join("; ");
      tr.innerHTML = `
        <td><input data-f="official" type="text" value="${escapeHtml(block.official || "")}" /></td>
        <td><textarea data-f="synonyms" rows="2">${escapeHtml(syn)}</textarea></td>
        <td><button type="button" class="btn danger">✕</button></td>`;
      tr.querySelector(".btn.danger").addEventListener("click", () => {
        syncVisibleAliases();
        aliasesDoc.aliases.splice(idx, 1);
        renderAliases();
      });
      aliasBody.appendChild(tr);
    }
    updateAliasStatus(visible.length, list.length);
  }

  function collectAliases() {
    syncVisibleAliases();
    return (aliasesDoc.aliases || [])
      .map((block) => ({
        official: String(block.official || "").trim(),
        synonyms: (block.synonyms || []).map((s) => String(s).trim()).filter(Boolean),
      }))
      .filter((x) => x.official);
  }

  async function saveAliases() {
    const aliases = collectAliases();
    try {
      const res = await fetch("/api/aliases", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ aliases }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        aliasStatus.textContent = data.detail || "Ошибка сохранения";
        return;
      }
      aliasesDoc = data;
      renderAliases();
      const total = (data.aliases || []).length;
      const q = (aliasSearch.value || "").trim();
      aliasStatus.textContent = q
        ? `Сохранено: ${total}. Показано с учётом поиска.`
        : `Сохранено: ${total}`;
      log("Алиасы сохранены");
    } catch (e) {
      aliasStatus.textContent = e.message;
    }
  }

  $("btnAliasAdd").addEventListener("click", () => {
    syncVisibleAliases();
    if (!aliasesDoc.aliases) aliasesDoc.aliases = [];
    aliasesDoc.aliases.push({ official: "", synonyms: [] });
    aliasSearch.value = "";
    renderAliases();
    const last = aliasBody.querySelector("tr:last-child input[data-f='official']");
    if (last) last.focus();
  });
  $("btnAliasSave").addEventListener("click", saveAliases);
  aliasSearch.addEventListener("input", renderAliases);

  /* -------- excel log -------- */
  async function loadExcelLog() {
    try {
      const res = await fetch("/api/excel-log");
      const data = await res.json().catch(() => ({}));
      excelLogBody.innerHTML = "";
      const entries = data.entries || [];
      if (!entries.length) {
        excelLogBody.innerHTML = `<tr class="empty-row"><td colspan="6">Нет записей</td></tr>`;
        return;
      }
      for (const e of [...entries].reverse()) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${escapeHtml(e.report_date || "—")}</td>
          <td>${escapeHtml(String(e.day_sheet ?? "—"))}</td>
          <td class="num">${formatMoney(e.grand_total)}</td>
          <td class="num">${e.unmatched_count ?? 0}</td>
          <td>${escapeHtml((e.written_at || "").replace("T", " "))}</td>
          <td><code>${escapeHtml(e.report_id || "")}</code></td>`;
        excelLogBody.appendChild(tr);
      }
    } catch (e) {
      excelLogBody.innerHTML = `<tr class="empty-row"><td colspan="6">${escapeHtml(e.message)}</td></tr>`;
    }
  }

  $("btnRefreshLog").addEventListener("click", loadExcelLog);
  $("btnEmployeesSave").addEventListener("click", saveEmployees);
  if (btnModelSave) btnModelSave.addEventListener("click", saveModel);
  if (btnModelRefresh) btnModelRefresh.addEventListener("click", loadModelSettings);

  btnParse.addEventListener("click", parseReport);
  btnCalc.addEventListener("click", recalculate);
  if (btnSaveDb) btnSaveDb.addEventListener("click", saveToDb);
  btnExcel.addEventListener("click", writeExcel);
  btnCancelPreview.addEventListener("click", cancelPreview);
  btnNewMonth.addEventListener("click", createMonth);
  if (btnRefreshWorkbooks) btnRefreshWorkbooks.addEventListener("click", refreshWorkbooks);
  if (btnActivateMonth) {
    btnActivateMonth.addEventListener("click", () => activateMonth({ syncDate: true }));
  }
  if (btnEditTable) btnEditTable.addEventListener("click", editExistingTable);
  function onMonthSelectChange(select) {
    if (suppressMonthChange) return;
    const ym = select.value;
    setBothMonthSelects(ym);
    activateMonth({ syncDate: true, yearMonth: ym });
  }
  if (monthSelect) monthSelect.addEventListener("change", () => onMonthSelectChange(monthSelect));
  if (monthSelectSettings) {
    monthSelectSettings.addEventListener("change", () => onMonthSelectChange(monthSelectSettings));
  }
  reportDate.addEventListener("change", () => {
    syncDateIntoEditor();
    syncMonthSelectToReportDate();
    updateReportWorkbookHint({
      year_month: selectedYearMonth() || (reportDate.value || "").slice(0, 7),
    });
  });

  window.addEventListener("beforeunload", (e) => {
    if (priceDirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  const initial = (location.hash || "#report").replace("#", "") || "report";
  showView(["report", "price", "aliases", "settings", "excel-log", "help"].includes(initial) ? initial : "report");
  refreshWorkbooks();
  setStep(1);
  log("Готово. Загрузите отчёт или вставьте текст.");
})();
