"use strict";

import {
  MISSING, assert, collectLeaves, getPointer, isFiniteNumber, isNonEmptyString,
  isObject, median, sameValue, sumCaseField, validJsonPointer, valueLabel
} from "./compare-data.js";

const MANIFEST_SCHEMA = 1;
const ANALYSIS_SCHEMA = 1;
const SUMMARY_SCHEMA = 2;
const ACTIVE_STATUSES = new Set(["draft", "reviewed", "final"]);
const ANALYSIS_STATUSES = new Set(["draft", "reviewed", "final", "planned"]);
const CLAIM_TYPES = new Set(["observed_fact", "interpretation", "hypothesis", "unknown"]);
const EVIDENCE_SOURCES = new Set(["metric", "baseline_summary", "candidate_summary"]);
const DERIVED_METRIC_IDS = new Set([
  "success_rate", "timeout_rate", "actual_input_tokens_per_success",
  "actual_output_tokens_per_success"
]);
const IGNORED_CONTEXT_PREFIXES = ["/config_id", "/sweep/reference_points"];
const HARD_CONTROL_PREFIXES = [
  "/model/", "/runtime/", "/workload/", "/sampling/", "/warmup/",
  "/orchestration/", "/environment/"
];

export function createComparisonModel({metrics, policyContracts, matchedContextPaths, source}) {
  function resolveStudyContract(raw, prefix) {
    const policyContract = policyContracts[raw.policy];
    assert(policyContract, prefix + ".policy 必须是 " + Object.keys(policyContracts).join(" 或 ") + "。");
    const axisContract = policyContract.axes[raw.axis];
    assert(axisContract, prefix + ".axis " + raw.axis + " 不受 policy " + raw.policy + " 支持。");
    assert(raw.metric_set === policyContract.metricSet, prefix + ".metric_set 在 policy " + raw.policy + " 下必须是 " + policyContract.metricSet + "。");
    assert(Array.isArray(raw.expected_changed_paths) && raw.expected_changed_paths.length > 0, prefix + ".expected_changed_paths 不能为空。");
    const declaredPaths = raw.expected_changed_paths.map((pointer, index) => {
      assert(validJsonPointer(pointer), prefix + ".expected_changed_paths[" + index + "] 不是有效 JSON pointer。");
      return pointer;
    });
    assert(new Set(declaredPaths).size === declaredPaths.length, prefix + ".expected_changed_paths 不允许重复。");
    const canonicalPaths = axisContract.paths;
    const exactMatch = declaredPaths.length === canonicalPaths.length &&
      declaredPaths.every((pointer, index) => pointer === canonicalPaths[index]);
    assert(exactMatch, prefix + ".expected_changed_paths 在 " + raw.policy + " / " + raw.axis + " 下必须依次为 " + canonicalPaths.join(", ") + "。");
    return {policyContract, axisContract, expectedChangedPaths: [...canonicalPaths]};
  }

  function validateManifest(data, manifestUrl) {
    assert(isObject(data), "comparisons.json 顶层必须是 object。");
    assert(data.schema_version === MANIFEST_SCHEMA, "不支持 comparison schema_version " + String(data.schema_version) + "。");
    assert(isObject(data.runs) && Object.keys(data.runs).length > 0, "runs registry 不能为空。");
    const runs = new Map();
    for (const [key, raw] of Object.entries(data.runs)) {
      const prefix = "runs." + key;
      assert(/^[a-z0-9][a-z0-9.-]*$/.test(key), prefix + " key 必须是稳定的 URL-safe id。");
      assert(isObject(raw), prefix + " 必须是 object。");
      for (const field of ["label", "summary_path", "expected_run_id", "expected_config_id", "source_status"]) {
        assert(isNonEmptyString(raw[field]), prefix + "." + field + " 缺失。");
      }
      assert(raw.source_status === "published", prefix + ".source_status 必须是 published。");
      runs.set(key, {
        key, label: raw.label, expectedRunId: raw.expected_run_id,
        expectedConfigId: raw.expected_config_id, sourceStatus: raw.source_status,
        summaryUrl: source.resolveInternal(raw.summary_path, manifestUrl, prefix + ".summary_path")
      });
    }
    assert(Array.isArray(data.studies) && data.studies.length > 0, "studies 必须包含至少一个 active study。");
    const ids = new Set();
    const studies = data.studies.map((raw, index) => {
      const prefix = "studies[" + index + "]";
      assert(isObject(raw), prefix + " 必须是 object。");
      for (const field of ["id", "label", "stage", "status", "policy", "axis", "baseline_run", "candidate_run", "metric_set", "analysis_path"]) {
        assert(isNonEmptyString(raw[field]), prefix + "." + field + " 缺失。");
      }
      assert(/^[a-z0-9][a-z0-9.-]*$/.test(raw.id), prefix + ".id 必须是稳定的 URL-safe story id。");
      assert(!ids.has(raw.id), "重复 comparison id：" + raw.id + "。");
      ids.add(raw.id);
      assert(ACTIVE_STATUSES.has(raw.status), prefix + ".status 不受支持。");
      const contract = resolveStudyContract(raw, prefix);
      assert(runs.has(raw.baseline_run), prefix + ".baseline_run 未出现在 runs registry。");
      assert(runs.has(raw.candidate_run), prefix + ".candidate_run 未出现在 runs registry。");
      assert(raw.baseline_run !== raw.candidate_run, prefix + " baseline 与 candidate 不得相同。");
      assert(Array.isArray(raw.concurrencies) && raw.concurrencies.length > 0, prefix + ".concurrencies 不能为空。");
      const concurrencies = raw.concurrencies.map(value => {
        assert(Number.isInteger(value) && value > 0, prefix + ".concurrencies 只允许正整数。");
        return value;
      });
      assert(new Set(concurrencies).size === concurrencies.length, prefix + ".concurrencies 不允许重复。");
      return {
        id: raw.id, label: raw.label, stage: raw.stage, status: raw.status,
        policy: raw.policy, axis: raw.axis, baseline: runs.get(raw.baseline_run),
        candidate: runs.get(raw.candidate_run), concurrencies, metricSet: raw.metric_set,
        ...contract,
        analysisUrl: source.resolveInternal(raw.analysis_path, manifestUrl, prefix + ".analysis_path")
      };
    });
    assert(isNonEmptyString(data.default_study), "default_study 缺失。");
    assert(ids.has(data.default_study), "default_study 未出现在 active studies 中。");
    const rawTemplates = data.templates == null ? [] : data.templates;
    assert(Array.isArray(rawTemplates), "templates 必须是 array。");
    const templates = rawTemplates.map((raw, index) => {
      const prefix = "templates[" + index + "]";
      assert(isObject(raw), prefix + " 必须是 object。");
      for (const field of ["id", "label", "stage", "status", "policy", "axis", "metric_set", "analysis_path"]) {
        assert(isNonEmptyString(raw[field]), prefix + "." + field + " 缺失。");
      }
      assert(/^[a-z0-9][a-z0-9.-]*$/.test(raw.id), prefix + ".id 必须是稳定的 URL-safe id。");
      assert(!ids.has(raw.id), "template id 与 active study 重复：" + raw.id + "。");
      ids.add(raw.id);
      assert(raw.status === "planned", prefix + ".status 必须是 planned。");
      const contract = resolveStudyContract(raw, prefix);
      assert(Array.isArray(raw.concurrencies) && raw.concurrencies.length > 0 && raw.concurrencies.every(value => Number.isInteger(value) && value > 0), prefix + ".concurrencies 必须是正整数 array。");
      assert(raw.baseline_run == null && raw.candidate_run == null, prefix + " planned template 不得引用尚未固定的 run。");
      return {
        id: raw.id, label: raw.label, stage: raw.stage, status: raw.status,
        policy: raw.policy, axis: raw.axis, metricSet: raw.metric_set,
        ...contract, concurrencies: raw.concurrencies,
        analysisUrl: source.resolveInternal(raw.analysis_path, manifestUrl, prefix + ".analysis_path")
      };
    });
    return {schemaVersion: data.schema_version, defaultStudy: data.default_study, runs, studies, templates};
  }

  function validateAnalysisLink(raw, index, analysisUrl) {
    const prefix = "links[" + index + "]";
    assert(isObject(raw), prefix + " 必须是 object。");
    assert(isNonEmptyString(raw.label), prefix + ".label 缺失。");
    assert(isNonEmptyString(raw.href), prefix + ".href 缺失。");
    assert(raw.kind !== "local_evidence", prefix + " 不能引用 local evidence。");
    assert(raw.visibility == null || raw.visibility === "public", prefix + ".visibility 只允许 public。");
    return {label: raw.label, url: source.resolveAnalysisLink(raw.href, analysisUrl, prefix + ".href")};
  }

  function validateEvidence(raw, claimIndex, evidenceIndex, study) {
    const prefix = "claims[" + claimIndex + "].evidence[" + evidenceIndex + "]";
    assert(isObject(raw), prefix + " 必须是 object。");
    assert(EVIDENCE_SOURCES.has(raw.source), prefix + ".source 不受支持。");
    if (raw.source === "metric") {
      const allowedMetrics = new Set([...study.policyContract.metricIds, ...DERIVED_METRIC_IDS]);
      assert(isNonEmptyString(raw.metric) && allowedMetrics.has(raw.metric), prefix + ".metric 不在 " + study.metricSet + " 中。");
      assert(Number.isInteger(raw.concurrency) && study.concurrencies.includes(raw.concurrency), prefix + ".concurrency 不在当前 study 的 selected concurrencies 中。");
      return {source: raw.source, metric: raw.metric, concurrency: raw.concurrency};
    }
    assert(validJsonPointer(raw.pointer), prefix + ".pointer 不是有效 JSON pointer。");
    return {source: raw.source, pointer: raw.pointer};
  }

  function validateAnalysis(data, study, analysisUrl) {
    assert(isObject(data), "comparison analysis 顶层必须是 object。");
    assert(data.schema_version === ANALYSIS_SCHEMA, "不支持 comparison analysis schema_version " + String(data.schema_version) + "。");
    assert(data.kind === "comparison_analysis", "comparison analysis kind 不匹配。");
    assert(data.comparison_id === study.id, "analysis comparison_id 与当前 study 不匹配。");
    assert(ANALYSIS_STATUSES.has(data.status), "comparison analysis status 不受支持。");
    assert(data.takeaway === null || isNonEmptyString(data.takeaway), "takeaway 必须是 string 或 null。");
    assert(Array.isArray(data.claims), "claims 必须是 array。");
    assert(Array.isArray(data.limitations) && data.limitations.every(isNonEmptyString), "limitations 必须是 string array。");
    assert(Array.isArray(data.links), "links 必须是 array。");
    const claims = data.claims.map((raw, index) => {
      const prefix = "claims[" + index + "]";
      assert(isObject(raw), prefix + " 必须是 object。");
      assert(CLAIM_TYPES.has(raw.type), prefix + ".type 不受支持。");
      assert(isNonEmptyString(raw.text), prefix + ".text 缺失。");
      assert(Array.isArray(raw.evidence), prefix + ".evidence 必须是 array。");
      const evidence = raw.evidence.map((item, evidenceIndex) => validateEvidence(item, index, evidenceIndex, study));
      if (["observed_fact", "interpretation", "unknown"].includes(raw.type)) {
        assert(evidence.length > 0, prefix + " 的 " + raw.type + " 必须引用 evidence。");
      }
      return {type: raw.type, text: raw.text, evidence};
    });
    return {
      status: data.status, takeaway: data.takeaway, claims, limitations: data.limitations,
      links: data.links.map((link, index) => validateAnalysisLink(link, index, analysisUrl))
    };
  }

  function validateSummary(data, run) {
    assert(isObject(data), run.label + " summary 顶层必须是 object。");
    assert(data.schema_version === SUMMARY_SCHEMA, run.label + " summary schema_version 必须是 " + SUMMARY_SCHEMA + "。");
    assert(isNonEmptyString(data.run_id), run.label + " summary run_id 缺失。");
    assert(isObject(data.context), run.label + " summary context 缺失。");
    assert(isObject(data.context.configuration), run.label + " summary context.configuration 缺失。");
    assert(isObject(data.context.run), run.label + " summary context.run 缺失。");
    assert(Array.isArray(data.cases), run.label + " summary cases 必须是 array。");
    assert(Array.isArray(data.concurrency_summary), run.label + " summary concurrency_summary 必须是 array。");
    const aggregateConcurrencies = new Set();
    for (const [index, aggregate] of data.concurrency_summary.entries()) {
      assert(isObject(aggregate), run.label + " concurrency_summary[" + index + "] 必须是 object。");
      assert(Number.isInteger(aggregate.concurrency) && aggregate.concurrency > 0, run.label + " concurrency_summary[" + index + "].concurrency 必须是正整数。");
      assert(!aggregateConcurrencies.has(aggregate.concurrency), run.label + " concurrency_summary 存在重复 C" + aggregate.concurrency + " aggregate row。");
      aggregateConcurrencies.add(aggregate.concurrency);
    }
    const identityIssues = [];
    if (data.run_id !== run.expectedRunId) identityIssues.push({path: "/identity/run_id", expected: run.expectedRunId, actual: data.run_id});
    if (data.context.configuration.config_id !== run.expectedConfigId) {
      identityIssues.push({path: "/identity/config_id", expected: run.expectedConfigId, actual: data.context.configuration.config_id});
    }
    return {
      data, identityIssues,
      diagnostics: [
        data.run_id === run.expectedRunId ? "" : run.label + " run_id mismatch：预期 " + run.expectedRunId + "，实际 " + data.run_id + "。",
        data.context.configuration.config_id === run.expectedConfigId ? "" : run.label + " config_id mismatch：预期 " + run.expectedConfigId + "，实际 " + String(data.context.configuration.config_id) + "。"
      ].filter(Boolean)
    };
  }

  function summarizeRun(summary, concurrency) {
    const config = summary.context.configuration;
    const cases = summary.cases.filter(item => item.concurrency === concurrency);
    const completeCases = cases.filter(item => item.measurement_complete === true && (!Array.isArray(item.invalid_reasons) || item.invalid_reasons.length === 0));
    const aggregateRows = summary.concurrency_summary.filter(item => item.concurrency === concurrency);
    assert(aggregateRows.length <= 1, summary.run_id + " 存在重复 C" + concurrency + " aggregate row。");
    const aggregate = aggregateRows[0] || null;
    const measuredCases = completeCases.length ? completeCases : cases;
    const expectedRepetitions = Number.isInteger(config.sweep?.measured_repetitions) ? config.sweep.measured_repetitions : null;
    const completeCount = Number.isInteger(aggregate?.complete_repetition_count) ? aggregate.complete_repetition_count : completeCases.length;
    const rawValid = summary.raw_validation_passed === true && summary.data_quality?.raw_schema_valid !== false;
    const aggregateConsistent = Boolean(aggregate && completeCount === completeCases.length);
    const usable = Boolean(aggregateConsistent && completeCases.length > 0);
    let dataStatus = "unavailable";
    if (usable || cases.length) {
      dataStatus = rawValid && expectedRepetitions !== null && completeCount === expectedRepetitions && completeCases.length === expectedRepetitions ? "complete" : "partial";
    }
    const requestCount = sumCaseField(measuredCases, item => item.client?.request_count);
    const successful = sumCaseField(measuredCases, item => item.client?.successful_requests);
    const failed = sumCaseField(measuredCases, item => item.client?.failed_requests);
    const timeouts = sumCaseField(measuredCases, item => item.client?.timeout_requests);
    const inputTokens = sumCaseField(measuredCases, item => item.client?.input_tokens);
    const outputTokens = sumCaseField(measuredCases, item => item.client?.output_tokens);
    const values = {};
    for (const metric of metrics) {
      const aggregateValue = metric.aggregateKey ? aggregate?.[metric.aggregateKey] : null;
      const caseValues = completeCases.map(metric.caseValue);
      values[metric.id] = caseValues.length && caseValues.every(isFiniteNumber)
        ? (isFiniteNumber(aggregateValue) ? aggregateValue : median(caseValues)) : null;
    }
    values.success_rate = requestCount > 0 ? successful / requestCount : null;
    values.timeout_rate = requestCount > 0 ? timeouts / requestCount : null;
    values.actual_input_tokens_per_success = successful > 0 ? inputTokens / successful : null;
    values.actual_output_tokens_per_success = successful > 0 ? outputTokens / successful : null;
    const fingerprints = new Set(cases.map(item => item.case_contract_fingerprint).filter(isNonEmptyString));
    if (isNonEmptyString(aggregate?.case_contract_fingerprint)) fingerprints.add(aggregate.case_contract_fingerprint);
    return {
      summary, config, aggregate, cases, completeCases, completeCount, expectedRepetitions,
      rawValid, aggregateConsistent, usable, dataStatus, values,
      counts: {requestCount, successful, failed, timeouts}, fingerprints: [...fingerprints],
      outcome: isNonEmptyString(summary.context.run.outcome) ? summary.context.run.outcome : "unknown",
      runContext: summary.context.run,
      shutdown: isObject(summary.context.observed_server?.shutdown) ? summary.context.observed_server.shutdown : null
    };
  }

  function isIgnoredContextPath(pointer) {
    return IGNORED_CONTEXT_PREFIXES.some(prefix => pointer === prefix || pointer.startsWith(prefix + "/"));
  }

  function compareContext(study, baseline, candidate, identityIssues) {
    const baselineLeaves = new Map();
    const candidateLeaves = new Map();
    collectLeaves(baseline.config, "", baselineLeaves);
    collectLeaves(candidate.config, "", candidateLeaves);
    const allPaths = new Set([...baselineLeaves.keys(), ...candidateLeaves.keys()]);
    const expectedSet = new Set(study.expectedChangedPaths);
    const expected = [];
    const unexpected = [];
    const matched = [];
    for (const pointer of [...allPaths].sort()) {
      if (!pointer || isIgnoredContextPath(pointer)) continue;
      const left = baselineLeaves.has(pointer) ? baselineLeaves.get(pointer) : MISSING;
      const right = candidateLeaves.has(pointer) ? candidateLeaves.get(pointer) : MISSING;
      if (expectedSet.has(pointer)) expected.push({path: pointer, baseline: left, candidate: right, changed: !sameValue(left, right)});
      else if (sameValue(left, right)) matched.push({path: pointer, baseline: left, candidate: right});
      else unexpected.push({path: pointer, baseline: left, candidate: right});
    }
    for (const pointer of study.expectedChangedPaths) {
      if (!expected.some(item => item.path === pointer)) {
        const left = getPointer(baseline.config, pointer);
        const right = getPointer(candidate.config, pointer);
        expected.push({path: pointer, baseline: left, candidate: right, changed: !sameValue(left, right)});
      }
    }
    for (const [path, left, right] of [
      ["/environment/architecture", baseline.summary.context.environment?.architecture ?? MISSING, candidate.summary.context.environment?.architecture ?? MISSING],
      ["/environment/node", baseline.summary.context.environment?.node ?? MISSING, candidate.summary.context.environment?.node ?? MISSING]
    ]) {
      if (left !== MISSING && right !== MISSING && sameValue(left, right)) matched.push({path, baseline: left, candidate: right});
      else unexpected.push({path, baseline: left, candidate: right, hard: true});
    }
    for (const issue of identityIssues) {
      unexpected.push({path: issue.path, baseline: "expected " + valueLabel(issue.expected), candidate: "actual " + valueLabel(issue.actual), hard: true});
    }
    const experiment = candidate.summary.context.experiment;
    for (const [path, expectedValue, actualValue] of [
      ["/candidate_experiment/kind", study.policyContract.candidateExperimentKind, experiment?.kind ?? MISSING],
      ["/candidate_experiment/axis", study.axis, experiment?.axis ?? MISSING],
      ["/candidate_experiment/baseline_config_id", study.baseline.expectedConfigId, experiment?.baseline_config_id ?? MISSING]
    ]) {
      if (!sameValue(expectedValue, actualValue)) {
        unexpected.push({path, baseline: "expected " + valueLabel(expectedValue), candidate: "actual " + valueLabel(actualValue), hard: true});
      }
    }
    const missingOrUnchangedAxis = expected.some(item => item.baseline === MISSING || item.candidate === MISSING || !item.changed);
    const hardControlMismatch = unexpected.some(item => item.hard || HARD_CONTROL_PREFIXES.some(prefix => item.path.startsWith(prefix)));
    const incompleteEvidence = baseline.dataStatus !== "complete" || candidate.dataStatus !== "complete";
    const contractFingerprintMatch = baseline.fingerprints.length === 1 && candidate.fingerprints.length === 1 && baseline.fingerprints[0] === candidate.fingerprints[0];
    let status = "controlled";
    if (incompleteEvidence || missingOrUnchangedAxis || hardControlMismatch) status = "not_comparable";
    else if (unexpected.length) status = "descriptive_only";
    return {
      status, expected, unexpected, matched,
      matchedFocus: matched.filter(item => matchedContextPaths.includes(item.path)),
      contractFingerprintMatch
    };
  }

  function pairDataStatus(baseline, candidate) {
    if (baseline.dataStatus === "complete" && candidate.dataStatus === "complete") return "complete";
    if (baseline.dataStatus === "unavailable" && candidate.dataStatus === "unavailable") return "unavailable";
    return "partial";
  }

  function pairOutcome(baseline, candidate) {
    const normalize = value => {
      const outcome = String(value || "unknown").toLowerCase();
      if (outcome === "failed" || outcome === "failure") return "failure";
      if (["success", "partial_failure", "aborted", "invalid", "running"].includes(outcome)) return outcome;
      return "unknown";
    };
    const left = normalize(baseline.outcome);
    const right = normalize(candidate.outcome);
    if (left === right) return left;
    if (left === "success") return right;
    if (right === "success") return left;
    return "mixed";
  }

  function buildComparison(study, baselineSummary, candidateSummary, concurrency, identityIssues) {
    const baseline = summarizeRun(baselineSummary, concurrency);
    const candidate = summarizeRun(candidateSummary, concurrency);
    const context = compareContext(study, baseline, candidate, identityIssues);
    const selectedMetrics = metrics.filter(metric => study.policyContract.metricIds.includes(metric.id));
    const hasMetrics = identityIssues.length === 0 && baseline.dataStatus === "complete" && candidate.dataStatus === "complete" &&
      selectedMetrics.some(metric => isFiniteNumber(baseline.values[metric.id]) && isFiniteNumber(candidate.values[metric.id]));
    return {
      study, metrics: selectedMetrics, concurrency, baseline, candidate, context,
      dataStatus: pairDataStatus(baseline, candidate), outcome: pairOutcome(baseline, candidate),
      hasMetrics, allowDelta: hasMetrics && context.status !== "not_comparable"
    };
  }

  return {buildComparison, validateAnalysis, validateManifest, validateSummary};
}
