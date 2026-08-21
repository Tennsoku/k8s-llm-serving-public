"use strict";

const MAX_JSON_BYTES = 2 * 1024 * 1024;
const MANIFEST_SCHEMA = 1;
const RUN_ANALYSIS_STATUSES = new Set(["draft", "reviewed", "final", "planned", "pending"]);
const REFERENCE_STATUSES = new Set(["pending", "observed", "unknown", "not_applicable"]);
const CLAIM_TYPES = new Set(["observed_fact", "interpretation", "hypothesis", "unknown"]);

export const REFERENCE_ORDER = ["c1", "c_eff", "c_pressure", "highest_tested"];
export const REFERENCE_LABELS = Object.freeze({
  c1: "C1 baseline",
  c_eff: "C_eff",
  c_pressure: "C_pressure",
  highest_tested: "Highest tested"
});
export const STATUS_LABELS = Object.freeze({
  in_progress: "in progress",
  not_applicable: "n/a"
});
export const CLAIM_LABELS = Object.freeze({
  observed_fact: "Observed fact",
  interpretation: "Interpretation",
  hypothesis: "Hypothesis",
  unknown: "Unknown"
});

export function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

export function assert(condition, message) {
  if (!condition) throw new Error(message);
}

export function createRunModel(entryContract) {
  assert(isObject(entryContract) && typeof entryContract.parseEntry === "function", "entry contract 缺失 parseEntry。" );
  let repoRootUrl = null;

  function setRepositoryRoot(url) {
    repoRootUrl = new URL(url);
  }

  function isAllowedProtocol(url) {
    return url.protocol === "http:" || url.protocol === "https:";
  }

  function isWithinRepository(url) {
    assert(repoRootUrl, "repository root 尚未初始化。");
    const prefix = repoRootUrl.pathname.endsWith("/")
      ? repoRootUrl.pathname
      : repoRootUrl.pathname + "/";
    return url.pathname === repoRootUrl.pathname || url.pathname.startsWith(prefix);
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
    const response = await fetch(url, {cache: "no-store", signal: options.signal});
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
    return {data, url: new URL(response.url || url)};
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
      const prefix = label + "[" + index + "]";
      assert(isObject(claim), prefix + " 必须是 object。");
      assert(CLAIM_TYPES.has(claim.type), prefix + ".type 不受支持。");
      assert(isNonEmptyString(claim.text), prefix + ".text 缺失。");
      const evidence = claim.evidence == null ? [] : claim.evidence;
      assert(Array.isArray(evidence) && evidence.every(isNonEmptyString), prefix + ".evidence 必须是 string array。");
      if (["observed_fact", "unknown"].includes(claim.type)) {
        assert(evidence.length > 0, prefix + " 必须引用 evidence。");
      }
      return {type: claim.type, text: claim.text, evidence};
    });
  }

  function validateStringArray(value, label) {
    assert(Array.isArray(value) && value.every(isNonEmptyString), label + " 必须是 string array。");
    return value;
  }

  function parseSingleSummary(raw, prefix, manifestUrl) {
    assert(raw.summary_set == null, prefix + ".summary_set 不属于 single-summary contract。");
    assert(isNonEmptyString(raw.expected_run_id), prefix + ".expected_run_id 缺失。");
    assert(isNonEmptyString(raw.summary_path), prefix + ".summary_path 缺失。");
    return {
      kind: "single",
      expectedRunId: raw.expected_run_id,
      summaryUrl: resolveInternal(raw.summary_path, manifestUrl, prefix + ".summary_path")
    };
  }

  function parseSummarySet(raw, prefix, manifestUrl) {
    assert(raw.expected_run_id == null && raw.summary_path == null, prefix + " 不能同时声明 single summary 与 summary_set。");
    assert(Array.isArray(raw.summary_set) && raw.summary_set.length >= 2 && raw.summary_set.length <= 3, prefix + ".summary_set 必须包含 2–3 项。");
    return {
      kind: "summary_set",
      items: raw.summary_set.map((item, index) => {
        const itemPrefix = prefix + ".summary_set[" + index + "]";
        assert(isObject(item), itemPrefix + " 必须是 object。");
        for (const key of ["label", "expected_run_id", "summary_path"]) {
          assert(isNonEmptyString(item[key]), itemPrefix + "." + key + " 缺失。");
        }
        return {
          label: item.label,
          expectedRunId: item.expected_run_id,
          summaryUrl: resolveInternal(item.summary_path, manifestUrl, itemPrefix + ".summary_path")
        };
      })
    };
  }

  function validateManifest(data, manifestUrl) {
    assert(isObject(data), "index.json 顶层必须是 object。");
    assert(data.schema_version === MANIFEST_SCHEMA, "不支持 index schema_version " + String(data.schema_version) + "。");
    assert(isNonEmptyString(data.viewer_path), "viewer_path 缺失。");
    assert(isObject(data.milestone), "milestone metadata 缺失。");
    assert(isNonEmptyString(data.milestone.id), "milestone.id 缺失。");
    assert(isNonEmptyString(data.milestone.title), "milestone.title 缺失。");
    assert(isNonEmptyString(data.milestone.analysis_path), "milestone.analysis_path 缺失。");
    assert(Array.isArray(data.entries) && data.entries.length > 0, "entries 必须包含至少一个条目。");

    const ids = new Set();
    const entries = data.entries.map((raw, index) => {
      const prefix = "entries[" + index + "]";
      assert(isObject(raw), prefix + " 必须是 object。");
      for (const key of ["id", "label", "stage", "source_status", "analysis_path"]) {
        assert(isNonEmptyString(raw[key]), prefix + "." + key + " 缺失。");
      }
      assert(raw.source_status === "published", prefix + ".source_status 必须是 published。");
      assert(/^[a-z0-9][a-z0-9.-]*$/.test(raw.id), prefix + ".id 必须是稳定的 URL-safe story id。");
      assert(!ids.has(raw.id), "重复 entry id：" + raw.id + "。");
      ids.add(raw.id);
      const contractApi = {
        assert,
        isObject,
        isNonEmptyString,
        parseSingle: () => parseSingleSummary(raw, prefix, manifestUrl),
        parseSummarySet: () => parseSummarySet(raw, prefix, manifestUrl)
      };
      const evidence = entryContract.parseEntry(raw, prefix, contractApi);
      assert(isObject(evidence) && ["single", "summary_set"].includes(evidence.kind), prefix + " entry contract 未返回有效 evidence。");
      return {
        id: raw.id,
        label: raw.label,
        stage: raw.stage,
        sourceStatus: raw.source_status,
        analysisUrl: resolveInternal(raw.analysis_path, manifestUrl, prefix + ".analysis_path"),
        evidence
      };
    });

    assert(isNonEmptyString(data.default_entry), "default_entry 缺失。");
    assert(ids.has(data.default_entry), "default_entry 未出现在 entries 中。");
    return {
      schemaVersion: data.schema_version,
      viewerUrl: resolveInternal(data.viewer_path, manifestUrl, "viewer_path"),
      milestone: {
        id: data.milestone.id,
        title: data.milestone.title,
        analysisUrl: resolveInternal(data.milestone.analysis_path, manifestUrl, "milestone.analysis_path")
      },
      defaultEntry: data.default_entry,
      entries
    };
  }

  function validateHandoff(raw) {
    assert(isObject(raw), "milestone handoff 缺失。");
    const items = Object.entries(raw);
    assert(items.length > 0, "milestone handoff 必须包含至少一项目标。");
    return items.map(([id, values]) => ({id, values: validateStringArray(values, "handoff." + id)}));
  }

  function validateMilestoneAnalysis(data, analysisUrl, milestoneId) {
    assert(isObject(data), "milestone analysis 顶层必须是 object。");
    assert(data.schema_version === 1, "不支持 milestone analysis schema。");
    assert(data.kind === "milestone_analysis", "milestone analysis kind 不匹配。");
    assert(data.milestone_id === milestoneId, "milestone_id 与 index.json 不匹配。");
    assert(isNonEmptyString(data.status), "milestone analysis status 缺失。");
    assert(isNonEmptyString(data.takeaway), "milestone takeaway 缺失。");
    return {
      status: data.status,
      takeaway: data.takeaway,
      scope: validateStringArray(data.scope, "scope"),
      claims: validateClaims(data.claims, "claims"),
      limitations: validateStringArray(data.limitations, "limitations"),
      handoff: validateHandoff(data.handoff),
      links: (data.links || []).map((link, index) => validateLink(link, index, analysisUrl))
    };
  }

  function validateReference(raw, key) {
    assert(isObject(raw), "operating_references." + key + " 必须是 object。");
    assert(REFERENCE_STATUSES.has(raw.status), "operating_references." + key + ".status 不受支持。");
    if (raw.status === "observed") {
      assert(Number.isInteger(raw.concurrency) && raw.concurrency > 0, "observed reference " + key + " 必须包含正整数 concurrency。");
    } else {
      assert(raw.concurrency === null, raw.status + " reference " + key + " 的 concurrency 必须为 null。");
    }
    const evidence = raw.evidence == null ? [] : validateStringArray(raw.evidence, "operating_references." + key + ".evidence");
    if (raw.status === "unknown") {
      assert(isNonEmptyString(raw.rationale), "unknown reference " + key + " 必须解释 tested-range evidence。");
      assert(evidence.length > 0, "unknown reference " + key + " 必须引用 tested-range evidence。");
    }
    return {
      status: raw.status,
      concurrency: raw.concurrency,
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
    for (const key of REFERENCE_ORDER) references[key] = validateReference(data.operating_references[key], key);
    return {
      status: data.status,
      takeaway: data.takeaway,
      references,
      claims: validateClaims(data.claims, "claims"),
      limitations: data.limitations == null ? [] : validateStringArray(data.limitations, "limitations"),
      links: (data.links || []).map((link, index) => validateLink(link, index, analysisUrl))
    };
  }

  return Object.freeze({
    fetchJson,
    setRepositoryRoot,
    validateManifest,
    validateMilestoneAnalysis,
    validateRunAnalysis
  });
}
