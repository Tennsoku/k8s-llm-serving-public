"use strict";

(() => {
  const MAX_JSON_BYTES = 2 * 1024 * 1024;
  const MANIFEST_SCHEMA = 1;
  const RUN_ANALYSIS_STATUSES = new Set(["draft", "reviewed", "final", "planned", "pending"]);
  const REFERENCE_STATUSES = new Set(["pending", "observed", "unknown", "not_applicable"]);
  const CLAIM_TYPES = new Set(["observed_fact", "interpretation", "hypothesis", "unknown"]);
  const REFERENCE_ORDER = ["c1", "c_eff", "c_pressure", "highest_tested"];
  const REFERENCE_LABELS = {
    c1: "C1 baseline",
    c_eff: "C_eff",
    c_pressure: "C_pressure",
    highest_tested: "Highest tested"
  };
  const STATUS_LABELS = {
    in_progress: "in progress",
    not_applicable: "n/a"
  };
  const CLAIM_LABELS = {
    observed_fact: "Observed fact",
    interpretation: "Interpretation",
    hypothesis: "Hypothesis",
    unknown: "Unknown"
  };

  const state = {
    manifest: null,
    manifestUrl: null,
    repoRootUrl: null,
    viewerUrl: null,
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

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isNonEmptyString(value) {
    return typeof value === "string" && value.trim().length > 0;
  }

  function assert(condition, message) {
    if (!condition) throw new Error(message);
  }

  function statusClass(status) {
    return String(status || "idle").replaceAll("_", "-").replace(/[^a-z0-9-]/g, "");
  }

  function statusLabel(status) {
    return STATUS_LABELS[status] || String(status || "idle").replaceAll("_", " ");
  }

  function setStatus(element, status, label) {
    element.className = "status-pill status-" + statusClass(status);
    element.textContent = label || statusLabel(status);
  }

  function setNotice(element, message) {
    element.textContent = message || "";
    element.hidden = !message;
  }

  function addPageError(message) {
    if (!state.pageErrors.includes(message)) state.pageErrors.push(message);
    setNotice(byId("pageError"), state.pageErrors.join("\n"));
  }

  function renderDiagnostics() {
    const messages = [
      state.queryDiagnostic,
      state.viewerDiagnostic,
      state.analysisDiagnostic
    ].filter(Boolean);
    setNotice(byId("runDiagnostic"), messages.join("\n"));
  }

  function createTextElement(tagName, className, text) {
    const node = document.createElement(tagName);
    if (className) node.className = className;
    node.textContent = text;
    return node;
  }

  function renderStringList(element, items, emptyText) {
    element.replaceChildren();
    const values = Array.isArray(items) ? items : [];
    if (!values.length) {
      element.append(createTextElement("li", "", emptyText || "待补充"));
      return;
    }
    for (const item of values) {
      element.append(createTextElement("li", "", item));
    }
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
      const card = createTextElement(
        "article",
        "claim-card claim-" + claim.type.replaceAll("_", "-"),
        ""
      );
      card.append(
        createTextElement("span", "claim-type", CLAIM_LABELS[claim.type]),
        createTextElement("p", "", claim.text)
      );
      if (claim.evidence.length) {
        card.append(
          createTextElement(
            "span",
            "evidence-ref",
            "Evidence · " + claim.evidence.join(" · ")
          )
        );
      }
      element.append(card);
    }
  }

  function isAllowedProtocol(url) {
    return url.protocol === "http:" || url.protocol === "https:";
  }

  function isWithinRepository(url) {
    const prefix = state.repoRootUrl.pathname.endsWith("/")
      ? state.repoRootUrl.pathname
      : state.repoRootUrl.pathname + "/";
    return url.pathname === state.repoRootUrl.pathname || url.pathname.startsWith(prefix);
  }

  function resolveInternal(path, baseUrl, label) {
    assert(isNonEmptyString(path), label + " 必须是非空路径。");
    let url;
    try {
      url = new URL(path, baseUrl);
    } catch (error) {
      throw new Error(label + " 不是有效 URL：" + error.message);
    }
    assert(isAllowedProtocol(url), label + " 只允许 http/https。");
    assert(!url.username && !url.password, label + " 不允许 URL credentials。");
    assert(url.origin === window.location.origin, label + " 必须与 showcase 同源。");
    assert(isWithinRepository(url), label + " 必须位于本次 Pages repository root 下。");
    return url;
  }

  function resolveAnalysisLink(path, baseUrl, label) {
    assert(isNonEmptyString(path), label + " 必须是非空路径。");
    let url;
    try {
      url = new URL(path, baseUrl);
    } catch (error) {
      throw new Error(label + " 不是有效 URL：" + error.message);
    }
    assert(isAllowedProtocol(url), label + " 只允许 http/https。");
    assert(!url.username && !url.password, label + " 不允许 URL credentials。");
    if (url.origin === window.location.origin) {
      assert(isWithinRepository(url), label + " 必须位于本次 Pages repository root 下。");
    }
    return url;
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      cache: "no-store",
      signal: options.signal
    });
    if (!response.ok) {
      throw new Error("读取 " + new URL(response.url || url).pathname + " 返回 HTTP " + response.status + "。");
    }

    const contentLength = Number(response.headers.get("content-length"));
    if (Number.isFinite(contentLength) && contentLength > MAX_JSON_BYTES) {
      throw new Error("JSON 超过 " + (MAX_JSON_BYTES / 1024 / 1024) + " MiB 展示层限制。");
    }

    const text = await response.text();
    if (new TextEncoder().encode(text).byteLength > MAX_JSON_BYTES) {
      throw new Error("JSON 超过 " + (MAX_JSON_BYTES / 1024 / 1024) + " MiB 展示层限制。");
    }

    let data;
    try {
      data = JSON.parse(text);
    } catch (error) {
      throw new Error("JSON 解析失败：" + error.message);
    }
    return {
      data,
      url: new URL(response.url || url)
    };
  }

  function validateLink(link, index, baseUrl) {
    assert(isObject(link), "links[" + index + "] 必须是 object。");
    assert(isNonEmptyString(link.label), "links[" + index + "].label 缺失。");
    assert(isNonEmptyString(link.href), "links[" + index + "].href 缺失。");
    assert(link.kind !== "local_evidence", "links[" + index + "] 不能引用 local evidence。");
    assert(link.visibility == null || link.visibility === "public", "links[" + index + "].visibility 只允许 public。");
    return {
      id: isNonEmptyString(link.id) ? link.id : "link-" + index,
      label: link.label,
      url: resolveAnalysisLink(link.href, baseUrl, "links[" + index + "].href")
    };
  }

  function validateClaims(claims, label) {
    assert(Array.isArray(claims), label + " 必须是 array。");
    return claims.map((claim, index) => {
      assert(isObject(claim), label + "[" + index + "] 必须是 object。");
      assert(CLAIM_TYPES.has(claim.type), label + "[" + index + "].type 不受支持。");
      assert(isNonEmptyString(claim.text), label + "[" + index + "].text 缺失。");
      const evidence = claim.evidence == null ? [] : claim.evidence;
      assert(Array.isArray(evidence) && evidence.every(isNonEmptyString), label + "[" + index + "].evidence 必须是 string array。");
      if (["observed_fact", "unknown"].includes(claim.type)) assert(evidence.length > 0, label + "[" + index + "] 必须引用 evidence。");
      return {
        type: claim.type,
        text: claim.text,
        evidence
      };
    });
  }

  function validateStringArray(value, label) {
    assert(Array.isArray(value) && value.every(isNonEmptyString), label + " 必须是 string array。");
    return value;
  }

  function validateManifest(data, manifestUrl) {
    assert(isObject(data), "index.json 顶层必须是 object。");
    assert(data.schema_version === MANIFEST_SCHEMA, "不支持 index schema_version " + String(data.schema_version) + "。");
    assert(isNonEmptyString(data.viewer_path), "viewer_path 缺失。");
    assert(isObject(data.milestone), "milestone metadata 缺失。");
    assert(isNonEmptyString(data.milestone.id), "milestone.id 缺失。");
    assert(isNonEmptyString(data.milestone.title), "milestone.title 缺失。");
    assert(isNonEmptyString(data.milestone.status), "milestone.status 缺失。");
    assert(isNonEmptyString(data.milestone.analysis_path), "milestone.analysis_path 缺失。");
    assert(Array.isArray(data.entries) && data.entries.length > 0, "entries 必须包含至少一个条目。");

    const entries = [];
    const ids = new Set();
    for (const [index, raw] of data.entries.entries()) {
      const prefix = "entries[" + index + "]";
      assert(isObject(raw), prefix + " 必须是 object。");
      for (const key of ["id", "label", "stage", "source_status", "expected_run_id", "summary_path", "analysis_path"]) {
        assert(isNonEmptyString(raw[key]), prefix + "." + key + " 缺失。");
      }
      assert(raw.source_status === "published", prefix + ".source_status 必须是 published。");
      assert(/^[a-z0-9][a-z0-9.-]*$/.test(raw.id), prefix + ".id 必须是稳定的 URL-safe story id。");
      assert(!ids.has(raw.id), "重复 entry id：" + raw.id + "。");
      ids.add(raw.id);
      entries.push({
        id: raw.id,
        label: raw.label,
        stage: raw.stage,
        source_status: raw.source_status,
        expected_run_id: raw.expected_run_id,
        summaryUrl: resolveInternal(raw.summary_path, manifestUrl, prefix + ".summary_path"),
        analysisUrl: resolveInternal(raw.analysis_path, manifestUrl, prefix + ".analysis_path")
      });
    }

    assert(isNonEmptyString(data.default_entry), "default_entry 缺失。");
    assert(ids.has(data.default_entry), "default_entry 未出现在 entries 中。");

    return {
      schema_version: data.schema_version,
      viewerUrl: resolveInternal(data.viewer_path, manifestUrl, "viewer_path"),
      milestone: {
        id: data.milestone.id,
        title: data.milestone.title,
        status: data.milestone.status,
        analysisUrl: resolveInternal(data.milestone.analysis_path, manifestUrl, "milestone.analysis_path")
      },
      default_entry: data.default_entry,
      entries
    };
  }

  function validateMilestoneAnalysis(data, analysisUrl) {
    assert(isObject(data), "milestone analysis 顶层必须是 object。");
    assert(data.schema_version === 1, "不支持 milestone analysis schema。");
    assert(data.kind === "milestone_analysis", "milestone analysis kind 不匹配。");
    assert(data.milestone_id === state.manifest.milestone.id, "milestone_id 与 index.json 不匹配。");
    assert(isNonEmptyString(data.status), "milestone analysis status 缺失。");
    assert(isNonEmptyString(data.takeaway), "milestone takeaway 缺失。");
    assert(isObject(data.handoff), "milestone handoff 缺失。");
    return {
      status: data.status,
      takeaway: data.takeaway,
      scope: validateStringArray(data.scope, "scope"),
      claims: validateClaims(data.claims, "claims"),
      limitations: validateStringArray(data.limitations, "limitations"),
      handoff: {
        m2: validateStringArray(data.handoff.m2, "handoff.m2"),
        m3: validateStringArray(data.handoff.m3, "handoff.m3")
      },
      links: (data.links || []).map((link, index) => validateLink(link, index, analysisUrl))
    };
  }

  function validateReference(raw, key) {
    assert(isObject(raw), "operating_references." + key + " 必须是 object。");
    assert(REFERENCE_STATUSES.has(raw.status), "operating_references." + key + ".status 不受支持。");
    const concurrency = raw.concurrency;
    if (raw.status === "observed") {
      assert(Number.isInteger(concurrency) && concurrency > 0, "observed reference " + key + " 必须包含正整数 concurrency。");
    } else {
      assert(concurrency === null, raw.status + " reference " + key + " 的 concurrency 必须为 null。");
    }
    const evidence = raw.evidence == null
      ? []
      : validateStringArray(raw.evidence, "operating_references." + key + ".evidence");
    if (raw.status === "unknown") {
      assert(isNonEmptyString(raw.rationale), "unknown reference " + key + " 必须解释 tested-range evidence。");
      assert(evidence.length > 0, "unknown reference " + key + " 必须引用 tested-range evidence。");
    }
    return {
      status: raw.status,
      concurrency,
      rationale: isNonEmptyString(raw.rationale) ? raw.rationale : null,
      evidence
    };
  }

  function validateRunAnalysis(data, entry, analysisUrl) {
    assert(isObject(data), "run analysis 顶层必须是 object。");
    assert(data.schema_version === 1, "不支持 run analysis schema。");
    assert(data.kind === "run_analysis", "run analysis kind 不匹配。");
    assert(data.showcase_id === entry.id, "analysis showcase_id 与当前 entry id 不匹配。");
    assert(RUN_ANALYSIS_STATUSES.has(data.status), "analysis status 不受支持。");
    assert(data.takeaway === null || isNonEmptyString(data.takeaway), "takeaway 必须是 string 或 null。");
    assert(isObject(data.operating_references), "operating_references 缺失。");

    const references = {};
    for (const key of REFERENCE_ORDER) {
      references[key] = validateReference(data.operating_references[key], key);
    }

    return {
      status: data.status,
      takeaway: data.takeaway,
      references,
      claims: validateClaims(data.claims, "claims"),
      limitations: data.limitations == null
        ? []
        : validateStringArray(data.limitations, "limitations"),
      links: (data.links || []).map((link, index) => validateLink(link, index, analysisUrl))
    };
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
    for (const key of ["m2", "m3"]) {
      const card = createTextElement("article", "handoff", "");
      card.append(createTextElement("strong", "", key.toUpperCase()));
      const list = document.createElement("ul");
      for (const text of handoff[key]) {
        list.append(createTextElement("li", "", text));
      }
      card.append(list);
      container.append(card);
    }
  }

  function renderMilestoneMeta() {
    const status = byId("milestoneStatus");
    setStatus(status, state.manifest.milestone.status);
    const chips = [
      state.manifest.entries.length + " selected entries",
      "schema v" + state.manifest.schema_version,
      "static same-origin JSON"
    ];
    const container = byId("milestoneMeta");
    container.replaceChildren(status, ...chips.map(text => createTextElement("span", "chip", text)));
  }

  function renderMilestoneAnalysis(analysis) {
    setStatus(byId("overviewStatus"), analysis.status);
    byId("milestoneTakeaway").textContent = analysis.takeaway;
    renderStringList(byId("milestoneScope"), analysis.scope);
    renderClaims(byId("milestoneClaims"), analysis.claims);
    renderStringList(byId("milestoneLimitations"), analysis.limitations);
    renderHandoff(analysis.handoff);
    renderLinks(byId("milestoneLinks"), analysis.links);
  }

  async function loadMilestoneAnalysis() {
    try {
      const result = await fetchJson(state.manifest.milestone.analysisUrl);
      const analysis = validateMilestoneAnalysis(result.data, result.url);
      renderMilestoneAnalysis(analysis);
    } catch (error) {
      setStatus(byId("overviewStatus"), "error");
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
      if (reference.status === "observed") {
        value.append(document.createTextNode("C" + reference.concurrency));
      } else {
        value.textContent = statusLabel(reference.status);
      }
      card.append(value);
      const badge = createTextElement("span", "", "");
      setStatus(badge, reference.status);
      card.append(badge);
      if (reference.rationale) {
        card.append(createTextElement("p", "", reference.rationale));
      }
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
    setStatus(byId("sourceStatus"), entry.source_status);
  }

  function renderRunAnalysis(analysis, entry) {
    setStatus(byId("analysisStatus"), analysis.status);
    byId("runTakeaway").textContent = analysis.takeaway === null
      ? "分析进行中；尚未形成 takeaway。"
      : analysis.takeaway;
    renderReferenceGrid(analysis.references);
    renderClaims(byId("runClaims"), analysis.claims);
    renderStringList(byId("runLimitations"), analysis.limitations);
    renderLinks(byId("runLinks"), [
      {
        label: "Published summary JSON",
        url: entry.summaryUrl
      },
      ...analysis.links
    ]);
    byId("runAnalysis").setAttribute("aria-busy", "false");

    const pendingReferences = REFERENCE_ORDER.filter(key => analysis.references[key].status === "pending");
    if (analysis.status === "final" && pendingReferences.length) {
      state.analysisDiagnostic = "Analysis 标记为 final，但仍有 pending reference：" + pendingReferences.join(", ") + "。";
    } else {
      state.analysisDiagnostic = "";
    }
    renderDiagnostics();
  }

  async function loadRunAnalysis(entry, epoch, signal) {
    try {
      const result = await fetchJson(entry.analysisUrl, {signal});
      if (epoch !== state.selectionEpoch) return;
      const analysis = validateRunAnalysis(result.data, entry, result.url);
      if (epoch !== state.selectionEpoch) return;
      renderRunAnalysis(analysis, entry);
    } catch (error) {
      if (error.name === "AbortError" || epoch !== state.selectionEpoch) return;
      setStatus(byId("analysisStatus"), "error");
      byId("runTakeaway").textContent = "人工 analysis 暂时不可用；下方 summary viewer 仍可独立检查。";
      byId("runAnalysis").setAttribute("aria-busy", "false");
      setNotice(byId("analysisError"), "Analysis 加载失败：" + error.message);
    }
  }

  function setViewerStatus(status, label) {
    setStatus(byId("viewerStatus"), status, label);
  }

  function updateHistory(id, mode) {
    if (mode === "none") return;
    const url = new URL(window.location.href);
    url.searchParams.set("run", id);
    if (mode === "push") {
      window.history.pushState({run: id}, "", url);
    } else {
      window.history.replaceState({run: id}, "", url);
    }
  }

  function navigateViewer(entry, epoch) {
    const token = String(epoch);
    state.activeViewerToken = token;
    clearTimeout(state.viewerTimeout);
    state.viewerDiagnostic = "";
    renderDiagnostics();

    const embeddedUrl = new URL(state.viewerUrl);
    embeddedUrl.searchParams.set("mode", "embedded");
    embeddedUrl.searchParams.set("src", entry.summaryUrl.href);
    embeddedUrl.searchParams.set("host_token", token);

    const standaloneUrl = new URL(state.viewerUrl);
    standaloneUrl.searchParams.set("src", entry.summaryUrl.href);

    const openLink = byId("openViewerLink");
    openLink.href = standaloneUrl.href;
    openLink.setAttribute("aria-disabled", "false");

    setViewerStatus("loading");
    byId("viewerFrame").src = embeddedUrl.href;
    state.viewerTimeout = window.setTimeout(() => {
      if (token !== state.activeViewerToken) return;
      setViewerStatus("error", "no response");
      state.viewerDiagnostic = "Summary viewer 在 20 秒内没有返回 ready/error；可独立打开检查具体响应。";
      renderDiagnostics();
    }, 20000);
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
    if (requested && state.entriesById.has(requested)) {
      return {id: requested, mode: "replace"};
    }
    if (requested) {
      state.queryDiagnostic = "URL 中的 run=" + requested + " 不在 selected index 中；已回退默认条目。";
    }
    return {id: state.manifest.default_entry, mode: "replace"};
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
    if (
      event.origin !== window.location.origin ||
      event.source !== frame.contentWindow ||
      !isObject(data) ||
      data.source !== "benchmark-summary-viewer" ||
      data.version !== 1 ||
      data.hostToken !== state.activeViewerToken
    ) {
      return;
    }

    clearTimeout(state.viewerTimeout);
    if (data.type === "loaded") {
      setViewerStatus("ready");
      const entry = state.entriesById.get(state.selectedId);
      const observedRunId = isObject(data.detail) ? data.detail.runId : null;
      if (entry && observedRunId !== entry.expected_run_id) {
        state.viewerDiagnostic = "Summary run_id mismatch：index 预期 " + entry.expected_run_id + "，实际 " + String(observedRunId) + "。该差异仅作诊断，不阻断展示。";
      } else {
        state.viewerDiagnostic = "";
      }
      renderDiagnostics();
      return;
    }

    if (data.type === "error") {
      setViewerStatus("error");
      const message = isObject(data.detail) && isNonEmptyString(data.detail.message)
        ? data.detail.message
        : "unknown viewer error";
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
    state.queryDiagnostic = requested
      ? "历史 URL 中的 run=" + requested + " 不在 selected index 中；已回退默认条目。"
      : "";
    selectEntry(state.manifest.default_entry, "replace");
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

    const requestedManifestUrl = new URL("index.json", window.location.href);
    const result = await fetchJson(requestedManifestUrl);
    state.manifestUrl = result.url;
    state.repoRootUrl = new URL("../../", state.manifestUrl);
    state.manifest = validateManifest(result.data, state.manifestUrl);
    state.viewerUrl = state.manifest.viewerUrl;
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
})();
