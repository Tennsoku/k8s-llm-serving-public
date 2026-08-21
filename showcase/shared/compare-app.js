"use strict";

import {
  CORE_METRICS, MAX_MANIFEST_BYTES, MAX_SUMMARY_BYTES, createRepositorySource
} from "./compare-data.js";
import {createComparisonModel} from "./compare-model.js";
import {createComparisonView} from "./compare-view.js";

export {CORE_METRICS, formatNumber, formatSigned} from "./compare-data.js";

export function startComparison({metrics, policyContracts, matchedContextPaths}) {
  const state = {
    manifest: null,
    manifestUrl: null,
    studiesById: new Map(),
    selectedStudyId: null,
    selectedConcurrency: null,
    selectionEpoch: 0,
    controller: null,
    queryDiagnostic: "",
    evidenceDiagnostic: ""
  };
  const source = createRepositorySource();
  const model = createComparisonModel({metrics, policyContracts, matchedContextPaths, source});
  const view = createComparisonView(state);

  function updateHistory(studyId, concurrency, mode) {
    if (mode === "none") return;
    const url = new URL(window.location.href);
    url.searchParams.set("study", studyId);
    url.searchParams.set("c", String(concurrency));
    const stateValue = {study: studyId, c: concurrency};
    if (mode === "push") window.history.pushState(stateValue, "", url);
    else window.history.replaceState(stateValue, "", url);
  }

  async function loadSelection(study, concurrency, historyMode) {
    state.selectedStudyId = study.id;
    state.selectedConcurrency = concurrency;
    const epoch = ++state.selectionEpoch;
    state.controller?.abort();
    state.controller = new AbortController();
    state.evidenceDiagnostic = "";
    view.renderDiagnostics();
    view.byId("studySelect").value = study.id;
    view.populateConcurrencySelect(study, concurrency);
    view.renderLoading(study, concurrency);
    updateHistory(study.id, concurrency, historyMode);

    const signal = state.controller.signal;
    const requests = await Promise.allSettled([
      source.fetchJson(study.baseline.summaryUrl, MAX_SUMMARY_BYTES, signal),
      source.fetchJson(study.candidate.summaryUrl, MAX_SUMMARY_BYTES, signal),
      source.fetchJson(study.analysisUrl, MAX_MANIFEST_BYTES, signal)
    ]);
    if (epoch !== state.selectionEpoch || signal.aborted) return;

    const errors = [];
    let baselineResult = null;
    let candidateResult = null;
    let analysis = null;
    for (const [index, result] of requests.entries()) {
      if (result.status === "rejected") {
        const label = ["Baseline summary", "Candidate summary", "Comparison analysis"][index];
        errors.push(label + " 加载失败：" + result.reason.message);
      }
    }
    if (requests[0].status === "fulfilled") {
      try {
        baselineResult = model.validateSummary(requests[0].value.data, study.baseline);
        errors.push(...baselineResult.diagnostics);
      } catch (error) {
        errors.push("Baseline summary contract 错误：" + error.message);
      }
    }
    if (requests[1].status === "fulfilled") {
      try {
        candidateResult = model.validateSummary(requests[1].value.data, study.candidate);
        errors.push(...candidateResult.diagnostics);
      } catch (error) {
        errors.push("Candidate summary contract 错误：" + error.message);
      }
    }
    if (requests[2].status === "fulfilled") {
      try {
        analysis = model.validateAnalysis(requests[2].value.data, study, requests[2].value.url);
      } catch (error) {
        errors.push("Comparison analysis contract 错误：" + error.message);
      }
    }

    view.setNotice(view.byId("loadError"), errors.join("\n"));
    if (!baselineResult || !candidateResult) {
      view.setStatus(view.byId("dataStatus"), "unavailable", "data · ");
      view.setStatus(view.byId("comparabilityStatus"), "not_comparable", "comparability · ");
      view.setStatus(view.byId("outcomeStatus"), "unknown", "outcome · ");
      view.setStatus(view.byId("analysisStatus"), analysis ? analysis.status : "error", "analysis · ");
      view.byId("takeaway").textContent = analysis?.takeaway || "至少一侧 summary 不可用；不计算 delta。";
      view.renderClaims(analysis || view.emptyAnalysis("Comparison analysis 暂时不可用。"));
      view.renderLimitations(analysis || view.emptyAnalysis("至少一侧 summary 不可用，页面保留 outcome-only 状态。"));
      view.renderLinks(study, analysis || view.emptyAnalysis(""));
      view.byId("metricsSection").hidden = true;
      view.byId("shapeSection").hidden = true;
      view.byId("outcomeGrid").replaceChildren();
      view.setNotice(view.byId("outcomeOnlyNotice"), "至少一侧 selected summary 不可用；没有足够 evidence 生成对比指标或 run outcome。");
      view.byId("comparisonView").setAttribute("aria-busy", "false");
      return;
    }

    const comparison = model.buildComparison(
      study, baselineResult.data, candidateResult.data, concurrency,
      [...baselineResult.identityIssues, ...candidateResult.identityIssues]
    );
    view.renderComparison(comparison);
    view.renderAnalysis(analysis || view.emptyAnalysis("Comparison analysis 加载失败；computed delta 仍可独立检查。"), comparison);
    if (!analysis) view.setStatus(view.byId("analysisStatus"), "error", "analysis · ");
    view.byId("comparisonView").setAttribute("aria-busy", "false");
  }

  function selectStudy(studyId, requestedConcurrency, historyMode) {
    const study = state.studiesById.get(studyId);
    if (!study) return;
    let concurrency = Number(requestedConcurrency);
    if (!Number.isInteger(concurrency) || !study.concurrencies.includes(concurrency)) {
      if (requestedConcurrency != null) {
        state.queryDiagnostic = "URL 中的 c=" + String(requestedConcurrency) + " 不属于 " + study.id + " 的 selected concurrency；已回退 C" + study.concurrencies[0] + "。";
      }
      concurrency = study.concurrencies[0];
    }
    loadSelection(study, concurrency, historyMode).catch(error => {
      if (error.name === "AbortError") return;
      view.setNotice(view.byId("loadError"), "Comparison 加载失败：" + error.message);
      view.setStatus(view.byId("dataStatus"), "unavailable", "data · ");
      view.setStatus(view.byId("comparabilityStatus"), "not_comparable", "comparability · ");
      view.setStatus(view.byId("outcomeStatus"), "unknown", "outcome · ");
      view.setStatus(view.byId("analysisStatus"), "error", "analysis · ");
      view.byId("takeaway").textContent = "Comparison 构建失败；不保留上一组 pair 的指标或结论。";
      view.byId("metricsSection").hidden = true;
      view.byId("shapeSection").hidden = true;
      for (const id of ["metricRows", "shapeGrid", "outcomeGrid"]) view.byId(id).replaceChildren();
      view.setNotice(view.byId("outcomeOnlyNotice"), "当前 pair 无法形成有效 comparison；请检查上方 contract 错误。");
      view.byId("comparisonView").setAttribute("aria-busy", "false");
    });
  }

  function chooseInitialSelection() {
    const url = new URL(window.location.href);
    const requestedStudy = url.searchParams.get("study");
    const requestedConcurrency = url.searchParams.get("c");
    let studyId = requestedStudy;
    if (!studyId || !state.studiesById.has(studyId)) {
      if (requestedStudy) state.queryDiagnostic = "URL 中的 study=" + requestedStudy + " 不在 selected comparisons 中；已回退默认 study。";
      studyId = state.manifest.defaultStudy;
    }
    const study = state.studiesById.get(studyId);
    let concurrency = Number(requestedConcurrency);
    if (!Number.isInteger(concurrency) || !study.concurrencies.includes(concurrency)) {
      if (requestedConcurrency) {
        const message = "URL 中的 c=" + requestedConcurrency + " 不属于 " + study.id + "；已回退 C" + study.concurrencies[0] + "。";
        state.queryDiagnostic = [state.queryDiagnostic, message].filter(Boolean).join("\n");
      }
      concurrency = study.concurrencies[0];
    }
    return {studyId, concurrency};
  }

  function handlePopState() {
    if (!state.manifest) return;
    const url = new URL(window.location.href);
    const requestedStudy = url.searchParams.get("study");
    const requestedConcurrency = url.searchParams.get("c");
    state.queryDiagnostic = "";
    if (requestedStudy && state.studiesById.has(requestedStudy)) {
      selectStudy(requestedStudy, requestedConcurrency, "none");
      return;
    }
    if (requestedStudy) state.queryDiagnostic = "历史 URL 中的 study=" + requestedStudy + " 不在 selected comparisons 中；已回退默认 study。";
    const fallback = state.studiesById.get(state.manifest.defaultStudy);
    selectStudy(fallback.id, fallback.concurrencies[0], "replace");
  }

  async function bootstrap() {
    for (const id of ["dataStatus", "comparabilityStatus", "outcomeStatus", "analysisStatus"]) {
      view.byId(id).setAttribute("role", "status");
      view.byId(id).setAttribute("aria-live", "polite");
    }
    if (window.location.protocol === "file:") {
      throw new Error("Comparison page 需要通过 127.0.0.1 的 repo-root HTTP server 打开，不能使用 file://。");
    }
    const requestedManifestUrl = new URL("comparisons.json", window.location.href);
    source.setManifestUrl(requestedManifestUrl);
    const result = await source.fetchJson(requestedManifestUrl, MAX_MANIFEST_BYTES);
    state.manifestUrl = result.url;
    source.setManifestUrl(state.manifestUrl);
    state.manifest = model.validateManifest(result.data, state.manifestUrl);
    state.studiesById = new Map(state.manifest.studies.map(study => [study.id, study]));
    view.renderManifest();
    view.populateStudySelect();
    const initial = chooseInitialSelection();
    view.renderDiagnostics();
    selectStudy(initial.studyId, initial.concurrency, "replace");
  }

  view.byId("studySelect").addEventListener("change", event => {
    state.queryDiagnostic = "";
    const study = state.studiesById.get(event.target.value);
    selectStudy(study.id, study.concurrencies[0], "push");
  });
  view.byId("concurrencySelect").addEventListener("change", event => {
    state.queryDiagnostic = "";
    selectStudy(state.selectedStudyId, Number(event.target.value), "push");
  });
  window.addEventListener("popstate", handlePopState);

  bootstrap().catch(error => {
    view.byId("studySelect").disabled = true;
    view.byId("concurrencySelect").disabled = true;
    view.byId("comparisonView").setAttribute("aria-busy", "false");
    view.byId("studyStage").textContent = "manifest unavailable";
    view.byId("studyTitle").textContent = "无法加载 selected comparison index";
    view.byId("takeaway").textContent = "Comparison manifest 初始化失败；没有加载任何 analysis 或 summary。";
    view.setStatus(view.byId("dataStatus"), "error", "data · ");
    view.setStatus(view.byId("comparabilityStatus"), "not_comparable", "comparability · ");
    view.setStatus(view.byId("outcomeStatus"), "unknown", "outcome · ");
    view.setStatus(view.byId("analysisStatus"), "error", "analysis · ");
    view.setNotice(view.byId("pageError"), "Comparison 初始化失败：" + error.message);
  });
}
