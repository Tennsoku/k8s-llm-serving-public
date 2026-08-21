"use strict";

export const MAX_MANIFEST_BYTES = 2 * 1024 * 1024;
export const MAX_SUMMARY_BYTES = 64 * 1024 * 1024;
export const MISSING = Symbol("missing");

export function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

export function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

export function assert(condition, message) {
  if (!condition) throw new Error(message);
}

export function formatNumber(value, digits) {
  if (!isFiniteNumber(value)) return "—";
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
}

export function formatSigned(value, digits) {
  if (!isFiniteNumber(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return sign + formatNumber(Math.abs(value), digits);
}

export function formatPercent(value, digits = 1) {
  return isFiniteNumber(value) ? formatNumber(value * 100, digits) + "%" : "—";
}

export function formatBytes(value) {
  return isFiniteNumber(value) ? formatNumber(value / (1024 ** 2), 0) + " MiB" : "—";
}

export function formatRelative(baseline, candidate) {
  if (!isFiniteNumber(baseline) || !isFiniteNumber(candidate) || baseline === 0) return "n/a";
  return formatSigned(((candidate - baseline) / Math.abs(baseline)) * 100, 1) + "%";
}

export function validJsonPointer(pointer) {
  return isNonEmptyString(pointer) && pointer.startsWith("/") && !/~(?:[^01]|$)/.test(pointer);
}

function decodePointerToken(token) {
  return token.replaceAll("~1", "/").replaceAll("~0", "~");
}

export function getPointer(root, pointer) {
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

export function stableValue(value) {
  if (value === MISSING) return "__missing__";
  if (Array.isArray(value)) return "[" + value.map(stableValue).join(",") + "]";
  if (isObject(value)) {
    return "{" + Object.keys(value).sort().map(key => JSON.stringify(key) + ":" + stableValue(value[key])).join(",") + "}";
  }
  return JSON.stringify(value);
}

export function sameValue(left, right) {
  return stableValue(left) === stableValue(right);
}

export function collectLeaves(value, pointer, target) {
  if (Array.isArray(value) || !isObject(value) || Object.keys(value).length === 0) {
    target.set(pointer, value);
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    const token = key.replaceAll("~", "~0").replaceAll("/", "~1");
    collectLeaves(child, pointer + "/" + token, target);
  }
}

export function valueLabel(value) {
  if (value === MISSING) return "missing";
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : formatNumber(value, 4);
  if (typeof value === "string") return value;
  const encoded = JSON.stringify(value);
  return encoded.length > 96 ? encoded.slice(0, 93) + "…" : encoded;
}

export function median(values) {
  const valid = values.filter(isFiniteNumber).sort((left, right) => left - right);
  if (!valid.length) return null;
  const middle = Math.floor(valid.length / 2);
  return valid.length % 2 ? valid[middle] : (valid[middle - 1] + valid[middle]) / 2;
}

export function sumCaseField(cases, getter) {
  if (!cases.length) return null;
  let total = 0;
  for (const item of cases) {
    const value = getter(item);
    if (!isFiniteNumber(value)) return null;
    total += value;
  }
  return total;
}

export const CORE_METRICS = [
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

export function createRepositorySource() {
  let repoRootUrl = null;

  function isAllowedProtocol(url) {
    return url.protocol === "http:" || url.protocol === "https:";
  }

  function isWithinRepository(url) {
    const prefix = repoRootUrl.pathname.endsWith("/") ? repoRootUrl.pathname : repoRootUrl.pathname + "/";
    return url.pathname === repoRootUrl.pathname || url.pathname.startsWith(prefix);
  }

  function setManifestUrl(manifestUrl) {
    repoRootUrl = new URL("../../", manifestUrl);
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

  return {fetchJson, resolveAnalysisLink, resolveInternal, setManifestUrl};
}
