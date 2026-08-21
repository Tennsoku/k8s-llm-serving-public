"use strict";

import {CLAIM_LABELS, REFERENCE_LABELS, REFERENCE_ORDER, STATUS_LABELS, createRunModel, isNonEmptyString, isObject} from "./run-model.js";

export function startRunApp({entryContract}) {
  const model = createRunModel(entryContract);
  const state = {
    manifest: null,
    entriesById: new Map(),
    selectedId: null,
    selectionEpoch: 0,
    analysisController: null,
    activeViewerToken: null,
    viewerTimeout: null,
    queryDiagnostic: "",
    viewerDiagnostic: "",
    analysisDiagnostic: "",
    pageErrors: []
  };
  const byId = id => document.getElementById(id);
  const viewerFrameShell = () => document.querySelector(".viewer-frame-shell");
  const viewerNote = () => document.querySelector(".viewer-note");

  function statusClass(status) { return String(status || "idle").replaceAll("_", "-").replace(/[^a-z0-9-]/g, ""); }

  function statusLabel(status) { return STATUS_LABELS[status] || String(status || "idle").replaceAll("_", " "); }

  function setStatus(element, status, label) {
    element.className = "status-pill status-" + statusClass(status);
    element.textContent = label || statusLabel(status);
  }

  function setNotice(element, message) {
    element.textContent = message || ""; element.hidden = !message;
  }

  function addPageError(message) {
    if (!state.pageErrors.includes(message)) state.pageErrors.push(message);
    setNotice(byId("pageError"), state.pageErrors.join("\n"));
  }

  function renderDiagnostics() {
    setNotice(byId("runDiagnostic"), [
      state.queryDiagnostic,
      state.viewerDiagnostic,
      state.analysisDiagnostic
    ].filter(Boolean).join("\n"));
  }

  function createTextElement(tagName, className, text) {
    const node = document.createElement(tagName);
    if (className) node.className = className; node.textContent = text;
    return node;
  }

  function renderStringList(element, items, emptyText) {
    element.replaceChildren();
    if (!items.length) {
      element.append(createTextElement("li", "", emptyText || "待补充"));
      return;
    }
    for (const item of items) element.append(createTextElement("li", "", item));
  }

  function renderClaims(element, claims) {
    element.replaceChildren();
    if (!claims.length) {
      const empty = createTextElement("article", "claim-card", "");
      empty.append(
        createTextElement("span", "claim-type", "Pending"),
        createTextElement("p", "", "尚未形成可发布 claim。")
      );
      element.append(empty);
      return;
    }
    for (const claim of claims) {
      const card = createTextElement("article", "claim-card claim-" + claim.type.replaceAll("_", "-"), "");
      card.append(
        createTextElement("span", "claim-type", CLAIM_LABELS[claim.type]),
        createTextElement("p", "", claim.text)
      );
      if (claim.evidence.length) {
        card.append(createTextElement("span", "evidence-ref", "Evidence · " + claim.evidence.join(" · ")));
      }
      element.append(card);
    }
  }

  function renderLinks(element, links) {
    element.replaceChildren();
    for (const link of links) {
      const anchor = document.createElement("a");
      anchor.className = "evidence-link";
      anchor.href = link.url.href;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      anchor.textContent = link.label + " ↗";
      anchor.setAttribute("aria-label", link.label + "（在新标签页打开）");
      element.append(anchor);
    }
  }

  function renderHandoff(handoff) {
    const container = byId("milestoneHandoff");
    container.replaceChildren();
    for (const item of handoff) {
      const card = createTextElement("article", "handoff", "");
      card.append(createTextElement("strong", "", item.id.toUpperCase()));
      const list = document.createElement("ul");
      for (const text of item.values) list.append(createTextElement("li", "", text));
      card.append(list);
      container.append(card);
    }
  }

  function renderMilestoneMeta() {
    const status = byId("milestoneStatus");
    setStatus(status, "loading");
    const chips = [
      state.manifest.entries.length + " selected entries",
      "schema v" + state.manifest.schemaVersion,
      "static same-origin JSON"
    ];
    byId("milestoneMeta").replaceChildren(status, ...chips.map(text => createTextElement("span", "chip", text)));
  }

  function renderMilestoneAnalysis(analysis) {
    setStatus(byId("overviewStatus"), analysis.status);
    setStatus(byId("milestoneStatus"), analysis.status);
    byId("milestoneTakeaway").textContent = analysis.takeaway;
    renderStringList(byId("milestoneScope"), analysis.scope);
    renderClaims(byId("milestoneClaims"), analysis.claims);
    renderStringList(byId("milestoneLimitations"), analysis.limitations);
    renderHandoff(analysis.handoff);
    renderLinks(byId("milestoneLinks"), analysis.links);
  }

  async function loadMilestoneAnalysis() {
    try {
      const result = await model.fetchJson(state.manifest.milestone.analysisUrl);
      renderMilestoneAnalysis(model.validateMilestoneAnalysis(
        result.data,
        result.url,
        state.manifest.milestone.id
      ));
    } catch (error) {
      setStatus(byId("overviewStatus"), "error");
      setStatus(byId("milestoneStatus"), "error");
      byId("milestoneTakeaway").textContent = "Milestone analysis 暂时不可用；精选 run 与 summary viewer 仍可独立使用。";
      addPageError("Milestone analysis 加载失败：" + error.message);
    }
  }

  function renderReferenceGrid(references) {
    const container = byId("referenceGrid");
    container.replaceChildren();
    for (const key of REFERENCE_ORDER) {
      const reference = references[key];
      const card = createTextElement("article", "reference-card", "");
      card.append(createTextElement("h5", "", REFERENCE_LABELS[key]));
      const value = createTextElement("div", "reference-value", "");
      value.textContent = reference.status === "observed" ? "C" + reference.concurrency : statusLabel(reference.status);
      card.append(value);
      const badge = createTextElement("span", "", "");
      setStatus(badge, reference.status);
      card.append(badge);
      if (reference.rationale) card.append(createTextElement("p", "", reference.rationale));
      if (reference.evidence.length) {
        card.append(createTextElement("span", "evidence-ref", "Evidence · " + reference.evidence.join(" · ")));
      }
      container.append(card);
    }
  }

  function emptyRunAnalysis() {
    byId("runAnalysis").setAttribute("aria-busy", "true");
    setStatus(byId("analysisStatus"), "loading");
    byId("runTakeaway").textContent = "正在加载人工 analysis…";
    byId("referenceGrid").replaceChildren();
    byId("runClaims").replaceChildren();
    byId("runLimitations").replaceChildren();
    byId("runLinks").replaceChildren();
    setNotice(byId("analysisError"), "");
  }

  function renderEntryHeader(entry) {
    byId("runStage").textContent = entry.stage;
    byId("runTitle").textContent = entry.label;
    byId("viewerFrame").title = entry.label + " benchmark summary viewer";
    setStatus(byId("sourceStatus"), entry.sourceStatus);
  }

  function evidenceLinks(entry) {
    if (entry.evidence.kind === "single") {
      return [{label: "Published summary JSON", url: entry.evidence.summaryUrl}];
    }
    return entry.evidence.items.map(item => ({
      label: "Published summary · " + item.label,
      url: item.summaryUrl
    }));
  }

  function renderRunAnalysis(analysis, entry) {
    setStatus(byId("analysisStatus"), analysis.status);
    byId("runTakeaway").textContent = analysis.takeaway === null ? "分析进行中；尚未形成 takeaway。" : analysis.takeaway;
    renderReferenceGrid(analysis.references);
    renderClaims(byId("runClaims"), analysis.claims);
    renderStringList(byId("runLimitations"), analysis.limitations);
    renderLinks(byId("runLinks"), [...evidenceLinks(entry), ...analysis.links]);
    byId("runAnalysis").setAttribute("aria-busy", "false");
    const pending = REFERENCE_ORDER.filter(key => analysis.references[key].status === "pending");
    state.analysisDiagnostic = analysis.status === "final" && pending.length
      ? "Analysis 标记为 final，但仍有 pending reference：" + pending.join(", ") + "。"
      : "";
    renderDiagnostics();
  }

  async function loadRunAnalysis(entry, epoch, signal) {
    try {
      const result = await model.fetchJson(entry.analysisUrl, {signal});
      if (epoch !== state.selectionEpoch) return;
      const analysis = model.validateRunAnalysis(result.data, entry, result.url);
      if (epoch === state.selectionEpoch) renderRunAnalysis(analysis, entry);
    } catch (error) {
      if (error.name === "AbortError" || epoch !== state.selectionEpoch) return;
      setStatus(byId("analysisStatus"), "error");
      byId("runTakeaway").textContent = "人工 analysis 暂时不可用；下方 summary viewer 仍可独立检查。";
      byId("runAnalysis").setAttribute("aria-busy", "false");
      setNotice(byId("analysisError"), "Analysis 加载失败：" + error.message);
    }
  }

  function ensureSummarySetPanel() {
    if (byId("summarySetPanel")) return byId("summarySetPanel");
    const panel = createTextElement("div", "summary-set-panel", "");
    panel.id = "summarySetPanel";
    const scroll = createTextElement("div", "summary-set-scroll", "");
    const table = document.createElement("table");
    table.className = "summary-set-table";
    table.setAttribute("aria-describedby", "summarySetCaption");
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    for (const label of ["Run point", "Actual input", "TTFT P95", "KV usage", "Process memory", "Outcome"]) {
      const cell = createTextElement("th", "", label);
      cell.scope = "col";
      headRow.append(cell);
    }
    head.append(headRow);
    const body = document.createElement("tbody");
    body.id = "summarySetBody";
    table.append(head, body);
    scroll.append(table);
    const caption = createTextElement("p", "", "C1 aggregate；TTFT、KV usage 与 NVML process memory 使用完整 repetition 的 median。");
    caption.id = "summarySetCaption";
    panel.append(scroll, caption);
    viewerFrameShell().before(panel);
    return panel;
  }

  function formatSetValue(value, digits, unit) { return Number.isFinite(value) ? new Intl.NumberFormat("zh-CN", {maximumFractionDigits: digits}).format(value) + unit : "n/a"; }

  function projectSummarySetItem(item, summary) {
    if (!isObject(summary)) throw new Error(item.label + " summary 顶层必须是 object。");
    const complete = (Array.isArray(summary.cases) ? summary.cases : []).filter(value =>
      value.concurrency === 1 && value.measurement_complete === true &&
      (!Array.isArray(value.invalid_reasons) || value.invalid_reasons.length === 0)
    );
    const aggregates = (Array.isArray(summary.concurrency_summary) ? summary.concurrency_summary : [])
      .filter(value => value.concurrency === 1);
    if (aggregates.length > 1) throw new Error(item.label + " 存在重复 C1 aggregate。");
    const inputs = complete.map(value => value.client?.input_tokens);
    const successes = complete.map(value => value.client?.successful_requests);
    const totalsUsable = complete.length > 0 && inputs.every(Number.isFinite) && successes.every(Number.isFinite);
    const successful = totalsUsable ? successes.reduce((total, value) => total + value, 0) : 0;
    const aggregate = complete.length ? aggregates[0] : null;
    return {
      label: item.label,
      expectedRunId: item.expectedRunId,
      actualInput: successful > 0 ? inputs.reduce((total, value) => total + value, 0) / successful : null,
      ttft: aggregate?.ttft_p95_seconds_median,
      kv: aggregate?.max_kv_cache_usage_ratio_median,
      memory: aggregate?.max_container_nvml_process_gpu_memory_used_bytes_median,
      outcome: isNonEmptyString(summary.context?.run?.outcome) ? summary.context.run.outcome : null,
      mismatch: summary.run_id !== item.expectedRunId
    };
  }

  function renderSummarySet(points) {
    const body = byId("summarySetBody");
    body.replaceChildren();
    for (const point of points) {
      const row = document.createElement("tr");
      const label = createTextElement("td", "summary-set-label", "");
      label.append(createTextElement("strong", "", point.label), createTextElement("small", "", point.expectedRunId));
      const outcome = createTextElement("span", "", "");
      if (point.outcome === null) {
        outcome.className = "status-pill";
        outcome.textContent = "n/a";
      } else setStatus(outcome, point.outcome);
      const outcomeCell = document.createElement("td");
      outcomeCell.append(outcome);
      row.append(
        label,
        createTextElement("td", "", formatSetValue(point.actualInput, 0, " tokens")),
        createTextElement("td", "", formatSetValue(Number.isFinite(point.ttft) ? point.ttft * 1000 : null, 1, " ms")),
        createTextElement("td", "", formatSetValue(Number.isFinite(point.kv) ? point.kv * 100 : null, 2, "%")),
        createTextElement("td", "", formatSetValue(Number.isFinite(point.memory) ? point.memory / (1024 ** 3) : null, 2, " GiB")),
        outcomeCell
      );
      body.append(row);
    }
  }

  async function loadSummarySet(entry, epoch, signal) {
    try {
      const points = await Promise.all(entry.evidence.items.map(async item => {
        const result = await model.fetchJson(item.summaryUrl, {signal});
        return projectSummarySetItem(item, result.data);
      }));
      if (epoch !== state.selectionEpoch) return;
      renderSummarySet(points);
      const mismatches = points.filter(point => point.mismatch).map(point => point.label);
      state.viewerDiagnostic = mismatches.length ? "Run set 的 run_id 与 manifest 不匹配：" + mismatches.join("、") + "。" : "";
      setStatus(byId("viewerStatus"), "ready");
      renderDiagnostics();
    } catch (error) {
      if (error.name === "AbortError" || epoch !== state.selectionEpoch) return;
      byId("summarySetBody").replaceChildren();
      setStatus(byId("viewerStatus"), "error");
      state.viewerDiagnostic = "Run set 加载失败：" + error.message;
      renderDiagnostics();
    }
  }

  function navigateViewer(entry, epoch) {
    clearTimeout(state.viewerTimeout);
    state.viewerDiagnostic = "";
    const isSet = entry.evidence.kind === "summary_set";
    const setPanel = isSet ? ensureSummarySetPanel() : byId("summarySetPanel");
    if (setPanel) setPanel.hidden = !isSet;
    viewerFrameShell().hidden = isSet;
    byId("openViewerLink").hidden = isSet;
    byId("viewerTitle").textContent = isSet ? "Long-context run set" : "Summary viewer";
    viewerNote().textContent = isSet
      ? "固定展示每份 C1 summary 的观测值；表格不计算跨 run delta、趋势线或 knee。"
      : "这里展示单个 run 内的可重算曲线与证据健康。Showcase 模式隐藏通用 knee heuristic，人工 operating-reference 结论以上方 analysis 为准。";
    setStatus(byId("viewerStatus"), "loading");
    renderDiagnostics();
    if (isSet) {
      state.activeViewerToken = null;
      byId("viewerFrame").src = "about:blank";
      byId("summarySetBody").replaceChildren();
      byId("openViewerLink").removeAttribute("href");
      byId("openViewerLink").setAttribute("aria-disabled", "true");
      loadSummarySet(entry, epoch, state.analysisController.signal);
      return;
    }
    const token = String(epoch);
    state.activeViewerToken = token;
    const embeddedUrl = new URL(state.manifest.viewerUrl);
    embeddedUrl.searchParams.set("mode", "embedded");
    embeddedUrl.searchParams.set("src", entry.evidence.summaryUrl.href);
    embeddedUrl.searchParams.set("host_token", token);
    const standaloneUrl = new URL(state.manifest.viewerUrl);
    standaloneUrl.searchParams.set("src", entry.evidence.summaryUrl.href);
    byId("openViewerLink").href = standaloneUrl.href;
    byId("openViewerLink").setAttribute("aria-disabled", "false");
    byId("viewerFrame").src = embeddedUrl.href;
    state.viewerTimeout = window.setTimeout(() => {
      if (token !== state.activeViewerToken) return;
      setStatus(byId("viewerStatus"), "error", "no response");
      state.viewerDiagnostic = "Summary viewer 在 20 秒内没有返回 ready/error；可独立打开检查具体响应。";
      renderDiagnostics();
    }, 20000);
  }

  function updateHistory(id, mode) {
    if (mode === "none") return;
    const url = new URL(window.location.href);
    url.searchParams.set("run", id);
    window.history[mode === "push" ? "pushState" : "replaceState"]({run: id}, "", url);
  }

  function selectEntry(id, historyMode) {
    const entry = state.entriesById.get(id);
    if (!entry) return;
    state.selectedId = id;
    const epoch = ++state.selectionEpoch;
    state.analysisController?.abort();
    state.analysisController = new AbortController();
    clearTimeout(state.viewerTimeout);
    state.viewerDiagnostic = "";
    state.analysisDiagnostic = "";
    renderDiagnostics();
    byId("runSelect").value = id;
    renderEntryHeader(entry);
    emptyRunAnalysis();
    loadRunAnalysis(entry, epoch, state.analysisController.signal);
    navigateViewer(entry, epoch);
    updateHistory(id, historyMode);
  }

  function chooseInitialEntry() {
    const requested = new URL(window.location.href).searchParams.get("run");
    if (requested && state.entriesById.has(requested)) return {id: requested, mode: "replace"};
    if (requested) state.queryDiagnostic = "URL 中的 run=" + requested + " 不在 selected index 中；已回退默认条目。";
    return {id: state.manifest.defaultEntry, mode: "replace"};
  }

  function populateRunSelect() {
    const select = byId("runSelect");
    select.replaceChildren();
    for (const entry of state.manifest.entries) {
      const option = document.createElement("option");
      option.value = entry.id;
      option.textContent = entry.label;
      select.append(option);
    }
    select.disabled = false;
  }

  function handleViewerMessage(event) {
    const frame = byId("viewerFrame");
    const data = event.data;
    if (event.origin !== window.location.origin || event.source !== frame.contentWindow ||
        !isObject(data) || data.source !== "benchmark-summary-viewer" || data.version !== 1 ||
        data.hostToken !== state.activeViewerToken) return;
    clearTimeout(state.viewerTimeout);
    if (data.type === "loaded") {
      setStatus(byId("viewerStatus"), "ready");
      const entry = state.entriesById.get(state.selectedId);
      const observed = isObject(data.detail) ? data.detail.runId : null;
      const expected = entry?.evidence.kind === "single" ? entry.evidence.expectedRunId : null;
      state.viewerDiagnostic = entry && observed !== expected
        ? "Summary run_id mismatch：index 预期 " + expected + "，实际 " + String(observed) + "。该差异仅作诊断，不阻断展示。"
        : "";
      renderDiagnostics();
    } else if (data.type === "error") {
      setStatus(byId("viewerStatus"), "error");
      const message = isObject(data.detail) && isNonEmptyString(data.detail.message) ? data.detail.message : "unknown viewer error";
      state.viewerDiagnostic = "Summary viewer 加载失败：" + message;
      renderDiagnostics();
    }
  }

  function handlePopState() {
    if (!state.manifest) return;
    const requested = new URL(window.location.href).searchParams.get("run");
    if (requested && state.entriesById.has(requested)) {
      state.queryDiagnostic = "";
      selectEntry(requested, "none");
      return;
    }
    state.queryDiagnostic = requested ? "历史 URL 中的 run=" + requested + " 不在 selected index 中；已回退默认条目。" : "";
    selectEntry(state.manifest.defaultEntry, "replace");
  }

  async function bootstrap() {
    byId("viewerStatus").setAttribute("role", "status");
    byId("viewerStatus").setAttribute("aria-live", "polite");
    byId("analysisStatus").setAttribute("role", "status");
    byId("analysisStatus").setAttribute("aria-live", "polite");
    byId("openViewerLink").removeAttribute("href");
    byId("openViewerLink").setAttribute("aria-disabled", "true");
    if (window.location.protocol === "file:") {
      throw new Error("Showcase 需要通过 127.0.0.1 的 repo-root HTTP server 打开，不能使用 file://。");
    }
    const result = await model.fetchJson(new URL("index.json", window.location.href));
    model.setRepositoryRoot(new URL("../../", result.url));
    state.manifest = model.validateManifest(result.data, result.url);
    state.entriesById = new Map(state.manifest.entries.map(entry => [entry.id, entry]));
    renderMilestoneMeta();
    populateRunSelect();
    loadMilestoneAnalysis();
    const initial = chooseInitialEntry();
    renderDiagnostics();
    selectEntry(initial.id, initial.mode);
  }

  byId("runSelect").addEventListener("change", event => {
    state.queryDiagnostic = "";
    selectEntry(event.target.value, "push");
  });
  window.addEventListener("message", handleViewerMessage);
  window.addEventListener("popstate", handlePopState);
  bootstrap().catch(error => {
    setStatus(byId("milestoneStatus"), "error");
    setStatus(byId("overviewStatus"), "error");
    setStatus(byId("viewerStatus"), "error");
    byId("milestoneTakeaway").textContent = "Milestone analysis 不可用；请检查 showcase manifest 与 analysis 文件。";
    byId("runSelect").disabled = true;
    byId("runAnalysis").setAttribute("aria-busy", "false");
    byId("runStage").textContent = "index unavailable";
    byId("runTitle").textContent = "无法加载 selected run index";
    setStatus(byId("analysisStatus"), "error");
    byId("runTakeaway").textContent = "Showcase manifest 初始化失败；没有加载任何 analysis 或 summary。";
    addPageError("Showcase 初始化失败：" + error.message);
  });
}
