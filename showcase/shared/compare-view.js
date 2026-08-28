"use strict";

import {
  formatNumber, formatPercent, formatRelative, getPointer,
  isFiniteNumber, isNonEmptyString, valueLabel
} from "./compare-data.js";
import {renderReviewError, renderReviewFragment} from "./review-fragment.js";

const STATUS_LABELS = {descriptive_only: "descriptive only", not_comparable: "not comparable"};

export function createComparisonView(state) {
  const byId = id => document.getElementById(id);

  function createTextElement(tagName, className, text) {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    element.textContent = text;
    return element;
  }

  function statusClass(status) {
    return String(status || "idle").replaceAll("_", "-").replace(/[^a-z0-9-]/g, "");
  }

  function statusLabel(status) {
    return STATUS_LABELS[status] || String(status || "idle").replaceAll("_", " ");
  }

  function setStatus(element, status, prefix = "") {
    element.className = "status-pill status-" + statusClass(status);
    element.textContent = prefix + statusLabel(status);
  }

  function setNotice(element, message) {
    element.textContent = message || "";
    element.hidden = !message;
  }

  function renderDiagnostics() {
    setNotice(byId("queryDiagnostic"), state.queryDiagnostic);
  }

  function appendDefinitionList(element, pairs) {
    element.replaceChildren();
    for (const [term, description] of pairs) {
      element.append(createTextElement("dt", "", term), createTextElement("dd", "", description));
    }
  }

  function renderManifest() {
    const chips = [
      state.manifest.studies.length + " active studies",
      state.manifest.templates.length + " planned template" + (state.manifest.templates.length === 1 ? "" : "s"),
      "selected pairs only",
      "schema v" + state.manifest.schemaVersion
    ];
    byId("pageMeta").replaceChildren(...chips.map(text => createTextElement("span", "chip", text)));
    const section = byId("plannedSection");
    const grid = byId("plannedGrid");
    grid.replaceChildren();
    section.hidden = state.manifest.templates.length === 0;
    for (const template of state.manifest.templates) {
      const card = createTextElement("article", "planned-card", "");
      card.append(
        createTextElement("h3", "", template.label),
        createTextElement("p", "", template.stage + " · " + template.axisContract.label),
        createTextElement("p", "", "Planned C" + template.concurrencies.join(" / C"))
      );
      grid.append(card);
    }
  }

  function populateStudySelect() {
    const select = byId("studySelect");
    select.replaceChildren();
    for (const study of state.manifest.studies) {
      const option = document.createElement("option");
      option.value = study.id;
      option.textContent = study.stage + " · " + study.label;
      select.append(option);
    }
    select.disabled = false;
  }

  function populateConcurrencySelect(study, selected) {
    const select = byId("concurrencySelect");
    select.replaceChildren();
    for (const concurrency of study.concurrencies) {
      const option = document.createElement("option");
      option.value = String(concurrency);
      option.textContent = "C" + concurrency;
      select.append(option);
    }
    select.value = String(selected);
    select.disabled = study.concurrencies.length < 2;
  }

  function renderAxisValues(study, baselineConfig = null, candidateConfig = null) {
    const hasValues = baselineConfig !== null && candidateConfig !== null;
    const pointers = study.expectedChangedPaths;
    const pager = byId("axisPager");
    const previous = byId("axisPrevious");
    const next = byId("axisNext");
    const page = byId("axisPage");
    let activeIndex = 0;
    function showPage(index) {
      activeIndex = Math.max(0, Math.min(index, pointers.length - 1));
      const pointer = pointers[activeIndex];
      byId("axisPath").textContent = pointer;
      byId("axisBaseline").textContent = hasValues ? valueLabel(getPointer(baselineConfig, pointer)) : "—";
      byId("axisCandidate").textContent = hasValues ? valueLabel(getPointer(candidateConfig, pointer)) : "—";
      page.textContent = (activeIndex + 1) + " / " + pointers.length;
      page.setAttribute("aria-label", "属性 " + (activeIndex + 1) + "/" + pointers.length + "：" + pointer);
      previous.disabled = !hasValues || activeIndex === 0;
      next.disabled = !hasValues || activeIndex === pointers.length - 1;
    }
    previous.onclick = () => showPage(activeIndex - 1);
    next.onclick = () => showPage(activeIndex + 1);
    pager.hidden = pointers.length < 2;
    byId("axisTitle").textContent = study.axisContract.label;
    byId("axisNote").textContent = pointers.length > 1
      ? study.axis + " 是一个逻辑 axis；它展开为 " + pointers.length + " 个属性并逐页展示，可比性校验仍要求全部按声明变化。"
      : "实际值来自两份 summary 的 context.configuration；该声明不替代可比性诊断。";
    showPage(0);
  }

  function renderLoading(study, concurrency) {
    byId("comparisonView").setAttribute("aria-busy", "true");
    byId("studyStage").textContent = study.stage;
    byId("studyTitle").textContent = study.label;
    byId("studyPolicy").textContent = study.policy + " · C" + concurrency + " · " + study.metricSet;
    byId("baselineLabel").textContent = study.baseline.label;
    byId("candidateLabel").textContent = study.candidate.label;
    byId("baselineRunId").textContent = study.baseline.expectedRunId;
    byId("candidateRunId").textContent = study.candidate.expectedRunId;
    for (const id of ["baselineMeta", "candidateMeta", "contextSummary", "contextDiagnostics", "metricRows", "shapeGrid", "outcomeGrid", "evidenceLinks"]) {
      byId(id).replaceChildren();
    }
    const reviewHost = byId("comparisonReview");
    reviewHost.replaceChildren(createTextElement("p", "panel-note", "正在加载 canonical review…"));
    reviewHost.setAttribute("aria-busy", "true");
    renderAxisValues(study);
    byId("contextCount").textContent = "—";
    byId("metricsSection").hidden = false;
    byId("shapeSection").hidden = false;
    byId("outcomeOnlyNotice").hidden = true;
    setStatus(byId("dataStatus"), "loading", "data · ");
    setStatus(byId("comparabilityStatus"), "idle", "comparability · ");
    setStatus(byId("outcomeStatus"), "idle", "outcome · ");
    setStatus(byId("analysisStatus"), "loading", "review · ");
    setNotice(byId("loadError"), "");
  }

  function renderRunCard(elementId, snapshot, expectedRun) {
    appendDefinitionList(byId(elementId), [
      ["Config", snapshot.config.config_id || "unknown"],
      ["C data", snapshot.completeCount + "/" + (snapshot.expectedRepetitions ?? "?") + " complete reps"],
      ["Raw schema", snapshot.rawValid ? "valid" : "not confirmed"],
      ["Source", statusLabel(expectedRun.sourceStatus)]
    ]);
  }

  function renderContext(comparison) {
    const context = comparison.context;
    byId("contextCount").textContent = context.matched.length + " matched";
    const declaredChangeLabel = comparison.study.expectedChangedPaths.length > 1
      ? "1 declared axis · " + context.expected.length + " properties"
      : context.expected.length + " declared change";
    byId("contextSummary").replaceChildren(
      createTextElement("span", "context-tag", context.matchedFocus.length + " critical fields matched"),
      createTextElement("span", "context-tag expected", declaredChangeLabel),
      createTextElement("span", context.unexpected.length ? "context-tag mismatch" : "context-tag", context.unexpected.length + " unexpected difference" + (context.unexpected.length === 1 ? "" : "s")),
      createTextElement("span", context.contractFingerprintMatch ? "context-tag" : "context-tag mismatch", "case contract fingerprint " + (context.contractFingerprintMatch ? "matched" : "differs"))
    );
    const diagnostics = byId("contextDiagnostics");
    diagnostics.replaceChildren();
    const rows = [
      ...context.expected.map(item => ({...item, kind: item.changed ? "expected" : "different"})),
      ...context.unexpected.map(item => ({...item, kind: "different"})),
      ...context.matchedFocus.map(item => ({...item, kind: "matched"}))
    ];
    if (!rows.length) {
      diagnostics.append(createTextElement("p", "panel-note", "没有可展示的 context 字段。"));
      return;
    }
    for (const item of rows) {
      const row = createTextElement("div", "diagnostic-row", "");
      row.append(
        createTextElement("code", item.kind, item.path + (item.kind === "expected" ? " · expected" : "")),
        createTextElement("span", item.kind === "different" ? "different" : "", "B · " + valueLabel(item.baseline)),
        createTextElement("span", item.kind === "different" ? "different" : "", "C · " + valueLabel(item.candidate))
      );
      diagnostics.append(row);
    }
  }

  function renderMetricTable(comparison) {
    const body = byId("metricRows");
    body.replaceChildren();
    for (const metric of comparison.metrics) {
      const baseline = comparison.baseline.values[metric.id];
      const candidate = comparison.candidate.values[metric.id];
      const absolute = comparison.allowDelta && isFiniteNumber(baseline) && isFiniteNumber(candidate) ? candidate - baseline : null;
      const row = document.createElement("tr");
      const name = createTextElement("td", "metric-name", metric.label);
      name.setAttribute("data-label", "Metric");
      name.append(createTextElement("small", "", metric.note));
      const baselineCell = createTextElement("td", "", isFiniteNumber(baseline) ? metric.format(baseline) : "—");
      const candidateCell = createTextElement("td", "", isFiniteNumber(candidate) ? metric.format(candidate) : "—");
      const deltaCell = createTextElement("td", "delta-neutral", isFiniteNumber(absolute) ? metric.delta(absolute) : "—");
      const relativeCell = createTextElement("td", "delta-neutral", comparison.allowDelta ? formatRelative(baseline, candidate) : "n/a");
      for (const [cell, label] of [[baselineCell, "Baseline"], [candidateCell, "Candidate"], [deltaCell, "Absolute Δ"], [relativeCell, "Relative Δ"]]) {
        cell.setAttribute("data-label", label);
      }
      row.append(name, baselineCell, candidateCell, deltaCell, relativeCell);
      body.append(row);
    }
    byId("metricMethod").textContent = comparison.allowDelta
      ? "B " + comparison.baseline.completeCount + " rep / C " + comparison.candidate.completeCount + " rep median；delta 以 baseline 为分母"
      : "两侧完整观测值可见；comparison contract 不满足，因此不计算 delta";
  }

  function renderTokenShape(comparison) {
    const grid = byId("shapeGrid");
    grid.replaceChildren();
    for (const definition of [
      {id: "actual_input_tokens_per_success", label: "Actual input tokens / success"},
      {id: "actual_output_tokens_per_success", label: "Actual output tokens / success"}
    ]) {
      const baseline = comparison.baseline.values[definition.id];
      const candidate = comparison.candidate.values[definition.id];
      const card = createTextElement("article", "shape-card", "");
      card.append(createTextElement("h5", "", definition.label));
      const values = createTextElement("div", "shape-values", "");
      for (const [label, value] of [
        ["Baseline", isFiniteNumber(baseline) ? formatNumber(baseline, 1) : "—"],
        ["Candidate", isFiniteNumber(candidate) ? formatNumber(candidate, 1) : "—"],
        ["Relative Δ", comparison.allowDelta ? formatRelative(baseline, candidate) : "n/a"]
      ]) {
        const item = document.createElement("div");
        item.append(createTextElement("span", "", label), createTextElement("strong", "", value));
        values.append(item);
      }
      card.append(values);
      grid.append(card);
    }
  }

  function outcomePairs(snapshot) {
    const run = snapshot.runContext;
    const shutdown = snapshot.shutdown;
    return [
      ["Run outcome", snapshot.outcome],
      ["Requests", formatNumber(snapshot.counts.requestCount, 0)],
      ["Successful", formatNumber(snapshot.counts.successful, 0) + " · " + formatPercent(snapshot.values.success_rate)],
      ["Failed / timeout", formatNumber(snapshot.counts.failed, 0) + " / " + formatNumber(snapshot.counts.timeouts, 0)],
      ["Stop reason", isNonEmptyString(run.stop_reason) ? run.stop_reason : "unknown"],
      ["Failure phase", isNonEmptyString(run.failure_phase) ? run.failure_phase : "none observed"],
      ["OOM killed", shutdown?.oom_killed ?? "unknown"],
      ["Lifecycle success", shutdown?.lifecycle_success ?? "unknown"]
    ];
  }

  function renderOutcome(comparison) {
    const grid = byId("outcomeGrid");
    grid.replaceChildren();
    for (const [role, snapshot] of [["Baseline", comparison.baseline], ["Candidate", comparison.candidate]]) {
      const card = createTextElement("article", "outcome-card", "");
      card.append(createTextElement("h5", "", role + " · " + snapshot.summary.run_id));
      const list = document.createElement("dl");
      appendDefinitionList(list, outcomePairs(snapshot));
      card.append(list);
      grid.append(card);
    }
    byId("outcomeNote").textContent = "C" + comparison.concurrency + " request outcomes + run lifecycle";
    const notice = byId("outcomeOnlyNotice");
    if (comparison.hasMetrics && comparison.allowDelta) {
      notice.hidden = true;
      notice.textContent = "";
    } else if (comparison.hasMetrics) {
      notice.textContent = "两侧完整观测值可并排审阅，但该 pair 不满足 comparison contract；页面不计算 delta。";
      notice.hidden = false;
    } else {
      notice.textContent = "该 pair 在 C" + comparison.concurrency + " 没有两侧都可用的 aggregate metrics；页面只展示 outcome / failure evidence，不计算不完整 delta。";
      notice.hidden = false;
    }
  }

  function renderLinks(study, reviewUrl = study.analysisUrl) {
    const links = [
      {label: "Baseline summary", url: study.baseline.summaryUrl},
      {label: "Candidate summary", url: study.candidate.summaryUrl},
      {label: "Canonical review", url: reviewUrl}
    ];
    const container = byId("evidenceLinks");
    container.replaceChildren();
    for (const link of links) {
      const anchor = createTextElement("a", "evidence-link", link.label + " ↗");
      anchor.href = link.url.href;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      anchor.setAttribute("aria-label", link.label + "（在新标签页打开）");
      container.append(anchor);
    }
  }

  function renderReview(review, comparison) {
    setStatus(byId("analysisStatus"), review.status, "review · ");
    renderReviewFragment(byId("comparisonReview"), review);
    renderLinks(comparison.study, review.sourceUrl);
  }

  function renderReviewUnavailable(message, study = null) {
    setStatus(byId("analysisStatus"), "error", "review · ");
    renderReviewError(byId("comparisonReview"), message);
    if (study) renderLinks(study);
    else byId("evidenceLinks").replaceChildren();
  }

  function renderComparison(comparison) {
    setStatus(byId("dataStatus"), comparison.dataStatus, "data · ");
    setStatus(byId("comparabilityStatus"), comparison.context.status, "comparability · ");
    setStatus(byId("outcomeStatus"), comparison.outcome, "outcome · ");
    byId("baselineRunId").textContent = comparison.baseline.summary.run_id;
    byId("candidateRunId").textContent = comparison.candidate.summary.run_id;
    renderRunCard("baselineMeta", comparison.baseline, comparison.study.baseline);
    renderRunCard("candidateMeta", comparison.candidate, comparison.study.candidate);
    renderAxisValues(comparison.study, comparison.baseline.config, comparison.candidate.config);
    renderContext(comparison);
    byId("metricsSection").hidden = !comparison.hasMetrics;
    byId("shapeSection").hidden = !comparison.hasMetrics;
    if (comparison.hasMetrics) {
      renderMetricTable(comparison);
      renderTokenShape(comparison);
    }
    renderOutcome(comparison);
  }

  return {
    byId, populateConcurrencySelect, populateStudySelect, renderComparison, renderDiagnostics,
    renderLoading, renderManifest, renderReview, renderReviewUnavailable, setNotice, setStatus
  };
}
