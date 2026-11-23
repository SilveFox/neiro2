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
  const btnParseRules = $("btnParseRules");
  const btnCalc = $("btnCalc");
  const btnSaveDb = $("btnSaveDb");
  const dbSaveStatus = $("dbSaveStatus");
  const btnExcel = $("btnExcel");
  const btnApplyPreview = $("btnApplyPreview");
  const btnCancelPreview = $("btnCancelPreview");
  const previewEditHint = $("previewEditHint");
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
  let previewDirty = false;
  let priceItems = [];
  let priceDirty = false;
  let aliasesDoc = { aliases: [] };
  const SERVICE_TYPES = ["Общее", "Интернет", "ТВ", "Комбо"];

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
    [btnParse, btnParseRules, btnCalc, btnSaveDb, btnExcel, btnApplyPreview, btnDownload, btnDownloadPeriod, btnNewMonth, btnActivateMonth, btnEditTable, btnSelectFile, btnPaste, monthSelect, monthSelectSettings].forEach((b) => {
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
  const downloadPeriodFrom = $("downloadPeriodFrom");
  const downloadPeriodTo = $("downloadPeriodTo");
  const btnDownload = $("btnDownload");
  const btnDownloadPeriod = $("btnDownloadPeriod");
  const btnRefreshWorkbooks = $("btnRefreshWorkbooks");
  const btnDeleteWorkbook = $("btnDeleteWorkbook");
  let suppressMonthChange = false;
  let lastActiveMeta = null;

  function closeMobileNav() {
    if (mainNav) mainNav.classList.remove("open");
    if (navToggle) navToggle.setAttribute("aria-expanded", "false");
  }

  const VIEW_NAMES = ["report", "price", "aliases", "settings", "excel-log", "db", "help"];
  let currentView = "";

  function viewFromHash() {
    const name = (location.hash || "#report").replace(/^#/, "") || "report";
    return VIEW_NAMES.includes(name) ? name : "report";
  }

  function showView(name, fromHash) {
    const same = currentView === name;
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    document.querySelectorAll(".nav-link").forEach((a) => {
      a.classList.toggle("active", a.dataset.nav === name);
    });
    const view = document.getElementById(`view-${name}`);
    if (view) view.classList.add("active");
    currentView = name;
    if (!fromHash && location.hash !== `#${name}`) location.hash = name;
    if (same) {
      closeMobileNav();
      return;
    }
    if (name === "report") {
      refreshWorkbooks();
      loadSites().catch(() => {});
    }
    if (name === "price") loadPrice();
    if (name === "aliases") loadAliases();
    if (name === "settings") {
      refreshWorkbooks();
      loadEmployees();
      loadHealth();
      loadModelSettings();
    }
    if (name === "excel-log") loadExcelLog();
    if (name === "db") loadDatabaseView();
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

  /* -------- preview (editable from report + calc amounts) -------- */
  function setPreviewDirty(on) {
    previewDirty = !!on;
    if (btnApplyPreview) btnApplyPreview.disabled = !previewDirty || !currentReport;
    if (previewEditHint) {
      previewEditHint.textContent = previewDirty
        ? "Есть несохранённые правки в таблице — нажмите «Применить правки»."
        : "Правьте ячейки прямо в таблице, затем «Применить правки» — JSON обновится и отчёт пересчитается.";
    }
  }

  function serviceTypeOptions(selected) {
    const cur = (selected || "Общее").trim() || "Общее";
    const values = SERVICE_TYPES.includes(cur) ? SERVICE_TYPES : [cur, ...SERVICE_TYPES];
    return values
      .map((v) => `<option value="${escapeHtml(v)}"${v === cur ? " selected" : ""}>${escapeHtml(v)}</option>`)
      .join("");
  }

  function findPricedForReportJob(calcWorker, reportJob) {
    const jobs = calcWorker?.jobs || [];
    if (!jobs.length) return null;
    const raw = String(reportJob?.raw_task_name || "").trim().toLowerCase();
    const desc = String(reportJob?.job_description || "").trim().toLowerCase();
    const vol = Number(reportJob?.volume);
    const unit = String(reportJob?.unit || "").trim().toLowerCase();
    const exact = jobs.find((j) => {
      const jr = String(j.raw_task_name || "").trim().toLowerCase();
      const jd = String(j.job_description || "").trim().toLowerCase();
      const ju = String(j.unit || "").trim().toLowerCase();
      const sameName = (raw && (jr === raw || jd === raw)) || (desc && (jr === desc || jd === desc));
      if (!sameName) return false;
      if (unit && ju && ju !== unit) return false;
      if (Number.isFinite(vol) && j.volume != null && Number(j.volume) !== vol) return false;
      return true;
    });
    if (exact) return exact;
    return (
      jobs.find((j) => {
        const jr = String(j.raw_task_name || "").trim().toLowerCase();
        const jd = String(j.job_description || "").trim().toLowerCase();
        return (raw && (jr === raw || jd === raw)) || (desc && (jr === desc || jd === desc));
      }) || null
    );
  }

  function markPreviewInputsDirty(tr) {
    tr.querySelectorAll("input, select").forEach((el) => {
      el.addEventListener("input", () => setPreviewDirty(true));
      el.addEventListener("change", () => setPreviewDirty(true));
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          applyPreviewAndRecalc();
        }
      });
    });
  }

  function fitFioInput(input) {
    if (!input) return;
    const text = input.value || input.placeholder || "ФИО";
    let probe = fitFioInput.probe;
    if (!probe) {
      probe = document.createElement("span");
      probe.setAttribute("aria-hidden", "true");
      probe.style.cssText = "position:fixed;left:-9999px;top:0;visibility:hidden;white-space:pre;pointer-events:none;";
      document.body.appendChild(probe);
      fitFioInput.probe = probe;
    }
    const cs = getComputedStyle(input);
    probe.style.font = cs.font;
    probe.style.letterSpacing = cs.letterSpacing;
    probe.textContent = text;
    const pad = (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
    const border = (parseFloat(cs.borderLeftWidth) || 0) + (parseFloat(cs.borderRightWidth) || 0);
    input.style.width = `${Math.ceil(probe.getBoundingClientRect().width + pad + border + 10)}px`;
  }

  function fitAllFioInputs() {
    previewBody.querySelectorAll('input[data-f="fio"]').forEach(fitFioInput);
  }

  function showCalc(calculation) {
    currentCalc = calculation || null;
    previewBody.innerHTML = "";
    problemList.innerHTML = "";

    let report = currentReport;
    if (!report && jsonEditor.value.trim()) {
      try {
        report = JSON.parse(jsonEditor.value);
        currentReport = report;
      } catch (_) {
        report = null;
      }
    }

    const workers = report?.workers || [];
    if (!workers.length) {
      previewBody.innerHTML = `<tr class="empty-row"><td colspan="8">Нет данных расчёта</td></tr>`;
      previewMeta.textContent = "Нет данных — загрузите отчёт";
      previewTotal.textContent = "";
      problemList.innerHTML = `<li class="muted">Пока нет проблемных работ</li>`;
      btnExcel.disabled = true;
      if (btnApplyPreview) btnApplyPreview.disabled = true;
      setPreviewDirty(false);
      return;
    }

    const unmatched = [];
    let jobCount = 0;

    workers.forEach((w, wi) => {
      const members = Array.isArray(w.members) ? w.members.filter(Boolean) : [];
      const fio = (members.length ? members.join(", ") : w.raw_worker_name) || "";
      const jobs = Array.isArray(w.performed_jobs) ? w.performed_jobs : [];
      const calcWorker = (calculation?.workers || [])[wi];

      if (!jobs.length) {
        const tr = document.createElement("tr");
        tr.dataset.w = String(wi);
        tr.innerHTML = `
          <td><input data-f="fio" type="text" value="${escapeHtml(fio)}" placeholder="ФИО" /></td>
          <td colspan="6" class="muted">Нет работ — добавьте строку</td>
          <td></td>`;
        const addBtn = document.createElement("button");
        addBtn.type = "button";
        addBtn.className = "btn outline";
        addBtn.textContent = "+ работа";
        addBtn.addEventListener("click", () => addPreviewJob(wi));
        tr.querySelector("td:last-child").appendChild(addBtn);
        markPreviewInputsDirty(tr);
        previewBody.appendChild(tr);
        return;
      }

      jobs.forEach((j, ji) => {
        jobCount += 1;
        const priced = findPricedForReportJob(calcWorker, j);
        const isUnmatched = !priced || priced.matched === false || !priced.matched_name;
        const displayName = j.job_description || j.raw_task_name || "";
        const volume = j.volume ?? "";
        const unit = j.unit || "шт";
        const serviceType = j.service_type || "Общее";
        const tariff = isUnmatched ? "—" : formatMoney(priced.unit_price);
        const amount =
          isUnmatched || priced.amount == null
            ? "—"
            : formatMoney(
                Number(priced.volume) === Number(volume) ? priced.amount : Number(volume) * Number(priced.unit_price || 0)
              );

        const tr = document.createElement("tr");
        tr.dataset.w = String(wi);
        tr.dataset.j = String(ji);
        if (isUnmatched) tr.classList.add("unmatched");
        tr.innerHTML = `
          <td><input data-f="fio" type="text" value="${escapeHtml(fio)}" placeholder="ФИО" /></td>
          <td>
            <input data-f="name" type="text" value="${escapeHtml(displayName)}" placeholder="Наименование работы" />
            ${priced?.matched_name && priced.matched_name !== displayName ? `<div class="preview-matched muted">→ ${escapeHtml(priced.matched_name)}</div>` : ""}
          </td>
          <td class="num"><input data-f="volume" type="number" step="any" min="0" value="${escapeHtml(String(volume))}" /></td>
          <td><input data-f="unit" type="text" value="${escapeHtml(unit)}" /></td>
          <td><select data-f="service_type">${serviceTypeOptions(serviceType)}</select></td>
          <td class="num">${escapeHtml(String(tariff))}</td>
          <td class="num">${escapeHtml(String(amount))}</td>
          <td class="preview-actions"></td>`;

        const actions = tr.querySelector(".preview-actions");
        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn danger";
        delBtn.title = "Удалить работу";
        delBtn.textContent = "✕";
        delBtn.addEventListener("click", () => removePreviewJob(wi, ji));
        actions.appendChild(delBtn);
        if (ji === jobs.length - 1) {
          const addBtn = document.createElement("button");
          addBtn.type = "button";
          addBtn.className = "btn outline";
          addBtn.title = "Добавить работу";
          addBtn.textContent = "+";
          addBtn.addEventListener("click", () => addPreviewJob(wi));
          actions.appendChild(addBtn);
        }

        markPreviewInputsDirty(tr);
        // Keep FIO in sync across rows of the same worker
        const fioInput = tr.querySelector('[data-f="fio"]');
        fioInput.addEventListener("input", () => {
          const val = fioInput.value;
          previewBody.querySelectorAll(`tr[data-w="${wi}"] input[data-f="fio"]`).forEach((inp) => {
            if (inp !== fioInput) inp.value = val;
            fitFioInput(inp);
          });
        });
        previewBody.appendChild(tr);

        if (isUnmatched) {
          unmatched.push({
            name: j.raw_task_name || j.job_description || "Без названия",
            description: j.job_description || "",
            unit: j.unit || "шт",
          });
        }
      });
    });

    const date = calculation?.report_date || report.report_date || reportDate.value || "—";
    previewMeta.textContent = `Дата ${date} · работ: ${jobCount} · не найдено: ${calculation?.unmatched_count ?? unmatched.length}`;
    previewTotal.textContent = calculation ? `Итого: ${formatMoney(calculation.grand_total)}` : "";
    fitAllFioInputs();
    btnExcel.disabled = false;
    setPreviewDirty(false);
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

  function collectPreviewEditsIntoReport() {
    const report = currentReport || (jsonEditor.value.trim() ? JSON.parse(jsonEditor.value) : null);
    if (!report || !Array.isArray(report.workers)) {
      throw new Error("Нет отчёта для применения правок");
    }
    const byWorker = new Map();
    previewBody.querySelectorAll("tr[data-w]").forEach((tr) => {
      const wi = Number(tr.dataset.w);
      if (!Number.isFinite(wi) || !report.workers[wi]) return;
      if (!byWorker.has(wi)) byWorker.set(wi, { fio: "", jobs: [] });
      const bucket = byWorker.get(wi);
      const fioEl = tr.querySelector('[data-f="fio"]');
      if (fioEl) bucket.fio = fioEl.value.trim();
      const nameEl = tr.querySelector('[data-f="name"]');
      if (!nameEl) return;
      const name = nameEl.value.trim();
      const volumeRaw = tr.querySelector('[data-f="volume"]')?.value ?? "";
      const volume = parseFloat(String(volumeRaw).replace(",", "."));
      const unit = (tr.querySelector('[data-f="unit"]')?.value || "шт").trim() || "шт";
      const service_type =
        (tr.querySelector('[data-f="service_type"]')?.value || "Общее").trim() || "Общее";
      if (!name) return;
      bucket.jobs.push({
        raw_task_name: name,
        job_description: name,
        service_type,
        volume: Number.isFinite(volume) ? volume : 0,
        unit,
      });
    });

    byWorker.forEach((bucket, wi) => {
      const w = report.workers[wi];
      const fio = bucket.fio;
      if (fio) {
        const members = fio.split(/[,;]+/).map((s) => s.trim()).filter(Boolean);
        w.members = members.length ? members : [fio];
        w.raw_worker_name = members.length > 1 ? members.join(", ") : members[0] || fio;
      }
      w.performed_jobs = bucket.jobs;
    });

    currentReport = report;
    jsonEditor.value = JSON.stringify(report, null, 2);
    setPreviewDirty(false);
    return report;
  }

  function removePreviewJob(workerIdx, jobIdx) {
    try {
      collectPreviewEditsIntoReport();
    } catch (_) {
      /* keep going with currentReport */
    }
    const report = currentReport;
    if (!report?.workers?.[workerIdx]) return;
    const jobs = report.workers[workerIdx].performed_jobs || [];
    jobs.splice(jobIdx, 1);
    report.workers[workerIdx].performed_jobs = jobs;
    currentReport = report;
    jsonEditor.value = JSON.stringify(report, null, 2);
    setPreviewDirty(true);
    showCalc(currentCalc);
    setPreviewDirty(true);
  }

  function addPreviewJob(workerIdx) {
    try {
      collectPreviewEditsIntoReport();
    } catch (_) {
      /* ignore */
    }
    const report = currentReport;
    if (!report?.workers?.[workerIdx]) return;
    if (!Array.isArray(report.workers[workerIdx].performed_jobs)) {
      report.workers[workerIdx].performed_jobs = [];
    }
    report.workers[workerIdx].performed_jobs.push({
      raw_task_name: "",
      job_description: "",
      service_type: "Общее",
      volume: 1,
      unit: "шт",
    });
    currentReport = report;
    jsonEditor.value = JSON.stringify(report, null, 2);
    showCalc(currentCalc);
    setPreviewDirty(true);
    const rows = previewBody.querySelectorAll(`tr[data-w="${workerIdx}"]`);
    const last = rows[rows.length - 1];
    last?.querySelector('[data-f="name"]')?.focus();
  }

  async function applyPreviewAndRecalc() {
    try {
      collectPreviewEditsIntoReport();
    } catch (e) {
      log(e.message);
      return;
    }
    await recalculate();
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
    if (previewDirty && previewBody.querySelector("tr[data-w]")) {
      try {
        collectPreviewEditsIntoReport();
      } catch (_) {
        /* fall back to JSON editor */
      }
    }
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

  function applyParseResult(data, elapsed, modeLabel) {
    currentReport = data.report;
    jsonEditor.value = JSON.stringify(data.report, null, 2);
    if (data.extracted_text) reportText.value = data.extracted_text;
    showCalc(data.calculation);
    setStep(3);
    const workers = (data.report.workers || []).length;
    const mode = modeLabel || (data.parse_mode === "rules" ? "без ИИ" : "ИИ");
    log(`Разбор (${mode}) успешен за ${elapsed}. Сотрудников: ${workers}.`);
    if (data.calculation?.unmatched_count) {
      log(`Не сопоставлено с прайсом: ${data.calculation.unmatched_count}`);
    }
  }

  /* -------- parse / calc / excel -------- */
  async function parseReport({ useAi = true } = {}) {
    const text = reportText.value.trim();
    if (!text) {
      log("Ошибка: пустой текст отчёта");
      return;
    }
    setBusy(true);
    startTimer();
    setStep(2);
    log(useAi ? "Отправка отчёта в модель..." : "Разбор без ИИ (правила)...");
    try {
      const res = await fetch("/api/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report_text: text,
          extra_prompt: useAi ? extraPrompt.value.trim() : "",
          report_date: reportDate.value || null,
          use_ai: useAi,
        }),
      });
      const data = await res.json().catch(() => ({}));
      const elapsed = stopTimer();
      if (!res.ok) {
        log(`Ошибка (${elapsed}): ${data.detail || res.statusText}`);
        setStep(1);
        return;
      }
      applyParseResult(data, elapsed, useAi ? "ИИ" : "без ИИ");
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
      const siteRaw = saveSiteSelect && saveSiteSelect.value ? Number(saveSiteSelect.value) : null;
      const res = await fetch("/api/reports/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report,
          calculation,
          source_text: reportText.value.trim() || null,
          report_date: report.report_date,
          site_id: Number.isFinite(siteRaw) ? siteRaw : null,
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
        const siteLabel = data.site_name ? ` · ${data.site_name}` : "";
        const skipped = data.skipped_unpriced
          ? ` · без прайса не записано ${data.skipped_unpriced}`
          : "";
        dbSaveStatus.textContent = `Сохранено · id ${data.id}${siteLabel} · ${data.workers_names || data.report_date || ""} · работ ${data.jobs_count ?? "—"}${skipped} · ${data.grand_total ?? 0} ₽`;
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
    previewDirty = false;
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
    lastActiveMeta = active || null;
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
    // Список показывает ту же книгу, что подпись «Активная таблица», а не прошлый выбор.
    const preferred = selectedActive || monthSelect?.value || monthSelectSettings?.value || "";
    suppressMonthChange = true;
    fillMonthSelect(monthSelect, items, preferred, selectedActive);
    fillMonthSelect(monthSelectSettings, items, preferred, selectedActive);
    suppressMonthChange = false;
    const ym =
      (active && active.year_month) ||
      (workbookItemsByName[preferred] && workbookItemsByName[preferred].year_month) ||
      "";
    if (ym) syncDownloadPeriodDefaults(ym);
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

  function workbookNameForDownload() {
    const key = selectedWorkbookKey();
    if (key && key.toLowerCase().endsWith(".xlsx")) return key;
    const activeName = String(lastActiveMeta?.name || "").trim();
    return activeName;
  }

  async function saveExcelBlob(blob, filename) {
    const a = document.createElement("a");
    const href = URL.createObjectURL(blob);
    a.href = href;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(href);
  }

  function filenameFromDisposition(header, fallback) {
    const match = /filename\*?=(?:UTF-8''|")?([^\";]+)/i.exec(header || "");
    let filename = match ? decodeURIComponent(match[1].replace(/"/g, "")) : fallback;
    if (!filename.toLowerCase().endsWith(".xlsx")) filename += ".xlsx";
    return filename;
  }

  async function downloadActiveExcel() {
    const name = workbookNameForDownload();
    if (!name) {
      if (workbookEditStatus) workbookEditStatus.textContent = "Нет активной таблицы";
      return;
    }
    setBusy(true);
    try {
      const url = `/api/download-excel?name=${encodeURIComponent(name)}`;
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || res.statusText);
      }
      const blob = await res.blob();
      const filename = filenameFromDisposition(res.headers.get("content-disposition"), name);
      await saveExcelBlob(blob, filename);
      log(`Скачана таблица ${filename}`);
      if (workbookEditStatus) workbookEditStatus.textContent = `Скачан файл ${filename}`;
    } catch (e) {
      log(`Ошибка скачивания: ${e.message}`);
      if (workbookEditStatus) workbookEditStatus.textContent = e.message;
    } finally {
      setBusy(false);
    }
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

  async function deleteSelectedWorkbook() {
    const key = selectedWorkbookKey();
    const item = key ? workbookItemsByName[key] : null;
    const name = (item && item.name) || (key && key.toLowerCase().endsWith(".xlsx") ? key : "");
    if (!name) {
      if (workbookEditStatus) workbookEditStatus.textContent = "Выберите таблицу в списке";
      return;
    }
    const label = item ? workbookDisplayName(item) : name;
    if (!(await askDbConfirm("Вы точно хотите удалить таблицу?"))) return;
    if (workbookEditStatus) workbookEditStatus.textContent = `Удаление ${label}…`;
    setBusy(true);
    try {
      const res = await fetch("/api/workbook/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Не удалось удалить таблицу");
      const msg = data.message || `Таблица «${label}» удалена`;
      log(msg);
      if (workbookEditStatus) workbookEditStatus.textContent = msg;
      await refreshWorkbooks();
    } catch (e) {
      if (workbookEditStatus) workbookEditStatus.textContent = e.message;
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

  function syncDownloadPeriodDefaults(ym) {
    if (!downloadPeriodFrom || !downloadPeriodTo) return;
    const month = String(ym || "").trim();
    if (!/^\d{4}-\d{2}$/.test(month)) return;
    const year = Number(month.slice(0, 4));
    const mon = Number(month.slice(5, 7));
    const lastDay = new Date(year, mon, 0).getDate();
    const from = `${month}-01`;
    const to = `${month}-${String(lastDay).padStart(2, "0")}`;
    if (!downloadPeriodFrom.value || downloadPeriodFrom.value.slice(0, 7) !== month) {
      downloadPeriodFrom.value = from;
    }
    if (!downloadPeriodTo.value || downloadPeriodTo.value.slice(0, 7) !== month) {
      downloadPeriodTo.value = to;
    }
    downloadPeriodFrom.min = from;
    downloadPeriodFrom.max = to;
    downloadPeriodTo.min = from;
    downloadPeriodTo.max = to;
  }

  async function downloadPeriodExcel() {
    const from = (downloadPeriodFrom?.value || "").trim();
    const to = (downloadPeriodTo?.value || "").trim();
    if (!from || !to) {
      if (workbookEditStatus) workbookEditStatus.textContent = "Укажите даты «с» и «по»";
      return;
    }
    if (from > to) {
      if (workbookEditStatus) workbookEditStatus.textContent = "Дата «с» не может быть позже «по»";
      return;
    }
    const name = workbookNameForDownload();
    setBusy(true);
    try {
      const params = new URLSearchParams({ from, to });
      if (name) params.set("name", name);
      const url = `/api/download-excel-period?${params.toString()}`;
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || res.statusText);
      }
      const blob = await res.blob();
      const filename = filenameFromDisposition(
        res.headers.get("content-disposition"),
        name || `period_${from}_${to}.xlsx`
      );
      await saveExcelBlob(blob, filename);
      log(`Скачан файл ${filename} за период ${from}…${to}`);
      if (workbookEditStatus) workbookEditStatus.textContent = "";
    } catch (e) {
      log(`Ошибка скачивания за период: ${e.message}`);
      if (workbookEditStatus) workbookEditStatus.textContent = e.message;
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

  /* -------- database browser -------- */
  const saveSiteSelect = $("saveSiteSelect");
  const dbBody = $("dbBody");
  const dbSheet = $("dbSheet");
  const dbTabs = $("dbTabs");
  const dbFoldersPanel = $("dbFoldersPanel");
  const dbFolderList = $("dbFolderList");
  const dbTablePanel = $("dbTablePanel");
  const dbSheetCaption = $("dbSheetCaption");
  const dbSummary = $("dbSummary");
  const dbStatus = $("dbStatus");
  const dbSiteStatus = $("dbSiteStatus");
  const dbSiteSelect = $("dbSiteSelect");
  const dbDateFrom = $("dbDateFrom");
  const dbDateTo = $("dbDateTo");
  const dbFio = $("dbFio");
  const siteList = $("siteList");
  const newSiteName = $("newSiteName");
  let dbSitesPayload = { sites: [], unassigned_count: 0, reports_total: 0 };
  let dbFilter = { site: "", from: "", to: "", fio: "" };
  let dbReports = [];
  let dbEditing = null;
  /** Open folder tabs: { id, report }. The folder list itself is not stored here. */
  let dbOpenTabs = [];
  let dbActiveTab = "folders";

  function formatDateRu(iso) {
    if (!iso) return "—";
    const [y, m, d] = String(iso).slice(0, 10).split("-");
    if (!y || !m || !d) return String(iso);
    return `${d}.${m}.${y}`;
  }

  function formatQty(n) {
    if (n == null || n === "") return "—";
    const v = Number(n);
    if (Number.isNaN(v)) return "—";
    return v.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
  }

  function jobsCountLabel(n) {
    const abs = Math.abs(Number(n) || 0);
    const n10 = abs % 10;
    const n100 = abs % 100;
    if (n10 === 1 && n100 !== 11) return "строка";
    if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return "строки";
    return "строк";
  }

  function dbIconButton(action, idAttr, id, label, kind) {
    const pencil = `<path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3z"/><path d="M13.5 6.5l3 3"/>`;
    const trash = `<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M7 7l1 13h8l1-13"/><path d="M10 11v6"/><path d="M14 11v6"/>`;
    return `<button type="button" class="db-pencil${kind === "trash" ? " db-trash" : ""}" data-db-action="${action}" ${idAttr}="${id}" aria-label="${label}" title="${label}">
      <svg viewBox="0 0 24 24" aria-hidden="true">${kind === "trash" ? trash : pencil}</svg>
    </button>`;
  }

  function dbSiteOptions(selected) {
    const sites = dbSitesPayload.sites || [];
    const current = selected == null ? "" : String(selected);
    return `<option value="">Без участка</option>${sites
      .map((s) => `<option value="${s.id}"${String(s.id) === current ? " selected" : ""}>${escapeHtml(s.name)}</option>`)
      .join("")}`;
  }

  function syncOpenTabs(reports) {
    for (const tab of dbOpenTabs) {
      const fresh = reports.find((item) => item.id === tab.id);
      if (fresh) tab.report = fresh;
    }
  }

  function closeDbTab(reportId) {
    const id = Number(reportId);
    dbOpenTabs = dbOpenTabs.filter((tab) => tab.id !== id);
    if (dbActiveTab === id) dbActiveTab = "folders";
    if (dbEditing && dbEditing.type === "job") {
      const stillVisible = dbOpenTabs.some((tab) =>
        (tab.report.jobs || []).some((row) => row.job_id === dbEditing.id)
      );
      if (!stillVisible) dbEditing = null;
    }
    if (dbEditing && dbEditing.type === "report" && dbEditing.id === id) dbEditing = null;
  }

  function openDbFolder(reportId) {
    const report = dbReports.find((item) => item.id === Number(reportId));
    if (!report) return;
    const existing = dbOpenTabs.find((tab) => tab.id === report.id);
    if (existing) existing.report = report;
    else dbOpenTabs.push({ id: report.id, report });
    dbActiveTab = report.id;
    renderDbBrowser();
  }

  function renderDbTabs() {
    if (!dbTabs) return;
    if (!dbOpenTabs.length) {
      dbTabs.hidden = true;
      dbTabs.innerHTML = "";
      return;
    }
    dbTabs.hidden = false;
    dbTabs.innerHTML = "";
    const foldersBtn = document.createElement("button");
    foldersBtn.type = "button";
    foldersBtn.className = `db-tab${dbActiveTab === "folders" ? " active" : ""}`;
    foldersBtn.dataset.dbTab = "folders";
    foldersBtn.setAttribute("role", "tab");
    foldersBtn.textContent = "Папки";
    dbTabs.appendChild(foldersBtn);
    for (const tab of dbOpenTabs) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `db-tab${dbActiveTab === tab.id ? " active" : ""}`;
      btn.dataset.dbTab = String(tab.id);
      btn.setAttribute("role", "tab");
      const title = tab.report.title || "Отчёт";
      btn.innerHTML = `<span class="db-tab-title">${escapeHtml(title)}</span><span class="db-tab-close" data-db-close="${tab.id}" role="button" aria-label="Закрыть вкладку">×</span>`;
      dbTabs.appendChild(btn);
    }
  }

  function renderDbFolderList(reports) {
    if (!dbFolderList) return;
    dbFolderList.innerHTML = "";
    if (!reports.length) {
      dbFolderList.innerHTML = `<p class="db-folder-empty">Нет записей по этому фильтру. Сохраните отчёт кнопкой «Сохранить в БД».</p>`;
      return;
    }
    for (const folder of reports) {
      const jobs = folder.jobs || [];
      const count = jobs.length;
      const card = document.createElement("div");
      card.className = "db-folder-card";
      card.dataset.report = String(folder.id);
      const editingFolder = dbEditing && dbEditing.type === "report" && dbEditing.id === folder.id;
      if (editingFolder) {
        const dateValue = String(folder.report_date || "").slice(0, 10);
        card.innerHTML = `
          <div class="db-folder-bar">
            <input class="db-inline-input" id="dbEditDate" type="date" value="${escapeHtml(dateValue)}" aria-label="Дата отчёта" />
            <select class="db-inline-input" id="dbEditSite" aria-label="Участок">${dbSiteOptions(folder.site_id)}</select>
            <div class="db-inline-actions">
              <button type="button" class="btn primary" data-db-action="save-report" data-report="${folder.id}">Сохранить</button>
              <button type="button" class="btn outline" data-db-action="cancel-db">Отмена</button>
            </div>
          </div>`;
      } else {
        card.innerHTML = `
          <div class="db-folder-bar">
            <button type="button" class="db-folder-btn" data-report="${folder.id}">
              <span class="db-folder-mark" aria-hidden="true"></span>
              <span class="db-folder-title">${escapeHtml(folder.title || "Отчёт")}</span>
              <span class="db-folder-meta">${escapeHtml(folder.site_name || "Без участка")} · ${count} ${jobsCountLabel(count)} · ${formatMoney(folder.amount)} ₽</span>
            </button>
            <div class="db-folder-edit">
              ${dbIconButton("edit-report", "data-report", folder.id, "Изменить", "pencil")}
              ${dbIconButton("delete-report", "data-report", folder.id, "Удалить отчёт", "trash")}
            </div>
          </div>`;
      }
      dbFolderList.appendChild(card);
    }
  }

  function renderDbJobs(folder) {
    if (!dbBody) return;
    const jobs = (folder && folder.jobs) || [];
    if (dbSheetCaption) {
      const count = jobs.length;
      dbSheetCaption.textContent = folder
        ? `${folder.site_name || "Без участка"} · ${formatDateRu(folder.report_date)} · ${count} ${jobsCountLabel(count)} · ${formatMoney(folder.amount)} ₽`
        : "";
    }
    dbBody.innerHTML = "";
    if (!jobs.length) {
      dbBody.innerHTML = `<tr class="empty-row"><td colspan="7">В этом отчёте нет работ из прайса</td></tr>`;
      return;
    }
    for (const row of jobs) {
      const tr = document.createElement("tr");
      tr.dataset.report = String(folder.id);
      const editingJob = dbEditing && dbEditing.type === "job" && dbEditing.id === row.job_id;
      if (editingJob) {
        const work = row.matched_name || row.task_name || "";
        tr.innerHTML = `
          <td><input class="db-inline-input" id="dbEditFio" value="${escapeHtml(row.worker_name || "")}" aria-label="ФИО" /></td>
          <td><input class="db-inline-input" id="dbEditTask" value="${escapeHtml(work)}" aria-label="Работа" /></td>
          <td><input class="db-inline-input" id="dbEditVolume" type="number" min="0" step="any" value="${row.volume ?? ""}" aria-label="Объём" /></td>
          <td><input class="db-inline-input" id="dbEditUnit" value="${escapeHtml(row.unit || "")}" aria-label="Единица" /></td>
          <td><input class="db-inline-input" id="dbEditPrice" type="number" min="0" step="any" value="${row.unit_price ?? ""}" aria-label="Тариф" /></td>
          <td class="num" id="dbEditAmount">${row.amount == null ? "—" : formatMoney(row.amount)}</td>
          <td>
            <div class="db-inline-actions">
              <button type="button" class="btn primary" data-db-action="save-job" data-job="${row.job_id}">Сохранить</button>
              <button type="button" class="btn outline" data-db-action="cancel-db">Отмена</button>
            </div>
          </td>`;
      } else {
        if (!row.matched) tr.classList.add("unmatched");
        const work = row.matched_name || row.task_name || "—";
        tr.innerHTML = `
          <td>${escapeHtml(row.worker_name || "—")}</td>
          <td>${escapeHtml(work)}</td>
          <td class="num">${formatQty(row.volume)}</td>
          <td>${escapeHtml(row.unit || "—")}</td>
          <td class="num">${row.unit_price == null ? "—" : formatMoney(row.unit_price)}</td>
          <td class="num">${row.amount == null ? "—" : formatMoney(row.amount)}</td>
          <td><div class="db-folder-edit">${dbIconButton("edit-job", "data-job", row.job_id, "Изменить", "pencil")}${dbIconButton("delete-job", "data-job", row.job_id, "Удалить строку", "trash")}</div></td>`;
      }
      dbBody.appendChild(tr);
    }
  }

  function renderDbBrowser() {
    renderDbFolderList(dbReports);
    renderDbTabs();
    const showTable = dbActiveTab !== "folders";
    if (dbFoldersPanel) dbFoldersPanel.hidden = showTable;
    if (dbTablePanel) dbTablePanel.hidden = !showTable;
    if (!showTable) return;
    const tab = dbOpenTabs.find((item) => item.id === dbActiveTab);
    if (!tab) {
      dbActiveTab = "folders";
      if (dbFoldersPanel) dbFoldersPanel.hidden = false;
      if (dbTablePanel) dbTablePanel.hidden = true;
      renderDbTabs();
      return;
    }
    renderDbJobs(tab.report);
  }

  function previewDbAmount() {
    const volume = document.getElementById("dbEditVolume");
    const price = document.getElementById("dbEditPrice");
    const out = document.getElementById("dbEditAmount");
    if (!volume || !price || !out) return;
    const vol = Number(String(volume.value).replace(",", "."));
    const cost = Number(String(price.value).replace(",", "."));
    if (!Number.isFinite(vol) || !Number.isFinite(cost)) {
      out.textContent = "—";
      return;
    }
    out.textContent = formatMoney(Math.round(vol * cost * 100) / 100);
  }

  function renderSiteControls() {
    const sites = dbSitesPayload.sites || [];
    const savedSite = saveSiteSelect ? saveSiteSelect.value : "";
    if (saveSiteSelect) {
      saveSiteSelect.innerHTML = `<option value="">Без участка</option>${sites
        .map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`)
        .join("")}`;
      if ([...saveSiteSelect.options].some((o) => o.value === savedSite)) {
        saveSiteSelect.value = savedSite;
      }
    }
    if (dbSiteSelect) {
      dbSiteSelect.innerHTML = `<option value="">Все участки</option><option value="__none__">Без участка</option>${sites
        .map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`)
        .join("")}`;
      if ([...dbSiteSelect.options].some((o) => o.value === dbFilter.site)) {
        dbSiteSelect.value = dbFilter.site;
      } else {
        dbFilter.site = "";
        dbSiteSelect.value = "";
      }
    }
    if (!siteList) return;
    const items = [
      { value: "", label: "Все участки", count: dbSitesPayload.reports_total || 0 },
      ...sites.map((s) => ({
        value: String(s.id),
        label: s.name,
        count: s.reports_count || 0,
      })),
      { value: "__none__", label: "Без участка", count: dbSitesPayload.unassigned_count || 0 },
    ];
    siteList.innerHTML = "";
    for (const item of items) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `site-item${dbFilter.site === item.value ? " active" : ""}`;
      btn.innerHTML = `<span>${escapeHtml(item.label)}</span><span class="site-count">${item.count}</span>`;
      btn.addEventListener("click", () => {
        dbFilter.site = item.value;
        if (dbSiteSelect) dbSiteSelect.value = item.value;
        renderSiteControls();
        loadDbRows();
      });
      siteList.appendChild(btn);
    }
  }

  async function loadSites() {
    const res = await fetch("/api/sites");
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Не удалось загрузить участки");
    dbSitesPayload = data;
    renderSiteControls();
    return data;
  }

  function syncDbFilterFromForm() {
    dbFilter = {
      site: dbSiteSelect ? dbSiteSelect.value : "",
      from: dbDateFrom ? dbDateFrom.value : "",
      to: dbDateTo ? dbDateTo.value : "",
      fio: dbFio ? dbFio.value.trim() : "",
    };
  }

  function writeDbFilterToForm() {
    if (dbSiteSelect) dbSiteSelect.value = dbFilter.site;
    if (dbDateFrom) dbDateFrom.value = dbFilter.from;
    if (dbDateTo) dbDateTo.value = dbFilter.to;
    if (dbFio) dbFio.value = dbFilter.fio;
  }

  async function loadDbRows(options = {}) {
    if (!dbBody) return;
    if (dbStatus && !options.keepStatus) dbStatus.textContent = "";
    const params = new URLSearchParams();
    if (dbFilter.site === "__none__") params.set("unassigned", "true");
    else if (dbFilter.site) params.set("site_id", dbFilter.site);
    if (dbFilter.from) params.set("from", dbFilter.from);
    if (dbFilter.to) params.set("to", dbFilter.to);
    if (dbFilter.fio) params.set("fio", dbFilter.fio);
    try {
      const res = await fetch(`/api/db/rows?${params.toString()}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Не удалось прочитать базу");
      dbReports = data.reports || [];
      syncOpenTabs(dbReports);
      const reports = dbReports;
      const summary = data.summary || {};
      if (dbSummary) {
        dbSummary.innerHTML = `
          <span class="db-stat">Отчётов: ${summary.reports ?? 0}</span>
          <span class="db-stat">Строк: ${summary.jobs ?? 0}</span>
          <span class="db-stat">ФИО: ${summary.workers ?? 0}</span>
          <span class="db-stat">Сумма: ${formatMoney(summary.amount)} ₽</span>`;
      }
      renderDbBrowser();
      if (dbStatus && summary.truncated) {
        dbStatus.textContent = `Показаны первые ${reports.length} отчётов. Сузьте фильтр, чтобы увидеть остальные.`;
      }
    } catch (e) {
      if (dbStatus) dbStatus.textContent = e.message;
      if (dbFolderList) {
        dbFolderList.innerHTML = `<p class="db-folder-empty">${escapeHtml(e.message)}</p>`;
      }
    }
  }

  async function loadDatabaseView() {
    try {
      await loadSites();
      writeDbFilterToForm();
      await loadDbRows();
    } catch (e) {
      if (dbStatus) dbStatus.textContent = e.message;
    }
  }

  async function createSite(event) {
    event.preventDefault();
    if (dbSiteStatus) dbSiteStatus.textContent = "";
    const name = (newSiteName && newSiteName.value.trim()) || "";
    if (!name) {
      if (dbSiteStatus) dbSiteStatus.textContent = "Введите название участка";
      return;
    }
    try {
      const res = await fetch("/api/sites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Не удалось создать участок");
      if (newSiteName) newSiteName.value = "";
      if (dbSiteStatus) dbSiteStatus.textContent = data.message || `Участок «${data.name}» создан`;
      dbFilter.site = String(data.id);
      if (saveSiteSelect) saveSiteSelect.value = String(data.id);
      await loadSites();
      if (saveSiteSelect) saveSiteSelect.value = String(data.id);
      await loadDbRows();
    } catch (e) {
      if (dbSiteStatus) dbSiteStatus.textContent = e.message;
    }
  }

  const siteCreateForm = $("siteCreateForm");
  const dbFilterForm = $("dbFilterForm");
  if (siteCreateForm) siteCreateForm.addEventListener("submit", createSite);
  if (dbFilterForm) {
    dbFilterForm.addEventListener("submit", (event) => {
      event.preventDefault();
      syncDbFilterFromForm();
      renderSiteControls();
      loadDbRows();
    });
  }
  const btnDbReset = $("btnDbReset");
  if (btnDbReset) {
    btnDbReset.addEventListener("click", () => {
      dbFilter = { site: "", from: "", to: "", fio: "" };
      writeDbFilterToForm();
      renderSiteControls();
      loadDbRows();
    });
  }
  const btnDbRefresh = $("btnDbRefresh");
  if (btnDbRefresh) btnDbRefresh.addEventListener("click", loadDatabaseView);

  const dbExport = $("dbExport");
  const dbExportList = $("dbExportList");
  const dbExportAll = $("dbExportAll");
  const dbExportStatus = $("dbExportStatus");
  const dbExportYes = $("dbExportYes");

  function syncDbExportAll() {
    if (!dbExportList || !dbExportAll) return;
    const boxes = [...dbExportList.querySelectorAll("input[data-report]")];
    const enabled = boxes.filter((box) => !box.disabled);
    dbExportAll.checked = enabled.length > 0 && enabled.every((box) => box.checked);
    dbExportAll.indeterminate = enabled.some((box) => box.checked) && !dbExportAll.checked;
  }

  function openDbExport() {
    if (!dbExport || !dbExportList) return;
    if (dbExportStatus) dbExportStatus.textContent = "";
    dbExportList.innerHTML = "";
    const reports = dbReports || [];
    if (!reports.length) {
      dbExportList.innerHTML = `<p class="db-folder-empty">Нет отчётов по текущему фильтру.</p>`;
    }
    for (const folder of reports) {
      const label = document.createElement("label");
      label.className = "db-export-item";
      const dated = Boolean(folder.report_date);
      const count = (folder.jobs || []).length;
      label.innerHTML = `
        <input type="checkbox" data-report="${folder.id}" ${dated ? "checked" : "disabled"} />
        <span>
          <strong>${escapeHtml(folder.title || "Отчёт")}</strong><br />
          <span class="muted">${escapeHtml(folder.site_name || "Без участка")} · ${count} ${jobsCountLabel(count)} · ${formatMoney(folder.amount)} ₽</span>
          ${dated ? "" : `<br /><span class="muted">Нет даты — в Excel не попадает</span>`}
        </span>`;
      dbExportList.appendChild(label);
    }
    syncDbExportAll();
    dbExport.hidden = false;
    if (dbExportYes) dbExportYes.focus();
  }

  function closeDbExport() {
    if (dbExport) dbExport.hidden = true;
  }

  async function downloadSelectedReports() {
    if (!dbExportList) return;
    const ids = [...dbExportList.querySelectorAll("input[data-report]:checked")].map((box) =>
      Number(box.dataset.report)
    );
    if (!ids.length) {
      if (dbExportStatus) dbExportStatus.textContent = "Отметьте хотя бы один отчёт";
      return;
    }
    if (dbExportStatus) dbExportStatus.textContent = "Формирование Excel…";
    if (dbExportYes) dbExportYes.disabled = true;
    try {
      const res = await fetch("/api/db/export-excel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_ids: ids }),
        cache: "no-store",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || res.statusText);
      }
      const blob = await res.blob();
      const filename = filenameFromDisposition(
        res.headers.get("content-disposition"),
        "otchety.xlsx"
      );
      await saveExcelBlob(blob, filename);
      log(`Скачаны отчёты из базы: ${filename}`);
      if (dbStatus) dbStatus.textContent = `Скачан файл ${filename}`;
      closeDbExport();
    } catch (e) {
      if (dbExportStatus) dbExportStatus.textContent = e.message;
    } finally {
      if (dbExportYes) dbExportYes.disabled = false;
    }
  }

  const btnDbDownload = $("btnDbDownload");
  if (btnDbDownload) btnDbDownload.addEventListener("click", openDbExport);
  if (dbExportAll) {
    dbExportAll.addEventListener("change", () => {
      if (!dbExportList) return;
      dbExportList.querySelectorAll("input[data-report]").forEach((box) => {
        if (!box.disabled) box.checked = dbExportAll.checked;
      });
      syncDbExportAll();
    });
  }
  if (dbExportList) {
    dbExportList.addEventListener("change", (event) => {
      if (event.target && event.target.matches("input[data-report]")) syncDbExportAll();
    });
  }
  if (dbExportYes) dbExportYes.addEventListener("click", downloadSelectedReports);
  const dbExportNo = $("dbExportNo");
  if (dbExportNo) dbExportNo.addEventListener("click", closeDbExport);
  if (dbExport) {
    dbExport.addEventListener("click", (event) => {
      if (event.target === dbExport) closeDbExport();
    });
  }
  async function saveDbReport(reportId) {
    const dateEl = document.getElementById("dbEditDate");
    const siteEl = document.getElementById("dbEditSite");
    if (!dateEl || !siteEl) return;
    if (dbStatus) dbStatus.textContent = "Сохранение…";
    try {
      const res = await fetch(`/api/reports/${reportId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report_date: dateEl.value,
          site_id: siteEl.value ? Number(siteEl.value) : null,
          site_set: true,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Не удалось сохранить отчёт");
      dbEditing = null;
      await loadSites();
      await loadDbRows({ keepStatus: true });
      if (dbStatus && !dbStatus.textContent) dbStatus.textContent = data.message || "Отчёт обновлён";
    } catch (e) {
      if (dbStatus) dbStatus.textContent = e.message;
    }
  }

  async function saveDbJob(jobId) {
    const fio = document.getElementById("dbEditFio");
    const task = document.getElementById("dbEditTask");
    const volume = document.getElementById("dbEditVolume");
    const unit = document.getElementById("dbEditUnit");
    const price = document.getElementById("dbEditPrice");
    if (!fio || !task || !volume || !unit || !price) return;
    if (dbStatus) dbStatus.textContent = "Сохранение…";
    try {
      const res = await fetch(`/api/db/jobs/${jobId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          worker_name: fio.value.trim(),
          task_name: task.value.trim(),
          volume: Number(String(volume.value).replace(",", ".")),
          unit: unit.value.trim() || "шт",
          unit_price: Number(String(price.value).replace(",", ".")),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Не удалось сохранить строку");
      dbEditing = null;
      await loadDbRows({ keepStatus: true });
      if (dbStatus && !dbStatus.textContent) dbStatus.textContent = data.message || "Строка обновлена";
    } catch (e) {
      if (dbStatus) dbStatus.textContent = e.message;
    }
  }

  function askDbConfirm(message) {
    const box = document.getElementById("dbConfirm");
    const text = document.getElementById("dbConfirmText");
    const yes = document.getElementById("dbConfirmYes");
    const no = document.getElementById("dbConfirmNo");
    if (!box || !text || !yes || !no) return Promise.resolve(false);
    text.textContent = message;
    box.hidden = false;
    return new Promise((resolve) => {
      const finish = (ok) => {
        box.hidden = true;
        yes.removeEventListener("click", onYes);
        no.removeEventListener("click", onNo);
        box.removeEventListener("click", onBackdrop);
        document.removeEventListener("keydown", onKey);
        resolve(ok);
      };
      const onYes = () => finish(true);
      const onNo = () => finish(false);
      const onBackdrop = (event) => {
        if (event.target === box) finish(false);
      };
      const onKey = (event) => {
        if (event.key === "Escape") finish(false);
      };
      yes.addEventListener("click", onYes);
      no.addEventListener("click", onNo);
      box.addEventListener("click", onBackdrop);
      document.addEventListener("keydown", onKey);
      no.focus();
    });
  }

  async function deleteDbReport(reportId) {
    if (!(await askDbConfirm("Вы точно хотите удалить папку?"))) return;
    if (dbStatus) dbStatus.textContent = "Удаление…";
    try {
      const res = await fetch(`/api/reports/${reportId}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Не удалось удалить отчёт");
      closeDbTab(reportId);
      if (dbEditing && dbEditing.type === "report" && String(dbEditing.id) === String(reportId)) dbEditing = null;
      await loadSites();
      await loadDbRows({ keepStatus: true });
      if (dbStatus && !dbStatus.textContent) dbStatus.textContent = data.message || "Отчёт удалён";
    } catch (e) {
      if (dbStatus) dbStatus.textContent = e.message;
    }
  }

  async function deleteDbJob(jobId) {
    if (!(await askDbConfirm("Вы точно хотите удалить строку?"))) return;
    if (dbStatus) dbStatus.textContent = "Удаление…";
    try {
      const res = await fetch(`/api/db/jobs/${jobId}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Не удалось удалить строку");
      if (dbEditing && dbEditing.type === "job" && String(dbEditing.id) === String(jobId)) dbEditing = null;
      await loadDbRows({ keepStatus: true });
      if (dbStatus && !dbStatus.textContent) dbStatus.textContent = data.message || "Строка удалена";
    } catch (e) {
      if (dbStatus) dbStatus.textContent = e.message;
    }
  }

  if (dbSheet) {
    dbSheet.addEventListener("input", (event) => {
      if (event.target && (event.target.id === "dbEditVolume" || event.target.id === "dbEditPrice")) {
        previewDbAmount();
      }
    });
    dbSheet.addEventListener("click", async (event) => {
      const closeBtn = event.target.closest("[data-db-close]");
      if (closeBtn) {
        event.stopPropagation();
        closeDbTab(closeBtn.dataset.dbClose);
        renderDbBrowser();
        return;
      }
      const tabBtn = event.target.closest("[data-db-tab]");
      if (tabBtn) {
        const raw = tabBtn.dataset.dbTab;
        dbActiveTab = raw === "folders" ? "folders" : Number(raw);
        renderDbBrowser();
        return;
      }
      const actionBtn = event.target.closest("[data-db-action]");
      if (actionBtn) {
        const action = actionBtn.dataset.dbAction;
        if (action === "cancel-db") {
          dbEditing = null;
          renderDbBrowser();
          return;
        }
        if (action === "edit-report") {
          dbEditing = { type: "report", id: Number(actionBtn.dataset.report) };
          dbActiveTab = "folders";
          renderDbBrowser();
          return;
        }
        if (action === "edit-job") {
          dbEditing = { type: "job", id: Number(actionBtn.dataset.job) };
          renderDbBrowser();
          return;
        }
        if (action === "save-report") {
          await saveDbReport(actionBtn.dataset.report);
          return;
        }
        if (action === "save-job") {
          await saveDbJob(actionBtn.dataset.job);
          return;
        }
        if (action === "delete-report") {
          await deleteDbReport(actionBtn.dataset.report);
          return;
        }
        if (action === "delete-job") {
          await deleteDbJob(actionBtn.dataset.job);
          return;
        }
      }
      const btn = event.target.closest(".db-folder-btn");
      if (!btn || !btn.dataset.report) return;
      openDbFolder(btn.dataset.report);
    });
  }
  if (dbSiteSelect) {
    dbSiteSelect.addEventListener("change", () => {
      dbFilter.site = dbSiteSelect.value;
      renderSiteControls();
      loadDbRows();
    });
  }
  $("btnEmployeesSave").addEventListener("click", saveEmployees);
  if (btnModelSave) btnModelSave.addEventListener("click", saveModel);
  if (btnModelRefresh) btnModelRefresh.addEventListener("click", loadModelSettings);

  btnParse.addEventListener("click", () => parseReport({ useAi: true }));
  if (btnParseRules) {
    btnParseRules.addEventListener("click", () => parseReport({ useAi: false }));
  }
  btnCalc.addEventListener("click", recalculate);
  if (btnSaveDb) btnSaveDb.addEventListener("click", saveToDb);
  if (btnApplyPreview) btnApplyPreview.addEventListener("click", applyPreviewAndRecalc);
  btnExcel.addEventListener("click", writeExcel);
  btnCancelPreview.addEventListener("click", cancelPreview);
  btnNewMonth.addEventListener("click", createMonth);
  if (btnRefreshWorkbooks) btnRefreshWorkbooks.addEventListener("click", refreshWorkbooks);
  if (btnActivateMonth) {
    btnActivateMonth.addEventListener("click", () => activateMonth({ syncDate: true }));
  }
  if (btnEditTable) btnEditTable.addEventListener("click", editExistingTable);
  if (btnDeleteWorkbook) btnDeleteWorkbook.addEventListener("click", deleteSelectedWorkbook);
  if (btnDownload) btnDownload.addEventListener("click", downloadActiveExcel);
  if (btnDownloadPeriod) btnDownloadPeriod.addEventListener("click", downloadPeriodExcel);
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
    updateReportWorkbookHint(lastActiveMeta);
  });

  window.addEventListener("beforeunload", (e) => {
    if (priceDirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  window.addEventListener("hashchange", () => showView(viewFromHash(), true));
  showView(viewFromHash());
  refreshWorkbooks();
  setStep(1);
  log("Готово. Загрузите отчёт или вставьте текст.");
})();
