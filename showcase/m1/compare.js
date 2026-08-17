"use strict";

(() => {
  const MANIFEST_SCHEMA = 1;
  const ANALYSIS_SCHEMA = 1;
  const SUMMARY_SCHEMA = 2;
  const MAX_MANIFEST_BYTES = 2 * 1024 * 1024;
  const MAX_SUMMARY_BYTES = 64 * 1024 * 1024;
  const ACTIVE_STATUSES = new Set(["draft", "reviewed", "final"]);
  const ANALYSIS_STATUSES = new Set(["draft", "reviewed", "final", "planned"]);
  const CLAIM_TYPES = new Set(["observed_fact", "interpretation", "hypothesis", "unknown"]);
  const EVIDENCE_SOURCES = new Set(["metric", "baseline_summary", "candidate_summary"]);
  const MISSING = Symbol("missing");

  const STATUS_LABELS = {
    descriptive_only: "descriptive only",
    not_comparable: "not comparable"
  };

  const CLAIM_LABELS = {
    observed_fact: "Observed fact",
    interpretation: "Interpretation",
    hypothesis: "Hypothesis",
    unknown: "Unknown"
  };

  const METRICS = [
    {
      id: "output_token_throughput_tps",
      label: "Output throughput",
      note: "median across complete repetitions",
      aggregateKey: "output_token_throughput_tps_median",
      caseValue: item => item.client?.output_token_throughput_tps,
      format: value => formatNumber(value, 1) + " tok/s",
      delta: value => formatSigned(value, 1) + " tok/s"
    },
    {
      id: "request_throughput_rps",
      label: "Request throughput",
      note: "median across complete repetitions",
      aggregateKey: "request_throughput_rps_median",
      caseValue: item => item.client?.request_throughput_rps,
      format: value => formatNumber(value, 2) + " req/s",
      delta: value => formatSigned(value, 2) + " req/s"
    },
    {
      id: "ttft_p95_seconds",
      label: "TTFT P95",
      note: "client-observed latency",
      aggregateKey: "ttft_p95_seconds_median",
      caseValue: item => item.client?.ttft_p95_seconds,
      format: value => formatNumber(value * 1000, 1) + " ms",
      delta: value => formatSigned(value * 1000, 1) + " ms"
    },
    {
      id: "tpot_p95_seconds",
      label: "TPOT P95",
      note: "client-observed latency",
      aggregateKey: "tpot_p95_seconds_median",
      caseValue: item => item.client?.tpot_p95_seconds,
      format: value => formatNumber(value * 1000, 2) + " ms",
      delta: value => formatSigned(value * 1000, 2) + " ms"
    },
    {
      id: "e2e_p95_seconds",
      label: "E2E P95",
      note: "client-observed latency",
      aggregateKey: "e2e_p95_seconds_median",
      caseValue: item => item.client?.e2e_p95_seconds,
      format: value => formatNumber(value, 3) + " s",
      delta: value => formatSigned(value, 3) + " s"
    },
    {
      id: "max_waiting_requests",
      label: "Max waiting requests",
      note: "median of repetition maxima",
      aggregateKey: "max_waiting_requests_median",
      caseValue: item => item.runtime_samples?.max_waiting_requests,
      format: value => formatNumber(value, 1),
      delta: value => formatSigned(value, 1)
    },
    {
      id: "max_running_requests",
      label: "Max running requests",
      note: "case peak · repetition median",
      aggregateKey: null,
      caseValue: item => item.runtime_samples?.max_running_requests,
      format: value => formatNumber(value, 1),
      delta: value => formatSigned(value, 1)
    },
    {
      id: "waiting_nonzero_sample_ratio",
      label: "Waiting nonzero samples",
      note: "case ratio · repetition median",
      aggregateKey: null,
      caseValue: item => item.runtime_samples?.waiting_nonzero_sample_ratio,
      format: value => formatNumber(value * 100, 2) + "%",
      delta: value => formatSigned(value * 100, 2) + " pp"
    },
    {
      id: "max_kv_cache_usage_ratio",
      label: "Max KV cache usage",
      note: "median of repetition maxima",
      aggregateKey: "max_kv_cache_usage_ratio_median",
      caseValue: item => item.runtime_samples?.max_kv_cache_usage_ratio,
      format: value => formatNumber(value * 100, 2) + "%",
      delta: value => formatSigned(value * 100, 2) + " pp"
    },
    {
      id: "process_gpu_memory_bytes",
      label: "Process GPU memory",
      note: "NVML process memory; unified-memory scope",
      aggregateKey: "max_container_nvml_process_gpu_memory_used_bytes_median",
      caseValue: item => item.system?.max_container_nvml_process_gpu_memory_used_bytes,
      format: value => formatNumber(value / (1024 ** 3), 2) + " GiB",
      delta: value => formatSigned(value / (1024 ** 3), 2) + " GiB"
    }
  ];

  const ALL_METRIC_IDS = new Set([
    ...METRICS.map(metric => metric.id),
    "success_rate",
    "timeout_rate",
    "actual_input_tokens_per_success",
    "actual_output_tokens_per_success"
  ]);

  const POLICY_CONTRACTS = {
    runtime_ovat_v1: {
      candidateExperimentKind: "ovat",
      metricSet: "m1_core_v1",
      axes: {
        "runtime.max_model_len": {
          label: "Maximum model length",
          paths: ["/runtime/max_model_len"]
        },
        "runtime.max_num_seqs": {
          label: "Maximum active sequences",
          paths: ["/runtime/max_num_seqs"]
        },
        "runtime.gpu_memory_utilization": {
          label: "GPU memory utilization",
          paths: ["/runtime/gpu_memory_utilization"]
        }
      }
    },
    model_compatibility_v1: {
      candidateExperimentKind: "compatibility",
      metricSet: "m1_compatibility_v1",
      axes: {
        model_identity: {
          label: "Model identity",
          paths: [
            "/model/id",
            "/model/path",
            "/model/artifact_revision",
            "/model/served_name"
          ]
        }
      }
    }
  };

  const MATCHED_CONTEXT_PATHS = [
    "/model/id",
    "/model/artifact_revision",
    "/runtime/image",
    "/runtime/dtype",
    "/runtime/generation_config",
    "/workload/shape",
    "/workload/input_tokens_target",
    "/workload/max_output_tokens",
    "/workload/prompt_sha256",
    "/workload/cache_identity/mode",
    "/sampling/stream",
    "/sampling/temperature",
    "/sampling/seed"
  ];

  const IGNORED_CONTEXT_PREFIXES = ["/config_id", "/sweep/reference_points"];
  const HARD_CONTROL_PREFIXES = [
    "/model/",
    "/runtime/",
    "/workload/",
    "/sampling/",
    "/warmup/",
    "/orchestration/",
    "/environment/"
  ];

  const state = {
    manifest: null,
    manifestUrl: null,
    repoRootUrl: null,
    studiesById: new Map(),
    selectedStudyId: null,
    selectedConcurrency: null,
    selectionEpoch: 0,
    controller: null,
    queryDiagnostic: "",
    evidenceDiagnostic: ""
  };

  const byId = id => document.getElementById(id);

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isNonEmptyString(value) {
    return typeof value === "string" && value.trim().length > 0;
  }

  function isFiniteNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function assert(condition, message) {
    if (!condition) throw new Error(message);
  }

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
    setNotice(
      byId("queryDiagnostic"),
      [state.queryDiagnostic, state.evidenceDiagnostic].filter(Boolean).join("\n")
    );
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
    assert(url.origin === window.location.origin, label + " 必须与 comparison page 同源。");
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

  async function fetchJson(url, maxBytes, signal) {
    const response = await fetch(url, {cache: "no-store", signal});
    if (!response.ok) {
      throw new Error("读取 " + new URL(response.url || url).pathname + " 返回 HTTP " + response.status + "。");
    }

    const finalUrl = new URL(response.url || url);
    assert(finalUrl.origin === window.location.origin, "JSON redirect 必须保持同源。");
    assert(isWithinRepository(finalUrl), "JSON redirect 必须位于 repository root 下。");

    const contentLength = Number(response.headers.get("content-length"));
    if (Number.isFinite(contentLength) && contentLength > maxBytes) {
      throw new Error("JSON 超过 " + formatBytes(maxBytes) + " 展示层限制。");
    }

    const text = await response.text();
    if (new TextEncoder().encode(text).byteLength > maxBytes) {
      throw new Error("JSON 超过 " + formatBytes(maxBytes) + " 展示层限制。");
    }

    try {
      return {data: JSON.parse(text), url: finalUrl};
    } catch (error) {
      throw new Error("JSON 解析失败：" + error.message);
    }
  }

  function validJsonPointer(pointer) {
    return isNonEmptyString(pointer) && pointer.startsWith("/") && !/~(?:[^01]|$)/.test(pointer);
  }

  function resolveStudyContract(raw, prefix) {
    const policyContract = POLICY_CONTRACTS[raw.policy];
    assert(
      policyContract,
      prefix + ".policy 必须是 " + Object.keys(POLICY_CONTRACTS).join(" 或 ") + "。"
    );
    const axisContract = policyContract.axes[raw.axis];
    assert(
      axisContract,
      prefix + ".axis " + raw.axis + " 不受 policy " + raw.policy + " 支持。"
    );
    assert(
      raw.metric_set === policyContract.metricSet,
      prefix + ".metric_set 在 policy " + raw.policy + " 下必须是 " + policyContract.metricSet + "。"
    );
    assert(Array.isArray(raw.expected_changed_paths) && raw.expected_changed_paths.length > 0, prefix + ".expected_changed_paths 不能为空。");
    const declaredPaths = raw.expected_changed_paths.map((pointer, pathIndex) => {
      assert(validJsonPointer(pointer), prefix + ".expected_changed_paths[" + pathIndex + "] 不是有效 JSON pointer。");
      return pointer;
    });
    assert(new Set(declaredPaths).size === declaredPaths.length, prefix + ".expected_changed_paths 不允许重复。");
    const canonicalPaths = axisContract.paths;
    const exactMatch = declaredPaths.length === canonicalPaths.length &&
      declaredPaths.every((pointer, index) => pointer === canonicalPaths[index]);
    assert(
      exactMatch,
      prefix + ".expected_changed_paths 在 " + raw.policy + " / " + raw.axis + " 下必须依次为 " + canonicalPaths.join(", ") + "。"
    );
    return {
      policyContract,
      axisContract,
      expectedChangedPaths: [...canonicalPaths]
    };
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
        key,
        label: raw.label,
        expectedRunId: raw.expected_run_id,
        expectedConfigId: raw.expected_config_id,
        sourceStatus: raw.source_status,
        summaryUrl: resolveInternal(raw.summary_path, manifestUrl, prefix + ".summary_path")
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
      const {policyContract, axisContract, expectedChangedPaths} = resolveStudyContract(raw, prefix);
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
        id: raw.id,
        label: raw.label,
        stage: raw.stage,
        status: raw.status,
        policy: raw.policy,
        axis: raw.axis,
        baseline: runs.get(raw.baseline_run),
        candidate: runs.get(raw.candidate_run),
        concurrencies,
        metricSet: raw.metric_set,
        policyContract,
        axisContract,
        expectedChangedPaths,
        analysisUrl: resolveInternal(raw.analysis_path, manifestUrl, prefix + ".analysis_path")
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
      const {policyContract, axisContract, expectedChangedPaths} = resolveStudyContract(raw, prefix);
      assert(Array.isArray(raw.concurrencies) && raw.concurrencies.length > 0 && raw.concurrencies.every(value => Number.isInteger(value) && value > 0), prefix + ".concurrencies 必须是正整数 array。");
      assert(raw.baseline_run == null && raw.candidate_run == null, prefix + " planned template 不得引用尚未固定的 run。");
      return {
        id: raw.id,
        label: raw.label,
        stage: raw.stage,
        status: raw.status,
        policy: raw.policy,
        axis: raw.axis,
        metricSet: raw.metric_set,
        policyContract,
        axisContract,
        expectedChangedPaths,
        concurrencies: raw.concurrencies,
        analysisUrl: resolveInternal(raw.analysis_path, manifestUrl, prefix + ".analysis_path")
      };
    });

    return {
      schemaVersion: data.schema_version,
      defaultStudy: data.default_study,
      runs,
      studies,
      templates
    };
  }

  function validateAnalysisLink(raw, index, analysisUrl) {
    const prefix = "links[" + index + "]";
    assert(isObject(raw), prefix + " 必须是 object。");
    assert(isNonEmptyString(raw.label), prefix + ".label 缺失。");
    assert(isNonEmptyString(raw.href), prefix + ".href 缺失。");
    assert(raw.kind !== "local_evidence", prefix + " 不能引用 local evidence。");
    assert(raw.visibility == null || raw.visibility === "public", prefix + ".visibility 只允许 public。");
    return {
      label: raw.label,
      url: resolveAnalysisLink(raw.href, analysisUrl, prefix + ".href")
    };
  }

  function validateEvidence(raw, claimIndex, evidenceIndex, study) {
    const prefix = "claims[" + claimIndex + "].evidence[" + evidenceIndex + "]";
    assert(isObject(raw), prefix + " 必须是 object。");
    assert(EVIDENCE_SOURCES.has(raw.source), prefix + ".source 不受支持。");
    if (raw.source === "metric") {
      assert(isNonEmptyString(raw.metric) && ALL_METRIC_IDS.has(raw.metric), prefix + ".metric 不在 " + study.metricSet + " 中。");
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
      status: data.status,
      takeaway: data.takeaway,
      claims,
      limitations: data.limitations,
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
    if (data.run_id !== run.expectedRunId) {
      identityIssues.push({path: "/identity/run_id", expected: run.expectedRunId, actual: data.run_id});
    }
    if (data.context.configuration.config_id !== run.expectedConfigId) {
      identityIssues.push({path: "/identity/config_id", expected: run.expectedConfigId, actual: data.context.configuration.config_id});
    }
    return {
      data,
      identityIssues,
      diagnostics: [
        data.run_id === run.expectedRunId
          ? ""
          : run.label + " run_id mismatch：预期 " + run.expectedRunId + "，实际 " + data.run_id + "。",
        data.context.configuration.config_id === run.expectedConfigId
          ? ""
          : run.label + " config_id mismatch：预期 " + run.expectedConfigId + "，实际 " + String(data.context.configuration.config_id) + "。"
      ].filter(Boolean)
    };
  }

  function decodePointerToken(token) {
    return token.replaceAll("~1", "/").replaceAll("~0", "~");
  }

  function getPointer(root, pointer) {
    if (pointer === "") return root;
    if (!validJsonPointer(pointer)) return MISSING;
    let value = root;
    for (const token of pointer.slice(1).split("/").map(decodePointerToken)) {
      if ((isObject(value) || Array.isArray(value)) && Object.prototype.hasOwnProperty.call(value, token)) {
        value = value[token];
      } else {
        return MISSING;
      }
    }
    return value;
  }

  function stableValue(value) {
    if (value === MISSING) return "__missing__";
    if (Array.isArray(value)) return "[" + value.map(stableValue).join(",") + "]";
    if (isObject(value)) {
      return "{" + Object.keys(value).sort().map(key => JSON.stringify(key) + ":" + stableValue(value[key])).join(",") + "}";
    }
    return JSON.stringify(value);
  }

  function sameValue(left, right) {
    return stableValue(left) === stableValue(right);
  }

  function collectLeaves(value, pointer, target) {
    if (Array.isArray(value) || !isObject(value) || Object.keys(value).length === 0) {
      target.set(pointer, value);
      return;
    }
    for (const [key, child] of Object.entries(value)) {
      const token = key.replaceAll("~", "~0").replaceAll("/", "~1");
      collectLeaves(child, pointer + "/" + token, target);
    }
  }

  function isIgnoredContextPath(pointer) {
    return IGNORED_CONTEXT_PREFIXES.some(prefix => pointer === prefix || pointer.startsWith(prefix + "/"));
  }

  function valueLabel(value) {
    if (value === MISSING) return "missing";
    if (value === null) return "null";
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "number") return Number.isInteger(value) ? String(value) : formatNumber(value, 4);
    if (typeof value === "string") return value;
    const encoded = JSON.stringify(value);
    return encoded.length > 96 ? encoded.slice(0, 93) + "…" : encoded;
  }

  function median(values) {
    const valid = values.filter(isFiniteNumber).sort((left, right) => left - right);
    if (!valid.length) return null;
    const middle = Math.floor(valid.length / 2);
    return valid.length % 2 ? valid[middle] : (valid[middle - 1] + valid[middle]) / 2;
  }

  function sumCaseField(cases, getter) {
    if (!cases.length) return null;
    let total = 0;
    for (const item of cases) {
      const value = getter(item);
      if (!isFiniteNumber(value)) return null;
      total += value;
    }
    return total;
  }

  function summarizeRun(summary, concurrency) {
    const config = summary.context.configuration;
    const cases = summary.cases.filter(item => item.concurrency === concurrency);
    const completeCases = cases.filter(item => item.measurement_complete === true && (!Array.isArray(item.invalid_reasons) || item.invalid_reasons.length === 0));
    const aggregateRows = summary.concurrency_summary.filter(item => item.concurrency === concurrency);
    assert(aggregateRows.length <= 1, summary.run_id + " 存在重复 C" + concurrency + " aggregate row。");
    const aggregate = aggregateRows[0] || null;
    const measuredCases = completeCases.length ? completeCases : cases;
    const expectedRepetitions = Number.isInteger(config.sweep?.measured_repetitions)
      ? config.sweep.measured_repetitions
      : null;
    const completeCount = Number.isInteger(aggregate?.complete_repetition_count)
      ? aggregate.complete_repetition_count
      : completeCases.length;
    const rawValid = summary.raw_validation_passed === true && summary.data_quality?.raw_schema_valid !== false;
    const aggregateConsistent = Boolean(aggregate && completeCount === completeCases.length);
    const usable = Boolean(aggregateConsistent && completeCases.length > 0);
    let dataStatus = "unavailable";
    if (usable || cases.length) {
      dataStatus = rawValid && expectedRepetitions !== null &&
        completeCount === expectedRepetitions && completeCases.length === expectedRepetitions
        ? "complete"
        : "partial";
    }

    const requestCount = sumCaseField(measuredCases, item => item.client?.request_count);
    const successful = sumCaseField(measuredCases, item => item.client?.successful_requests);
    const failed = sumCaseField(measuredCases, item => item.client?.failed_requests);
    const timeouts = sumCaseField(measuredCases, item => item.client?.timeout_requests);
    const inputTokens = sumCaseField(measuredCases, item => item.client?.input_tokens);
    const outputTokens = sumCaseField(measuredCases, item => item.client?.output_tokens);
    const values = {};

    for (const metric of METRICS) {
      const aggregateValue = metric.aggregateKey ? aggregate?.[metric.aggregateKey] : null;
      const caseValues = completeCases.map(metric.caseValue);
      values[metric.id] = caseValues.length && caseValues.every(isFiniteNumber)
        ? (isFiniteNumber(aggregateValue) ? aggregateValue : median(caseValues))
        : null;
    }
    values.success_rate = requestCount > 0 ? successful / requestCount : null;
    values.timeout_rate = requestCount > 0 ? timeouts / requestCount : null;
    values.actual_input_tokens_per_success = successful > 0 ? inputTokens / successful : null;
    values.actual_output_tokens_per_success = successful > 0 ? outputTokens / successful : null;

    const fingerprints = new Set(
      cases.map(item => item.case_contract_fingerprint).filter(isNonEmptyString)
    );
    if (isNonEmptyString(aggregate?.case_contract_fingerprint)) {
      fingerprints.add(aggregate.case_contract_fingerprint);
    }

    return {
      summary,
      config,
      aggregate,
      cases,
      completeCases,
      completeCount,
      expectedRepetitions,
      rawValid,
      aggregateConsistent,
      usable,
      dataStatus,
      values,
      counts: {requestCount, successful, failed, timeouts},
      fingerprints: [...fingerprints],
      outcome: isNonEmptyString(summary.context.run.outcome) ? summary.context.run.outcome : "unknown",
      runContext: summary.context.run,
      shutdown: isObject(summary.context.observed_server?.shutdown)
        ? summary.context.observed_server.shutdown
        : null
    };
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
      if (expectedSet.has(pointer)) {
        expected.push({path: pointer, baseline: left, candidate: right, changed: !sameValue(left, right)});
      } else if (sameValue(left, right)) {
        matched.push({path: pointer, baseline: left, candidate: right});
      } else {
        unexpected.push({path: pointer, baseline: left, candidate: right});
      }
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
      if (left !== MISSING && right !== MISSING && sameValue(left, right)) {
        matched.push({path, baseline: left, candidate: right});
      } else {
        unexpected.push({path, baseline: left, candidate: right, hard: true});
      }
    }

    for (const issue of identityIssues) {
      unexpected.push({
        path: issue.path,
        baseline: "expected " + valueLabel(issue.expected),
        candidate: "actual " + valueLabel(issue.actual),
        hard: true
      });
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
    const hardControlMismatch = unexpected.some(item =>
      item.hard || HARD_CONTROL_PREFIXES.some(prefix => item.path.startsWith(prefix))
    );
    const incompleteEvidence = baseline.dataStatus !== "complete" || candidate.dataStatus !== "complete";
    const contractFingerprintMatch = baseline.fingerprints.length === 1 && candidate.fingerprints.length === 1 && baseline.fingerprints[0] === candidate.fingerprints[0];
    let status = "controlled";
    if (incompleteEvidence || missingOrUnchangedAxis || hardControlMismatch) {
      status = "not_comparable";
    } else if (unexpected.length || !contractFingerprintMatch) {
      status = "descriptive_only";
    }

    return {
      status,
      expected,
      unexpected,
      matched,
      matchedFocus: matched.filter(item => MATCHED_CONTEXT_PATHS.includes(item.path)),
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
    const hasMetrics = identityIssues.length === 0 &&
      baseline.dataStatus === "complete" && candidate.dataStatus === "complete" &&
      METRICS.some(metric => isFiniteNumber(baseline.values[metric.id]) && isFiniteNumber(candidate.values[metric.id]));
    const allowDelta = hasMetrics && context.status !== "not_comparable";
    return {
      study,
      concurrency,
      baseline,
      candidate,
      context,
      dataStatus: pairDataStatus(baseline, candidate),
      outcome: pairOutcome(baseline, candidate),
      hasMetrics,
      allowDelta
    };
  }

  function formatNumber(value, digits) {
    if (!isFiniteNumber(value)) return "—";
    return value.toLocaleString("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    });
  }

  function formatSigned(value, digits) {
    if (!isFiniteNumber(value)) return "—";
    const sign = value > 0 ? "+" : value < 0 ? "−" : "";
    return sign + formatNumber(Math.abs(value), digits);
  }

  function formatPercent(value, digits = 1) {
    return isFiniteNumber(value) ? formatNumber(value * 100, digits) + "%" : "—";
  }

  function formatBytes(value) {
    return isFiniteNumber(value) ? formatNumber(value / (1024 ** 2), 0) + " MiB" : "—";
  }

  function formatRelative(baseline, candidate) {
    if (!isFiniteNumber(baseline) || !isFiniteNumber(candidate) || baseline === 0) return "n/a";
    return formatSigned(((candidate - baseline) / Math.abs(baseline)) * 100, 1) + "%";
  }

  function appendDefinitionList(element, pairs) {
    element.replaceChildren();
    for (const [term, description] of pairs) {
      element.append(
        createTextElement("dt", "", term),
        createTextElement("dd", "", description)
      );
    }
  }

  function renderManifestMeta() {
    const chips = [
      state.manifest.studies.length + " active studies",
      state.manifest.templates.length + " planned template" + (state.manifest.templates.length === 1 ? "" : "s"),
      "selected pairs only",
      "schema v" + state.manifest.schemaVersion
    ];
    byId("pageMeta").replaceChildren(...chips.map(text => createTextElement("span", "chip", text)));
  }

  function renderPlannedTemplates() {
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
      byId("axisBaseline").textContent = hasValues
        ? valueLabel(getPointer(baselineConfig, pointer))
        : "—";
      byId("axisCandidate").textContent = hasValues
        ? valueLabel(getPointer(candidateConfig, pointer))
        : "—";
      page.textContent = (activeIndex + 1) + " / " + pointers.length;
      page.setAttribute(
        "aria-label",
        "属性 " + (activeIndex + 1) + "/" + pointers.length + "：" + pointer
      );
      previous.disabled = !hasValues || activeIndex === 0;
      next.disabled = !hasValues || activeIndex === pointers.length - 1;
    }

    previous.onclick = () => showPage(activeIndex - 1);
    next.onclick = () => showPage(activeIndex + 1);
    pager.hidden = pointers.length < 2;
    byId("axisTitle").textContent = study.axisContract.label;
    byId("axisNote").textContent = pointers.length > 1
      ? "model_identity 是一个逻辑 axis；它展开为 " + pointers.length + " 个身份属性并逐页展示，可比性校验仍要求全部按声明变化。"
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
    byId("baselineMeta").replaceChildren();
    byId("candidateMeta").replaceChildren();
    byId("takeaway").textContent = "正在并发加载 baseline、candidate 与人工 analysis…";
    renderAxisValues(study);
    byId("contextCount").textContent = "—";
    byId("contextSummary").replaceChildren();
    byId("contextDiagnostics").replaceChildren();
    byId("metricRows").replaceChildren();
    byId("shapeGrid").replaceChildren();
    byId("outcomeGrid").replaceChildren();
    byId("claims").replaceChildren();
    byId("limitations").replaceChildren();
    byId("evidenceLinks").replaceChildren();
    byId("metricsSection").hidden = false;
    byId("shapeSection").hidden = false;
    byId("outcomeOnlyNotice").hidden = true;
    setStatus(byId("dataStatus"), "loading", "data · ");
    setStatus(byId("comparabilityStatus"), "idle", "comparability · ");
    setStatus(byId("outcomeStatus"), "idle", "outcome · ");
    setStatus(byId("analysisStatus"), "loading", "analysis · ");
    setNotice(byId("loadError"), "");
  }

  function renderRunCard(elementId, snapshot, expectedRun) {
    const pairs = [
      ["Config", snapshot.config.config_id || "unknown"],
      ["C data", snapshot.completeCount + "/" + (snapshot.expectedRepetitions ?? "?") + " complete reps"],
      ["Raw schema", snapshot.rawValid ? "valid" : "not confirmed"],
      ["Source", statusLabel(expectedRun.sourceStatus)]
    ];
    appendDefinitionList(byId(elementId), pairs);
  }

  function renderAxis(comparison) {
    renderAxisValues(comparison.study, comparison.baseline.config, comparison.candidate.config);
  }

  function renderContext(comparison) {
    const context = comparison.context;
    byId("contextCount").textContent = context.matched.length + " matched";
    const summary = byId("contextSummary");
    const declaredChangeLabel = comparison.study.expectedChangedPaths.length > 1
      ? "1 declared axis · " + context.expected.length + " properties"
      : context.expected.length + " declared change";
    summary.replaceChildren();
    summary.append(
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
      const path = createTextElement("code", item.kind, item.path + (item.kind === "expected" ? " · expected" : ""));
      row.append(
        path,
        createTextElement("span", item.kind === "different" ? "different" : "", "B · " + valueLabel(item.baseline)),
        createTextElement("span", item.kind === "different" ? "different" : "", "C · " + valueLabel(item.candidate))
      );
      diagnostics.append(row);
    }
  }

  function renderMetricTable(comparison) {
    const body = byId("metricRows");
    body.replaceChildren();
    for (const metric of METRICS) {
      const baseline = comparison.baseline.values[metric.id];
      const candidate = comparison.candidate.values[metric.id];
      const absolute = comparison.allowDelta && isFiniteNumber(baseline) && isFiniteNumber(candidate)
        ? candidate - baseline
        : null;
      const row = document.createElement("tr");
      const name = createTextElement("td", "metric-name", metric.label);
      name.setAttribute("data-label", "Metric");
      name.append(createTextElement("small", "", metric.note));
      const baselineCell = createTextElement("td", "", isFiniteNumber(baseline) ? metric.format(baseline) : "—");
      const candidateCell = createTextElement("td", "", isFiniteNumber(candidate) ? metric.format(candidate) : "—");
      const deltaCell = createTextElement("td", "delta-neutral", isFiniteNumber(absolute) ? metric.delta(absolute) : "—");
      const relativeCell = createTextElement(
        "td",
        "delta-neutral",
        comparison.allowDelta ? formatRelative(baseline, candidate) : "n/a"
      );
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

  function evidenceLabel(evidence) {
    if (evidence.source === "metric") return "metric · " + evidence.metric + " · C" + evidence.concurrency;
    return evidence.source.replaceAll("_", " ") + " · " + evidence.pointer;
  }

  function renderClaims(analysis) {
    const container = byId("claims");
    container.replaceChildren();
    if (!analysis.claims.length) {
      const card = createTextElement("article", "claim-card", "");
      card.append(
        createTextElement("span", "claim-type", "Pending"),
        createTextElement("p", "", "尚未形成可发布 comparison claim。")
      );
      container.append(card);
      return;
    }
    for (const claim of analysis.claims) {
      const card = createTextElement("article", "claim-card claim-" + claim.type.replaceAll("_", "-"), "");
      card.append(
        createTextElement("span", "claim-type", CLAIM_LABELS[claim.type]),
        createTextElement("p", "", claim.text)
      );
      for (const evidence of claim.evidence) {
        card.append(createTextElement("span", "evidence-ref", evidenceLabel(evidence)));
      }
      container.append(card);
    }
  }

  function renderLimitations(analysis) {
    const list = byId("limitations");
    list.replaceChildren();
    const values = analysis.limitations.length ? analysis.limitations : ["尚未记录 limitation。"];
    for (const text of values) list.append(createTextElement("li", "", text));
  }

  function renderLinks(study, analysis) {
    const links = [
      {label: "Baseline summary", url: study.baseline.summaryUrl},
      {label: "Candidate summary", url: study.candidate.summaryUrl},
      {label: "Comparison analysis JSON", url: study.analysisUrl},
      ...analysis.links
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

  function verifyEvidence(analysis, comparison) {
    const warnings = [];
    for (const [claimIndex, claim] of analysis.claims.entries()) {
      for (const evidence of claim.evidence) {
        if (evidence.source === "metric") {
          if (evidence.concurrency !== comparison.concurrency) continue;
          const baseline = comparison.baseline.values[evidence.metric];
          const candidate = comparison.candidate.values[evidence.metric];
          if (!isFiniteNumber(baseline) || !isFiniteNumber(candidate)) {
            warnings.push("claim " + (claimIndex + 1) + " 引用的 metric " + evidence.metric + " 在 C" + evidence.concurrency + " 不完整。");
          }
          continue;
        }
        const summary = evidence.source === "baseline_summary"
          ? comparison.baseline.summary
          : comparison.candidate.summary;
        if (getPointer(summary, evidence.pointer) === MISSING) {
          warnings.push("claim " + (claimIndex + 1) + " 的 " + evidence.source + " pointer 不存在：" + evidence.pointer + "。");
        }
      }
    }
    state.evidenceDiagnostic = warnings.join("\n");
    renderDiagnostics();
  }

  function emptyAnalysis(message) {
    return {status: "draft", takeaway: null, claims: [], limitations: [message], links: []};
  }

  function renderAnalysis(analysis, comparison) {
    setStatus(byId("analysisStatus"), analysis.status, "analysis · ");
    byId("takeaway").textContent = analysis.takeaway === null
      ? "分析进行中；尚未形成 selected takeaway。"
      : analysis.takeaway;
    renderClaims(analysis);
    renderLimitations(analysis);
    renderLinks(comparison.study, analysis);
    verifyEvidence(analysis, comparison);
  }

  function renderComparison(comparison) {
    setStatus(byId("dataStatus"), comparison.dataStatus, "data · ");
    setStatus(byId("comparabilityStatus"), comparison.context.status, "comparability · ");
    setStatus(byId("outcomeStatus"), comparison.outcome, "outcome · ");
    byId("baselineRunId").textContent = comparison.baseline.summary.run_id;
    byId("candidateRunId").textContent = comparison.candidate.summary.run_id;
    renderRunCard("baselineMeta", comparison.baseline, comparison.study.baseline);
    renderRunCard("candidateMeta", comparison.candidate, comparison.study.candidate);
    renderAxis(comparison);
    renderContext(comparison);
    byId("metricsSection").hidden = !comparison.hasMetrics;
    byId("shapeSection").hidden = !comparison.hasMetrics;
    if (comparison.hasMetrics) {
      renderMetricTable(comparison);
      renderTokenShape(comparison);
    }
    renderOutcome(comparison);
  }

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
    renderDiagnostics();
    byId("studySelect").value = study.id;
    populateConcurrencySelect(study, concurrency);
    renderLoading(study, concurrency);
    updateHistory(study.id, concurrency, historyMode);

    const signal = state.controller.signal;
    const requests = await Promise.allSettled([
      fetchJson(study.baseline.summaryUrl, MAX_SUMMARY_BYTES, signal),
      fetchJson(study.candidate.summaryUrl, MAX_SUMMARY_BYTES, signal),
      fetchJson(study.analysisUrl, MAX_MANIFEST_BYTES, signal)
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
        baselineResult = validateSummary(requests[0].value.data, study.baseline);
        errors.push(...baselineResult.diagnostics);
      } catch (error) {
        errors.push("Baseline summary contract 错误：" + error.message);
      }
    }
    if (requests[1].status === "fulfilled") {
      try {
        candidateResult = validateSummary(requests[1].value.data, study.candidate);
        errors.push(...candidateResult.diagnostics);
      } catch (error) {
        errors.push("Candidate summary contract 错误：" + error.message);
      }
    }
    if (requests[2].status === "fulfilled") {
      try {
        analysis = validateAnalysis(requests[2].value.data, study, requests[2].value.url);
      } catch (error) {
        errors.push("Comparison analysis contract 错误：" + error.message);
      }
    }

    setNotice(byId("loadError"), errors.join("\n"));
    if (!baselineResult || !candidateResult) {
      setStatus(byId("dataStatus"), "unavailable", "data · ");
      setStatus(byId("comparabilityStatus"), "not_comparable", "comparability · ");
      setStatus(byId("outcomeStatus"), "unknown", "outcome · ");
      setStatus(byId("analysisStatus"), analysis ? analysis.status : "error", "analysis · ");
      byId("takeaway").textContent = analysis?.takeaway || "至少一侧 summary 不可用；不计算 delta。";
      renderClaims(analysis || emptyAnalysis("Comparison analysis 暂时不可用。"));
      renderLimitations(analysis || emptyAnalysis("至少一侧 summary 不可用，页面保留 outcome-only 状态。"));
      renderLinks(study, analysis || emptyAnalysis(""));
      byId("metricsSection").hidden = true;
      byId("shapeSection").hidden = true;
      byId("outcomeGrid").replaceChildren();
      setNotice(byId("outcomeOnlyNotice"), "至少一侧 selected summary 不可用；没有足够 evidence 生成对比指标或 run outcome。");
      byId("comparisonView").setAttribute("aria-busy", "false");
      return;
    }

    const comparison = buildComparison(
      study,
      baselineResult.data,
      candidateResult.data,
      concurrency,
      [...baselineResult.identityIssues, ...candidateResult.identityIssues]
    );
    renderComparison(comparison);
    renderAnalysis(analysis || emptyAnalysis("Comparison analysis 加载失败；computed delta 仍可独立检查。"), comparison);
    if (!analysis) setStatus(byId("analysisStatus"), "error", "analysis · ");
    byId("comparisonView").setAttribute("aria-busy", "false");
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
      setNotice(byId("loadError"), "Comparison 加载失败：" + error.message);
      setStatus(byId("dataStatus"), "unavailable", "data · ");
      setStatus(byId("comparabilityStatus"), "not_comparable", "comparability · ");
      setStatus(byId("outcomeStatus"), "unknown", "outcome · ");
      setStatus(byId("analysisStatus"), "error", "analysis · ");
      byId("takeaway").textContent = "Comparison 构建失败；不保留上一组 pair 的指标或结论。";
      byId("metricsSection").hidden = true;
      byId("shapeSection").hidden = true;
      byId("metricRows").replaceChildren();
      byId("shapeGrid").replaceChildren();
      byId("outcomeGrid").replaceChildren();
      setNotice(byId("outcomeOnlyNotice"), "当前 pair 无法形成有效 comparison；请检查上方 contract 错误。");
      byId("comparisonView").setAttribute("aria-busy", "false");
    });
  }

  function chooseInitialSelection() {
    const url = new URL(window.location.href);
    const requestedStudy = url.searchParams.get("study");
    const requestedConcurrency = url.searchParams.get("c");
    let studyId = requestedStudy;
    if (!studyId || !state.studiesById.has(studyId)) {
      if (requestedStudy) {
        state.queryDiagnostic = "URL 中的 study=" + requestedStudy + " 不在 selected comparisons 中；已回退默认 study。";
      }
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
    if (requestedStudy) {
      state.queryDiagnostic = "历史 URL 中的 study=" + requestedStudy + " 不在 selected comparisons 中；已回退默认 study。";
    }
    const fallback = state.studiesById.get(state.manifest.defaultStudy);
    selectStudy(fallback.id, fallback.concurrencies[0], "replace");
  }

  async function bootstrap() {
    for (const id of ["dataStatus", "comparabilityStatus", "outcomeStatus", "analysisStatus"]) {
      byId(id).setAttribute("role", "status");
      byId(id).setAttribute("aria-live", "polite");
    }

    if (window.location.protocol === "file:") {
      throw new Error("Comparison page 需要通过 127.0.0.1 的 repo-root HTTP server 打开，不能使用 file://。");
    }
    const requestedManifestUrl = new URL("comparisons.json", window.location.href);
    state.repoRootUrl = new URL("../../", requestedManifestUrl);
    const result = await fetchJson(requestedManifestUrl, MAX_MANIFEST_BYTES);
    state.manifestUrl = result.url;
    state.repoRootUrl = new URL("../../", state.manifestUrl);
    state.manifest = validateManifest(result.data, state.manifestUrl);
    state.studiesById = new Map(state.manifest.studies.map(study => [study.id, study]));

    renderManifestMeta();
    renderPlannedTemplates();
    populateStudySelect();
    const initial = chooseInitialSelection();
    renderDiagnostics();
    selectStudy(initial.studyId, initial.concurrency, "replace");
  }

  byId("studySelect").addEventListener("change", event => {
    state.queryDiagnostic = "";
    const study = state.studiesById.get(event.target.value);
    selectStudy(study.id, study.concurrencies[0], "push");
  });

  byId("concurrencySelect").addEventListener("change", event => {
    state.queryDiagnostic = "";
    selectStudy(state.selectedStudyId, Number(event.target.value), "push");
  });

  window.addEventListener("popstate", handlePopState);

  bootstrap().catch(error => {
    byId("studySelect").disabled = true;
    byId("concurrencySelect").disabled = true;
    byId("comparisonView").setAttribute("aria-busy", "false");
    byId("studyStage").textContent = "manifest unavailable";
    byId("studyTitle").textContent = "无法加载 selected comparison index";
    byId("takeaway").textContent = "Comparison manifest 初始化失败；没有加载任何 analysis 或 summary。";
    setStatus(byId("dataStatus"), "error", "data · ");
    setStatus(byId("comparabilityStatus"), "not_comparable", "comparability · ");
    setStatus(byId("outcomeStatus"), "unknown", "outcome · ");
    setStatus(byId("analysisStatus"), "error", "analysis · ");
    setNotice(byId("pageError"), "Comparison 初始化失败：" + error.message);
  });
})();
