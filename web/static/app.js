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
  const monthSelect = $("monthSelect");
  const activeWorkbookLabel = $("activeWorkbookLabel");
  const btnNewMonth = $("btnNewMonth");
  const btnActivateMonth = $("btnActivateMonth");
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
    [btnParse, btnCalc, btnSaveDb, btnExcel, btnNewMonth, btnActivateMonth, btnSelectFile, btnPaste].forEach((b) => {
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
  function showView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    document.querySelectorAll(".nav-link").forEach((a) => {
      a.classList.toggle("active", a.dataset.nav === name);
    });
    const view = document.getElementById(`view-${name}`);
    if (view) view.classList.add("active");
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
  }

  document.querySelectorAll("[data-nav]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      showView(el.dataset.nav);
    });
  });

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
        const li = document.createElement("li");
        li.innerHTML = `
          <span class="warn">!</span>
          <span>Проблемные работы (не найдено в прайсе): <strong>${escapeHtml(u.name)}</strong></span>
          <button type="button" class="btn outline btn-add-price">Добавить в прайс</button>`;
        li.querySelector(".btn-add-price").addEventListener("click", () => addUnmatchedToPrice(u));
        problemList.appendChild(li);
      }
    }
  }

  async function addUnmatchedToPrice(item) {
    await loadPrice(true);
    const exists = priceItems.some((p) => p.name.toLowerCase() === item.name.toLowerCase());
    if (exists) {
      log(`Уже есть в прайсе: ${item.name}`);
      showView("price");
      return;
    }
    priceItems.push({
      name: item.name,
      price: 0,
      unit: item.unit || "шт.",
      row: null,
    });
    priceDirty = true;
    renderPriceTable();
    showView("price");
    priceStatus.textContent = `Добавлено «${item.name}». Укажите цену и нажмите «Сохранить».`;
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
  function renderWorkbookList(data) {
    const active = data.active;
    activeWorkbookLabel.textContent = active
      ? `Активная книга: ${active.name || active.path}${active.year_month ? " (" + active.year_month + ")" : ""}`
      : "Активная книга: —";

    const items = data.items || [];
    monthSelect.innerHTML = "";
    if (!items.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Нет созданных месяцев";
      monthSelect.appendChild(opt);
      return;
    }
    for (const item of items) {
      const opt = document.createElement("option");
      opt.value = item.year_month || item.path;
      opt.textContent = `${item.year_month || item.name}${item.active ? " — активный" : ""}`;
      if (item.active) opt.selected = true;
      monthSelect.appendChild(opt);
    }
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

  async function createMonth() {
    const value = newMonth.value;
    if (!value) {
      log("Выберите месяц для создания");
      return;
    }
    const [y, m] = value.split("-").map(Number);
    setBusy(true);
    log(`Создание пустого месяца ${value}...`);
    try {
      const res = await fetch("/api/workbook/new", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ year: y, month: m, activate: true }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        log(`Ошибка: ${data.detail || res.statusText}`);
        return;
      }
      log(data.message || "Месяц создан");
      await refreshWorkbooks();
    } catch (e) {
      log(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function activateMonth() {
    const ym = monthSelect.value;
    if (!ym) {
      log("Нет месяца для активации");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/workbook/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ year_month: ym }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        log(`Ошибка активации: ${data.detail || res.statusText}`);
        return;
      }
      log(`Активна книга: ${data.active?.name || ym}`);
      await refreshWorkbooks();
    } catch (e) {
      log(e.message);
    } finally {
      setBusy(false);
    }
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
  btnActivateMonth.addEventListener("click", activateMonth);
  reportDate.addEventListener("change", syncDateIntoEditor);

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
