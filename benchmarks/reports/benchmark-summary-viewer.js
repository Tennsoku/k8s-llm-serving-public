"use strict";

(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const GIB = 1024 ** 3;
  const MIB_PER_GIB = 1024;
  const MAX_FILE_BYTES = 64 * 1024 * 1024;
  const SUPPORTED_SCHEMAS = new Set([1, 2]);
  const RAW_LABELS = {
    requests: "Request metrics",
    case_events: "Case events",
    runtime_samples: "Runtime samples",
    system_samples: "System samples"
  };
  const QUERY = new URLSearchParams(window.location.search);
  const VIEWER_MODE = QUERY.get("mode") === "embedded" ? "embedded" : "standalone";
  const IS_EMBEDDED = VIEWER_MODE === "embedded";
  const HOST_TOKEN = QUERY.get("host_token");
  document.documentElement.dataset.viewerMode = VIEWER_MODE;

  let model = null;
  let selectedConcurrencyValue = null;

  const byId = id => document.getElementById(id);

  function notifyHost(type, detail = {}) {
    if (
      !IS_EMBEDDED ||
      window.parent === window ||
      !["http:", "https:"].includes(window.location.protocol)
    ) return;
    try {
      window.parent.postMessage({
        source: "benchmark-summary-viewer",
        version: 1,
        hostToken: HOST_TOKEN,
        type,
        detail
      }, window.location.origin);
    } catch {
      return;
    }
  }

  function setText(id, value) {
    byId(id).textContent = value == null ? "—" : String(value);
  }

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function finite(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  }

  function getPath(object, path) {
    let current = object;
    for (const key of path) {
      if (!isObject(current) || !(key in current)) return null;
      current = current[key];
    }
    return finite(current);
  }

  function median(values) {
    if (!values.length) return null;
    const ordered = [...values].sort((left, right) => left - right);
    const middle = Math.floor(ordered.length / 2);
    return ordered.length % 2
      ? ordered[middle]
      : (ordered[middle - 1] + ordered[middle]) / 2;
  }

  function makeStats(values) {
    const clean = values.filter(value => finite(value) !== null);
    return {
      count: clean.length,
      median: median(clean),
      min: clean.length ? Math.min(...clean) : null,
      max: clean.length ? Math.max(...clean) : null
    };
  }

  function statsFor(cases, getter, transform = value => value) {
    const values = [];
    for (const item of cases) {
      const observed = finite(getter(item));
      if (observed === null) continue;
      const converted = finite(transform(observed));
      if (converted !== null) values.push(converted);
    }
    return makeStats(values);
  }

  function sumObserved(cases, getter) {
    const values = cases.map(getter).map(finite).filter(value => value !== null);
    return values.length ? values.reduce((total, value) => total + value, 0) : null;
  }

  function counterDelta(item, semantic) {
    const counter = item?.runtime_counters?.[semantic];
    if (!isObject(counter) || counter.valid !== true) return null;
    return finite(counter.delta);
  }

  function histogramMean(item, semantic) {
    const histogram = item?.server_histograms?.[semantic];
    if (!isObject(histogram) || histogram.valid !== true) return null;
    return finite(histogram.mean);
  }

  function formatNumber(value, maximumFractionDigits = 0) {
    if (finite(value) === null) return "—";
    return new Intl.NumberFormat("zh-CN", {
      maximumFractionDigits,
      minimumFractionDigits: 0
    }).format(value);
  }

  function formatCompact(value) {
    if (finite(value) === null) return "—";
    return new Intl.NumberFormat("zh-CN", {
      notation: Math.abs(value) >= 1000 ? "compact" : "standard",
      maximumFractionDigits: 1
    }).format(value);
  }

  function formatCount(value) {
    return finite(value) === null ? "—" : formatNumber(value, 0);
  }

  function formatMilliseconds(value) {
    if (finite(value) === null) return "—";
    const digits = value < 10 ? 2 : value < 100 ? 1 : 0;
    return `${formatNumber(value, digits)} ms`;
  }

  function formatSecondsAsMs(value) {
    return finite(value) === null ? "—" : formatMilliseconds(value * 1000);
  }

  function formatGiB(value) {
    if (finite(value) === null) return "—";
    return `${formatNumber(value, value < 10 ? 2 : 1)} GiB`;
  }

  function formatBytesAsGiB(value) {
    return finite(value) === null ? "—" : formatGiB(value / GIB);
  }

  function formatRatio(value, digits = 2) {
    return finite(value) === null ? "—" : `${formatNumber(value * 100, digits)}%`;
  }

  function formatPercentValue(value, digits = 1) {
    return finite(value) === null ? "—" : `${formatNumber(value, digits)}%`;
  }

  function formatSignedPercent(value) {
    if (finite(value) === null) return "—";
    return `${value > 0 ? "+" : ""}${formatNumber(value * 100, 1)}%`;
  }

  function formatDate(value) {
    if (typeof value !== "string" || !value) return "未记录生成时间";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZoneName: "short"
    }).format(date);
  }

  function formatRange(stat, formatter) {
    if (!stat || finite(stat.min) === null || finite(stat.max) === null) return "range —";
    return `${formatter(stat.min)} – ${formatter(stat.max)}`;
  }

  const METRIC_DEFS = {
    outputTps: {
      label: "输出 Token 吞吐",
      unit: "tok/s",
      format: value => formatNumber(value, value >= 100 ? 0 : 1),
      axis: value => formatCompact(value)
    },
    inputTps: {
      label: "输入 Token 吞吐",
      unit: "tok/s",
      format: value => formatNumber(value, value >= 100 ? 0 : 1),
      axis: value => formatCompact(value)
    },
    requestRps: {
      label: "Request Throughput",
      unit: "req/s",
      format: value => formatNumber(value, 2),
      axis: value => formatNumber(value, value >= 10 ? 0 : 1)
    },
    ttftP95Ms: {
      label: "P95 TTFT",
      unit: "ms",
      format: value => formatNumber(value, value < 10 ? 2 : value < 100 ? 1 : 0),
      axis: value => formatNumber(value, value < 10 ? 1 : 0)
    },
    tpotP95Ms: {
      label: "P95 TPOT",
      unit: "ms/token",
      format: value => formatNumber(value, value < 10 ? 2 : value < 100 ? 1 : 0),
      axis: value => formatNumber(value, value < 10 ? 1 : 0)
    },
    e2eP95Ms: {
      label: "P95 E2E",
      unit: "ms",
      format: value => formatNumber(value, value < 10 ? 2 : value < 100 ? 1 : 0),
      axis: value => formatNumber(value, value < 10 ? 1 : 0)
    },
    nvmlGiB: {
      label: "容器 NVML allocation",
      unit: "GiB",
      format: value => formatNumber(value, value < 10 ? 2 : 1),
      axis: value => formatNumber(value, value < 10 ? 1 : 0),
      note: "容器 cgroup 中 GPU 进程的 driver-reported allocation；不是独立 VRAM。"
    },
    cgroupCurrentGiB: {
      label: "cgroup sampled current",
      unit: "GiB",
      format: value => formatNumber(value, value < 10 ? 2 : 1),
      axis: value => formatNumber(value, value < 10 ? 1 : 0),
      note: "每个 case 采样窗口内 memory.current 的最大值。"
    },
    cgroupPeakGiB: {
      label: "cgroup lifetime peak",
      unit: "GiB",
      format: value => formatNumber(value, value < 10 ? 2 : 1),
      axis: value => formatNumber(value, value < 10 ? 1 : 0),
      note: "cgroup 生命周期水位，不代表该 case 新增的内存。"
    },
    hostUsedGiB: {
      label: "Host memory used",
      unit: "GiB",
      format: value => formatNumber(value, value < 10 ? 2 : 1),
      axis: value => formatNumber(value, value < 10 ? 1 : 0),
      note: "全主机 total − MemAvailable，包含 serving 容器之外的使用量。"
    },
    hostAvailableGiB: {
      label: "Host MemAvailable minimum",
      unit: "GiB",
      format: value => formatNumber(value, value < 10 ? 2 : 1),
      axis: value => formatNumber(value, value < 10 ? 1 : 0),
      note: "每个 case 采样窗口内的最小 MemAvailable；越低表示余量越小。"
    },
    gpuFbGiB: {
      label: "GPU framebuffer reported",
      unit: "GiB",
      format: value => formatNumber(value, value < 10 ? 2 : 1),
      axis: value => formatNumber(value, value < 10 ? 1 : 0),
      note: "GB10 上可能不支持该聚合值；null / unsupported 不是 0。"
    }
  };

  function aggregateGroup(concurrency, cases) {
    const orderedCases = [...cases].sort((leftCase, rightCase) => {
      const left = finite(leftCase.repetition) ?? Number.MAX_SAFE_INTEGER;
      const right = finite(rightCase.repetition) ?? Number.MAX_SAFE_INTEGER;
      return left - right;
    });
    const completeCases = orderedCases.filter(item => item.measurement_complete === true);

    const metrics = {
      outputTps: statsFor(completeCases, item => getPath(item, ["client", "output_token_throughput_tps"])),
      inputTps: statsFor(completeCases, item => getPath(item, ["client", "input_token_throughput_tps"])),
      requestRps: statsFor(completeCases, item => getPath(item, ["client", "request_throughput_rps"])),
      ttftP95Ms: statsFor(completeCases, item => getPath(item, ["client", "ttft_p95_seconds"]), value => value * 1000),
      tpotP95Ms: statsFor(completeCases, item => getPath(item, ["client", "tpot_p95_seconds"]), value => value * 1000),
      e2eP95Ms: statsFor(completeCases, item => getPath(item, ["client", "e2e_p95_seconds"]), value => value * 1000),
      maxRunning: statsFor(completeCases, item => getPath(item, ["runtime_samples", "max_running_requests"])),
      maxWaiting: statsFor(completeCases, item => getPath(item, ["runtime_samples", "max_waiting_requests"])),
      waitingNonzeroPct: statsFor(completeCases, item => getPath(item, ["runtime_samples", "waiting_nonzero_sample_ratio"]), value => value * 100),
      kvPct: statsFor(completeCases, item => getPath(item, ["runtime_samples", "max_kv_cache_usage_ratio"]), value => value * 100),
      gpuAvgPct: statsFor(completeCases, item => getPath(item, ["system", "avg_gpu_utilization_percent"])),
      gpuMaxPct: statsFor(completeCases, item => getPath(item, ["system", "max_gpu_utilization_percent"])),
      nvmlGiB: statsFor(completeCases, item => getPath(item, ["system", "max_container_nvml_process_gpu_memory_used_bytes"]), value => value / GIB),
      cgroupCurrentGiB: statsFor(completeCases, item => getPath(item, ["system", "max_cgroup_memory_current_bytes"]), value => value / GIB),
      cgroupPeakGiB: statsFor(completeCases, item => getPath(item, ["system", "max_cgroup_memory_peak_bytes"]), value => value / GIB),
      hostUsedGiB: statsFor(completeCases, item => getPath(item, ["system", "max_host_memory_used_bytes"]), value => value / GIB),
      hostAvailableGiB: statsFor(completeCases, item => getPath(item, ["system", "min_host_memory_available_bytes"]), value => value / GIB),
      gpuFbGiB: statsFor(completeCases, item => getPath(item, ["system", "max_gpu_memory_used_mib"]), value => value / MIB_PER_GIB),
      prefixHitPct: statsFor(completeCases, item => finite(item.prefix_cache_token_hit_ratio), value => value * 100),
      preemptions: statsFor(completeCases, item => counterDelta(item, "preemption_events_total"))
    };

    const counts = {
      requests: sumObserved(orderedCases, item => getPath(item, ["client", "request_count"])),
      successful: sumObserved(orderedCases, item => getPath(item, ["client", "successful_requests"])),
      failed: sumObserved(orderedCases, item => getPath(item, ["client", "failed_requests"])),
      timeouts: sumObserved(orderedCases, item => getPath(item, ["client", "timeout_requests"])),
      runtimeSampleFailures: sumObserved(orderedCases, item => getPath(item, ["runtime_samples", "scrape_failure_count"])),
      systemSampleFailures: sumObserved(orderedCases, item => getPath(item, ["system", "sample_failure_count"])),
      preemptions: sumObserved(orderedCases, item => counterDelta(item, "preemption_events_total")),
      cgroupHigh: sumObserved(orderedCases, item => getPath(item, ["system", "cgroup_memory_high_events_delta"])),
      cgroupMax: sumObserved(orderedCases, item => getPath(item, ["system", "cgroup_memory_max_events_delta"])),
      cgroupOom: sumObserved(orderedCases, item => getPath(item, ["system", "cgroup_oom_events_delta"])),
      cgroupOomKill: sumObserved(orderedCases, item => getPath(item, ["system", "cgroup_oom_kill_events_delta"])),
      pgscan: sumObserved(orderedCases, item => getPath(item, ["system", "host_pgscan_kswapd_delta"])),
      pgsteal: sumObserved(orderedCases, item => getPath(item, ["system", "host_pgsteal_kswapd_delta"])),
      swapIn: sumObserved(orderedCases, item => getPath(item, ["system", "host_pswpin_delta"])),
      swapOut: sumObserved(orderedCases, item => getPath(item, ["system", "host_pswpout_delta"]))
    };

    const framebuffer = { ok: 0, unsupported: 0, error: 0, recorded: false };
    for (const item of orderedCases) {
      const statuses = item?.system?.gpu_fb_memory_status_counts;
      if (!isObject(statuses)) continue;
      framebuffer.recorded = true;
      for (const status of ["ok", "unsupported", "error"]) {
        const value = finite(statuses[status]);
        if (value !== null) framebuffer[status] += value;
      }
    }

    return {
      concurrency,
      cases: orderedCases,
      completeCases,
      completeCount: completeCases.length,
      repetitionCount: orderedCases.length,
      trendEligible: orderedCases.length > 0 && completeCases.length === orderedCases.length,
      metrics,
      counts,
      framebuffer,
      marginal: null
    };
  }

  function normalizeSelectionAnalysis(value) {
    if (!isObject(value) || value.interpretation !== "annotations_only") return null;
    const pointsByConcurrency = new Map();
    if (Array.isArray(value.points)) {
      for (const point of value.points) {
        if (!isObject(point)) continue;
        const concurrency = finite(point.concurrency);
        if (concurrency !== null) pointsByConcurrency.set(concurrency, point);
      }
    }
    return {
      criteria: isObject(value.criteria) ? value.criteria : {},
      baselineConcurrency: finite(value.baseline_concurrency),
      pointsByConcurrency
    };
  }

  function selectionNotes(group) {
    const point = group.selection;
    if (!isObject(point)) return [];
    const notes = [];
    if (point.throughput_below_floor === true) notes.push("marginal below floor");
    const latency = Array.isArray(point.latency)
      ? point.latency.filter(item => isObject(item) && item.above_ceiling === true)
      : [];
    if (latency.length) notes.push(`${latency.map(item => item.metric).join("/")} above ceiling`);
    const indicators = Array.isArray(point.pressure_indicators)
      ? point.pressure_indicators.filter(item => isObject(item) && item.matched === true)
      : [];
    if (indicators.length) notes.push(`${indicators.map(item => item.metric).join("/")} observed`);
    return notes;
  }

  function validateAndNormalize(data, sourceName) {
    if (!isObject(data)) throw new Error("summary.json 顶层必须是 JSON object。");
    const schemaVersion = finite(data.schema_version);
    if (!SUPPORTED_SCHEMAS.has(schemaVersion)) {
      const observed = data.schema_version == null ? "未记录" : String(data.schema_version);
      throw new Error(`当前页面只支持 summary schema v1 / v2；收到 ${observed}。`);
    }
    if (!Array.isArray(data.cases)) {
      throw new Error("summary.json 缺少 cases[]。");
    }

    const grouped = new Map();
    for (let index = 0; index < data.cases.length; index += 1) {
      const item = data.cases[index];
      if (!isObject(item)) throw new Error(`cases[${index}] 不是 object。`);
      const concurrency = finite(item.concurrency);
      if (concurrency === null || concurrency < 0) {
        throw new Error(`cases[${index}] 缺少有效 concurrency。`);
      }
      if (!grouped.has(concurrency)) grouped.set(concurrency, []);
      grouped.get(concurrency).push(item);
    }

    const groups = [...grouped.entries()]
      .map(([concurrency, cases]) => aggregateGroup(concurrency, cases))
      .sort((left, right) => left.concurrency - right.concurrency);
    const selectionAnalysis = normalizeSelectionAnalysis(data.selection_analysis);
    for (const group of groups) {
      group.selection = selectionAnalysis?.pointsByConcurrency.get(group.concurrency) ?? null;
    }
    const allCases = groups.flatMap(group => group.cases);
    const completeCases = allCases.filter(item => item.measurement_complete === true);
    const health = {
      rawValidationPassed: data.raw_validation_passed === true
        ? true
        : data.raw_validation_passed === false ? false : null,
      completeCases: completeCases.length,
      incompleteCases: allCases.length - completeCases.length,
      totalCases: allCases.length,
      requests: sumObserved(allCases, item => getPath(item, ["client", "request_count"])),
      successful: sumObserved(allCases, item => getPath(item, ["client", "successful_requests"])),
      failed: sumObserved(allCases, item => getPath(item, ["client", "failed_requests"])),
      timeouts: sumObserved(allCases, item => getPath(item, ["client", "timeout_requests"])),
      runtimeSampleFailures: sumObserved(allCases, item => getPath(item, ["runtime_samples", "scrape_failure_count"])),
      systemSampleFailures: sumObserved(allCases, item => getPath(item, ["system", "sample_failure_count"])),
      preemptions: sumObserved(allCases, item => counterDelta(item, "preemption_events_total")),
      cgroupOom: sumObserved(allCases, item => getPath(item, ["system", "cgroup_oom_events_delta"])),
      cgroupOomKill: sumObserved(allCases, item => getPath(item, ["system", "cgroup_oom_kill_events_delta"])),
      rawValidation: isObject(data.raw_validation) ? data.raw_validation : {},
      rawRecordCounts: isObject(data.raw_record_counts) ? data.raw_record_counts : {}
    };

    const shapeCases = completeCases.length ? completeCases : allCases;
    const shapeSuccess = sumObserved(shapeCases, item => getPath(item, ["client", "successful_requests"]));
    const inputTokens = sumObserved(shapeCases, item => getPath(item, ["client", "input_tokens"]));
    const outputTokens = sumObserved(shapeCases, item => getPath(item, ["client", "output_tokens"]));
    const actualShape = {
      input: shapeSuccess && inputTokens !== null ? inputTokens / shapeSuccess : null,
      output: shapeSuccess && outputTokens !== null ? outputTokens / shapeSuccess : null,
      successSamples: shapeSuccess
    };
    const prefix = statsFor(shapeCases, item => finite(item.prefix_cache_token_hit_ratio));

    const normalized = {
      schemaVersion,
      runId: typeof data.run_id === "string" && data.run_id ? data.run_id : "未记录 run_id",
      generatedAt: typeof data.generated_at_utc === "string" ? data.generated_at_utc : null,
      sourceName: sourceName || "summary.json",
      groups,
      allCases,
      completeCases,
      health,
      actualShape,
      prefix,
      context: isObject(data.context) ? data.context : null,
      selectionAnalysis,
      raw: data,
      analysis: null,
      qualityState: "good"
    };

    normalized.analysis = analyzeRun(normalized);
    normalized.qualityState = classifyQuality(normalized);
    return normalized;
  }

  function groupPressureSignals(group) {
    const signals = [];
    if ((group.metrics.maxWaiting.max ?? 0) > 0 || (group.metrics.waitingNonzeroPct.max ?? 0) > 0) signals.push("waiting request");
    if ((group.counts.preemptions ?? 0) > 0) signals.push("preemption");
    if ((group.counts.failed ?? 0) > 0) signals.push("request failure");
    if ((group.counts.timeouts ?? 0) > 0) signals.push("timeout");
    if ((group.counts.cgroupOom ?? 0) > 0 || (group.counts.cgroupOomKill ?? 0) > 0) signals.push("OOM event");
    if ((group.counts.cgroupHigh ?? 0) > 0 || (group.counts.cgroupMax ?? 0) > 0) signals.push("cgroup pressure event");
    if ((group.counts.swapIn ?? 0) > 0 || (group.counts.swapOut ?? 0) > 0) signals.push("swap activity");
    if ((group.counts.pgscan ?? 0) > 0 || (group.counts.pgsteal ?? 0) > 0) signals.push("reclaim activity");
    return signals;
  }

  function analyzeRun(normalized) {
    const points = normalized.groups.filter(group =>
      group.trendEligible &&
      finite(group.metrics.outputTps.median) !== null &&
      finite(group.metrics.ttftP95Ms.median) !== null
    );
    const steps = [];
    for (let index = 1; index < points.length; index += 1) {
      const previous = points[index - 1];
      const current = points[index];
      const deltaConcurrency = current.concurrency - previous.concurrency;
      const deltaThroughput = current.metrics.outputTps.median - previous.metrics.outputTps.median;
      const slope = deltaConcurrency > 0 ? deltaThroughput / deltaConcurrency : null;
      const throughputGrowth = previous.metrics.outputTps.median > 0
        ? deltaThroughput / previous.metrics.outputTps.median : null;
      const ttftGrowth = previous.metrics.ttftP95Ms.median > 0
        ? (current.metrics.ttftP95Ms.median - previous.metrics.ttftP95Ms.median) / previous.metrics.ttftP95Ms.median
        : null;
      const step = {
        previous,
        current,
        deltaConcurrency,
        deltaThroughput,
        slope,
        throughputGrowth,
        ttftGrowth,
        slopeRatio: null
      };
      current.marginal = step;
      steps.push(step);
    }

    const firstPositiveSlope = steps
      .map(step => step.slope)
      .find(value => finite(value) !== null && value > 0) ?? null;
    for (const step of steps) {
      step.slopeRatio = firstPositiveSlope && finite(step.slope) !== null
        ? step.slope / firstPositiveSlope
        : null;
    }
    const trendStep = steps.find((step, index) =>
      index > 0 && finite(step.slopeRatio) !== null && step.slopeRatio <= 0.65
    ) ?? null;
    const trendPressure = trendStep ? groupPressureSignals(trendStep.current) : [];
    const baselineTtft = points[0]?.metrics.ttftP95Ms.median ?? null;
    const trendLatencyGrowth = trendStep && baselineTtft > 0
      ? trendStep.current.metrics.ttftP95Ms.median / baselineTtft - 1
      : null;
    const kneeSupported = Boolean(
      trendStep &&
      (trendStep.deltaThroughput <= 0 || trendPressure.length > 0) &&
      (trendLatencyGrowth === null || trendLatencyGrowth >= 0.2)
    );

    const failureGroup = normalized.groups.find(group =>
      (group.counts.failed ?? 0) > 0 ||
      (group.counts.timeouts ?? 0) > 0 ||
      (group.counts.cgroupOom ?? 0) > 0 ||
      (group.counts.cgroupOomKill ?? 0) > 0
    ) ?? null;
    const failureIndex = failureGroup ? normalized.groups.indexOf(failureGroup) : -1;
    const previousHealthy = failureIndex > 0
      ? [...normalized.groups.slice(0, failureIndex)].reverse().find(group =>
          group.trendEligible &&
          (group.counts.failed ?? 0) === 0 &&
          (group.counts.timeouts ?? 0) === 0 &&
          (group.counts.cgroupOom ?? 0) === 0 &&
          (group.counts.cgroupOomKill ?? 0) === 0
        ) ?? null
      : null;
    const peak = points.reduce((best, group) =>
      !best || group.metrics.outputTps.median > best.metrics.outputTps.median ? group : best
    , null);

    return {
      points,
      steps,
      firstPositiveSlope,
      trendStep,
      trendPressure,
      trendLatencyGrowth,
      kneeSupported,
      failureGroup,
      previousHealthy,
      peak
    };
  }

  function classifyQuality(normalized) {
    const health = normalized.health;
    if (health.rawValidationPassed === false || (health.cgroupOomKill ?? 0) > 0) return "bad";
    if (
      health.rawValidationPassed !== true ||
      health.incompleteCases > 0 ||
      (health.failed ?? 0) > 0 ||
      (health.timeouts ?? 0) > 0 ||
      (health.runtimeSampleFailures ?? 0) > 0 ||
      (health.systemSampleFailures ?? 0) > 0 ||
      (health.cgroupOom ?? 0) > 0
    ) return "warn";
    return "good";
  }

  function createElement(tagName, className, text) {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }

  function createSvgElement(tagName, attributes = {}, text) {
    const element = document.createElementNS(SVG_NS, tagName);
    for (const [name, value] of Object.entries(attributes)) {
      element.setAttribute(name, String(value));
    }
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }

  function appendChip(container, text, className = "") {
    const chip = createElement("span", `chip${className ? ` ${className}` : ""}`, text);
    container.append(chip);
    return chip;
  }

  function createCell(mainText, subText = null, mainClass = "") {
    const cell = document.createElement("td");
    const main = createElement("span", `cell-main${mainClass ? ` ${mainClass}` : ""}`, mainText);
    cell.append(main);
    if (subText) cell.append(createElement("span", "cell-sub", subText));
    return cell;
  }

  function renderMeta() {
    const container = byId("heroMeta");
    container.replaceChildren();
    appendChip(container, model.runId, "chip-accent");
    appendChip(container, `schema v${model.schemaVersion}`);
    appendChip(container, formatDate(model.generatedAt));
    appendChip(container, model.sourceName);
    if (model.selectionAnalysis) {
      const criteria = model.selectionAnalysis.criteria;
      const floor = finite(criteria.throughput_marginal_floor_ratio);
      const ceiling = finite(criteria.latency_multiplier_ceiling);
      appendChip(container, "selection criteria", "chip-accent");
      if (floor !== null) appendChip(container, `slope floor ${formatRatio(floor, 1)}`);
      if (ceiling !== null) appendChip(container, `latency ceiling ${formatNumber(ceiling, 1)}×`);
    }
    if (model.prefix.median !== null && model.prefix.median >= 0.9) {
      appendChip(container, `Prefix cache token hit ${formatRatio(model.prefix.median)}`, "chip-warn");
    }
  }

  function renderScopeNote() {
    const note = byId("scopeNoteText");
    const prefix = createElement("strong", "", "当前页面只做本 run 内对比。");
    const configuration = model.context?.configuration;
    const hasConfigurationContext = isObject(configuration) &&
      Object.keys(configuration).length > 0;
    const detail = hasConfigurationContext
      ? " enriched summary 包含 configuration context；viewer 仍不会自动判定跨 run 可比性。"
      : " 这是未带自包含 context 的 legacy summary；跨 run 解读仍需 companion run.yaml。";
    note.replaceChildren(prefix, document.createTextNode(detail));
  }

  function renderQualityBanner() {
    const health = model.health;
    const banner = byId("qualityBanner");
    banner.dataset.state = model.qualityState;
    const complete = `${health.completeCases}/${health.totalCases} case 采集完整`;
    const requestResult = `${formatCount(health.successful)}/${formatCount(health.requests)} 请求成功`;

    if (health.totalCases === 0) {
      setText("qualityTitle", "run 在 measured case 前结束");
      setText("qualityBadge", "仅展示 lifecycle / context");
    } else if (model.qualityState === "good") {
      setText("qualityTitle", "结构校验与采集状态完整");
      setText("qualityBadge", "可进入趋势阅读");
    } else if (model.qualityState === "warn") {
      setText("qualityTitle", "存在需先解释的数据缺口或失败信号");
      setText("qualityBadge", "谨慎解读");
    } else {
      setText("qualityTitle", "结构校验或 OOM 证据需要优先处理");
      setText("qualityBadge", "停止自动下结论");
    }
    byId("qualityBadge").className = `chip ${model.qualityState === "good" ? "chip-accent" : model.qualityState === "warn" ? "chip-warn" : "chip-danger"}`;
    setText("qualityDescription", `${complete} · ${requestResult} · failed ${formatCount(health.failed)} · timeout ${formatCount(health.timeouts)}`);
    setText("qualitySide", `${formatCount(health.requests)} requests\n${formatCount(model.raw.raw_record_counts?.runtime_samples)} runtime samples`);
  }

  function renderKpis() {
    const groups = model.groups;
    const analysis = model.analysis;
    const minimum = groups[0]?.concurrency;
    const maximum = groups.at(-1)?.concurrency;
    setText(
      "testedRangeValue",
      groups.length
        ? (minimum === maximum ? `C${formatNumber(minimum)}` : `C${formatNumber(minimum)} → C${formatNumber(maximum)}`)
        : "无 measured case"
    );
    setText("testedRangeSub", groups.length
      ? `${groups.length} 个档位 · ${model.health.totalCases} repetitions/cases`
      : "仅保留 lifecycle / context evidence");

    if (analysis.peak) {
      setText("peakThroughputValue", formatNumber(analysis.peak.metrics.outputTps.median, 0));
      setText("peakThroughputSub", `C${analysis.peak.concurrency} · ${formatRange(analysis.peak.metrics.outputTps, value => formatNumber(value, 0))}`);
    } else {
      setText("peakThroughputValue", "不可用");
      setText("peakThroughputSub", "没有采集完整的吞吐点");
    }

    if (analysis.kneeSupported) {
      setText("kneeValue", `候选 C${analysis.trendStep.current.concurrency}`);
      setText("kneeSub", "有收益变平与压力/失败共同信号，仍需人工确认");
    } else if (analysis.trendStep) {
      setText("kneeValue", "未确认");
      setText("kneeSub", `C${analysis.trendStep.current.concurrency} 起仅观察到收益递减提示`);
    } else {
      setText("kneeValue", "未观察到");
      setText("kneeSub", "现有完整档位不足以形成 knee 提示");
    }

    if (analysis.failureGroup) {
      const left = analysis.previousHealthy ? `C${analysis.previousHealthy.concurrency}` : "首个测试点之前";
      setText("capacityValue", `${left} – C${analysis.failureGroup.concurrency}`);
      setText("capacitySub", "观察到失败/OOM/timeout 的区间；不是自动容量结论");
    } else if (groups.length) {
      setText("capacityValue", "未触达");
      setText("capacitySub", `测试到 C${maximum} 未见失败、timeout 或 OOM`);
    } else {
      setText("capacityValue", "未建立");
      setText("capacitySub", "没有 measured case，查看 lifecycle stop_reason");
    }

    const input = finite(model.actualShape.input);
    const output = finite(model.actualShape.output);
    setText("workloadValue", input !== null && output !== null
      ? `${formatNumber(input, input % 1 ? 1 : 0)} → ${formatNumber(output, output % 1 ? 1 : 0)}`
      : "不可用");

    setText("prefixCacheValue", model.prefix.median === null ? "不可用" : formatRatio(model.prefix.median));
    const prefixElement = byId("prefixCacheValue");
    prefixElement.classList.toggle("amber", (model.prefix.median ?? 0) >= 0.9);
    setText("prefixCacheSub", model.prefix.median === null
      ? "summary 未提供该指标"
      : (model.prefix.median >= 0.9 ? "高命中；TTFT / input TPS 仅适用于当前缓存 workload" : "token-based hit ratio，不是 request hit rate"));
  }

  function renderInsights() {
    const analysis = model.analysis;
    const incompleteSuffix = model.health.incompleteCases
      ? `另有 ${model.health.incompleteCases} 个不完整 case 已排除出趋势。`
      : "";

    if (analysis.trendStep) {
      const step = analysis.trendStep;
      const slope = finite(step.slope) === null ? "—" : `${formatNumber(step.slope, 1)} tok/s / ΔC`;
      const ratio = finite(step.slopeRatio) === null ? "—" : formatPercentValue(step.slopeRatio * 100, 1);
      const latency = finite(analysis.trendLatencyGrowth) === null ? "TTFT 变化不可用" : `相对首个完整点，P95 TTFT ${formatSignedPercent(analysis.trendLatencyGrowth)}`;
      if (analysis.kneeSupported) {
        setText("kneeInsightTitle", `C${step.current.concurrency} 是待复验的 knee 候选区`);
        setText("kneeInsightBody", `该段每新增一个并发的吞吐增益为 ${slope}，约为初段的 ${ratio}；${latency}。同时观察到 ${analysis.trendPressure.join("、")}。这是候选提示，不是最终结论。${incompleteSuffix}`);
      } else {
        setText("kneeInsightTitle", `C${step.current.concurrency} 起出现收益递减，但 knee 尚未确认`);
        const missing = analysis.trendPressure.length
          ? `当前压力信号：${analysis.trendPressure.join("、")}，但组合证据仍不足。`
          : "没有同时观察到 waiting、preemption、失败、OOM、swap 或 reclaim。";
        setText("kneeInsightBody", `该段每新增一个并发的吞吐增益为 ${slope}，约为初段的 ${ratio}；${latency}。${missing} ${incompleteSuffix}`);
      }
    } else {
      setText("kneeInsightTitle", "现有曲线没有形成可复验的 knee 提示");
      setText("kneeInsightBody", `完整可比较点为 ${analysis.points.length} 个。需要继续扩展并发或 workload 压力，并同时观察吞吐边际收益、TTFT、queue 与资源信号。${incompleteSuffix}`);
    }

    if (analysis.failureGroup) {
      const group = analysis.failureGroup;
      const left = analysis.previousHealthy ? `最后健康点 C${analysis.previousHealthy.concurrency}` : "缺少更低的健康点";
      setText("capacityInsightTitle", `失败信号首次出现在 C${group.concurrency}`);
      setText("capacityInsightBody", `${left}；C${group.concurrency} 记录 failed ${formatCount(group.counts.failed)}、timeout ${formatCount(group.counts.timeouts)}、OOM ${formatCount(group.counts.cgroupOom)}、OOM kill ${formatCount(group.counts.cgroupOomKill)}。需要结合原始日志确认是否构成容量边界。`);
    } else if (model.groups.length) {
      const maximum = model.groups.at(-1)?.concurrency;
      setText("capacityInsightTitle", `容量边界未在 C${maximum} 以内触达`);
      setText("capacityInsightBody", `未记录 request failure、timeout、cgroup OOM/OOM kill。最高成功并发只是当前测试上界，不是容量边界；需要继续施压或改变 context/model shape。${incompleteSuffix}`);
    } else {
      const stopReason = model.context?.run?.stop_reason ?? "未记录";
      setText("capacityInsightTitle", "没有 measured case 可用于容量判断");
      setText("capacityInsightBody", `run stop_reason：${stopReason}。本页只展示 lifecycle/context，不从零 case 推导 knee 或容量边界。`);
    }
  }

  function niceCeiling(value) {
    if (finite(value) === null || value <= 0) return 1;
    const magnitude = 10 ** Math.floor(Math.log10(value));
    const normalized = value / magnitude;
    const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10;
    return nice * magnitude;
  }

  function selectGroup(concurrency, shouldScroll = false) {
    if (!model.groups.some(group => group.concurrency === concurrency)) return;
    selectedConcurrencyValue = concurrency;
    byId("selectedConcurrency").value = String(concurrency);
    renderCharts();
    renderComparison();
    renderSelectedGroup();
    if (shouldScroll) byId("repeatHeading").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderRangeChart(hostId, metricKey) {
    const host = byId(hostId);
    host.replaceChildren();
    const definition = METRIC_DEFS[metricKey];
    const points = model.analysis.points.filter(group => finite(group.metrics[metricKey]?.median) !== null);
    if (!points.length) {
      host.append(createElement("div", "chart-empty", `${definition.label} 在当前 summary 中不可用；缺失值未按 0 绘制。`));
      return;
    }

    const width = 760;
    const height = 300;
    const margin = { top: 24, right: 20, bottom: 48, left: 62 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const maximum = Math.max(...points.map(point => point.metrics[metricKey].max ?? point.metrics[metricKey].median));
    const ceiling = niceCeiling(maximum * 1.08);
    const xStep = points.length > 1 ? plotWidth / (points.length - 1) : 0;
    const xAt = index => points.length > 1 ? margin.left + index * xStep : margin.left + plotWidth / 2;
    const yAt = value => margin.top + plotHeight - (value / ceiling) * plotHeight;
    const svg = createSvgElement("svg", {
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": `${definition.label} 与 concurrency 的曲线`
    });

    const selectedIndex = points.findIndex(point => point.concurrency === selectedConcurrencyValue);
    if (selectedIndex >= 0) {
      const bandWidth = points.length > 1 ? Math.min(70, xStep * 0.65) : 70;
      svg.append(createSvgElement("rect", {
        x: xAt(selectedIndex) - bandWidth / 2,
        y: margin.top,
        width: bandWidth,
        height: plotHeight,
        rx: 8,
        class: "chart-selection"
      }));
    }

    const tickCount = 4;
    for (let tick = 0; tick <= tickCount; tick += 1) {
      const value = ceiling * tick / tickCount;
      const y = yAt(value);
      svg.append(createSvgElement("line", {
        x1: margin.left,
        x2: width - margin.right,
        y1: y,
        y2: y,
        class: tick === 0 ? "chart-axis-line" : "chart-grid-line"
      }));
      svg.append(createSvgElement("text", {
        x: margin.left - 10,
        y: y + 4,
        "text-anchor": "end",
        class: "chart-axis-label"
      }, definition.axis(value)));
    }

    if (points.length > 1) {
      const upper = points.map((point, index) => `${xAt(index)},${yAt(point.metrics[metricKey].max)}`);
      const lower = [...points].reverse().map((point, reverseIndex) => {
        const index = points.length - 1 - reverseIndex;
        return `${xAt(index)},${yAt(point.metrics[metricKey].min)}`;
      });
      svg.append(createSvgElement("polygon", {
        points: [...upper, ...lower].join(" "),
        class: "chart-range"
      }));
    }

    for (let index = 0; index < points.length; index += 1) {
      const point = points[index];
      const x = xAt(index);
      const stat = point.metrics[metricKey];
      svg.append(createSvgElement("line", {
        x1: x,
        x2: x,
        y1: yAt(stat.min),
        y2: yAt(stat.max),
        class: "chart-whisker"
      }));
    }

    const path = points.map((point, index) => `${index ? "L" : "M"}${xAt(index)},${yAt(point.metrics[metricKey].median)}`).join(" ");
    svg.append(createSvgElement("path", { d: path, class: "chart-line" }));

    const trendConcurrency = model.analysis.trendStep?.current.concurrency;
    const trendIndex = points.findIndex(point => point.concurrency === trendConcurrency);
    if (trendIndex >= 0 && ["outputTps", "inputTps", "requestRps", "ttftP95Ms", "tpotP95Ms", "e2eP95Ms"].includes(metricKey)) {
      const x = xAt(trendIndex);
      svg.append(createSvgElement("line", {
        x1: x,
        x2: x,
        y1: margin.top,
        y2: margin.top + plotHeight,
        class: "chart-knee-line"
      }));
      svg.append(createSvgElement("text", {
        x: x + 6,
        y: margin.top + 11,
        class: "chart-knee-label"
      }, "收益递减提示"));
    }

    for (let index = 0; index < points.length; index += 1) {
      const point = points[index];
      const stat = point.metrics[metricKey];
      const circle = createSvgElement("circle", {
        cx: xAt(index),
        cy: yAt(stat.median),
        r: 5,
        class: `chart-dot${point.concurrency === selectedConcurrencyValue ? " selected" : ""}`,
        tabindex: 0,
        role: "button",
        "aria-label": `C${point.concurrency} ${definition.label} ${definition.format(stat.median)} ${definition.unit}`
      });
      circle.append(createSvgElement("title", {}, `C${point.concurrency} · median ${definition.format(stat.median)} ${definition.unit}\nmin–max ${definition.format(stat.min)} – ${definition.format(stat.max)}`));
      circle.addEventListener("click", () => selectGroup(point.concurrency));
      circle.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectGroup(point.concurrency);
        }
      });
      svg.append(circle);
      svg.append(createSvgElement("text", {
        x: xAt(index),
        y: height - 22,
        "text-anchor": "middle",
        class: "chart-axis-label"
      }, `C${point.concurrency}`));
    }

    svg.append(createSvgElement("text", {
      x: width - margin.right,
      y: height - 5,
      "text-anchor": "end",
      class: "chart-axis-label"
    }, "已测试档位（等距）"));
    host.append(svg);
  }

  function selectedGroup() {
    return model.groups.find(group => group.concurrency === selectedConcurrencyValue) ?? model.groups.at(-1);
  }

  function renderChartHeader(statId, rangeId, metricKey) {
    const group = selectedGroup();
    const definition = METRIC_DEFS[metricKey];
    const stat = group?.metrics[metricKey];
    setText(statId, group && stat?.median !== null
      ? `C${group.concurrency} · ${definition.format(stat.median)} ${definition.unit}`
      : `${definition.label} 不可用`);
    setText(rangeId, stat?.median !== null
      ? `repeat ${formatRange(stat, definition.format)} ${definition.unit}`
      : "null / unsupported 未按 0 处理");
  }

  function incompletePointNote() {
    const incomplete = model.groups.filter(group => !group.trendEligible).map(group => `C${group.concurrency}`);
    return incomplete.length ? ` 不完整点 ${incomplete.join("、")} 未进入曲线。` : "";
  }

  function renderCharts() {
    const throughputMetric = byId("throughputMetric").value;
    const latencyMetric = byId("latencyMetric").value;
    const memoryMetric = byId("memoryMetric").value;
    renderRangeChart("throughputChart", throughputMetric);
    renderRangeChart("latencyChart", latencyMetric);
    renderRangeChart("memoryChart", memoryMetric);
    renderChartHeader("throughputChartStat", "throughputChartRange", throughputMetric);
    renderChartHeader("latencyChartStat", "latencyChartRange", latencyMetric);
    renderChartHeader("memoryChartStat", "memoryChartRange", memoryMetric);
    setText("throughputChartNote", `横轴按已测试档位等距排列；边际表按真实 ΔC 计算。${incompletePointNote()}`);
    setText("latencyChartNote", `${latencyMetric === "tpotP95Ms" ? "TPOT 是请求级平均 decode 间隔的分位，不是 token-level ITL。" : "分位数只使用成功请求。"}${incompletePointNote()}`);
    const memoryDefinition = METRIC_DEFS[memoryMetric];
    const unsupported = model.groups.reduce((total, group) => total + group.framebuffer.unsupported, 0);
    const unsupportedText = memoryMetric === "gpuFbGiB" && unsupported > 0
      ? ` 当前记录 ${formatCount(unsupported)} 个 unsupported sample，因此不显示为 0。`
      : "";
    setText("memoryChartNote", `${memoryDefinition.note}${unsupportedText}${incompletePointNote()}`);
  }

  function createPressureCard(label, value, subtext) {
    const card = createElement("div", "pressure-card");
    card.append(createElement("span", "", label));
    card.append(createElement("strong", "", value));
    card.append(createElement("small", "", subtext));
    return card;
  }

  function renderSelectedGroup() {
    const group = selectedGroup();
    if (!group) return;
    setText("selectedConcurrencyMeta", `C${group.concurrency} · ${group.completeCount}/${group.repetitionCount} repeats 采集完整`);
    const pressureGrid = byId("pressureGrid");
    pressureGrid.replaceChildren(
      createPressureCard("运行请求峰值", formatNumber(group.metrics.maxRunning.median, 1), formatRange(group.metrics.maxRunning, value => formatNumber(value, 1))),
      createPressureCard("等待请求峰值", formatNumber(group.metrics.maxWaiting.median, 1), `nonzero samples ${formatPercentValue(group.metrics.waitingNonzeroPct.median, 1)}`),
      createPressureCard("KV Cache 峰值", formatPercentValue(group.metrics.kvPct.median, 3), formatRange(group.metrics.kvPct, value => formatPercentValue(value, 3))),
      createPressureCard("GPU 利用率", formatPercentValue(group.metrics.gpuAvgPct.median, 1), `case max ${formatPercentValue(group.metrics.gpuMaxPct.max, 1)}`),
      createPressureCard("Preemption events", formatCount(group.counts.preemptions), `${group.repetitionCount} repeats 合计；不是唯一请求数`),
      createPressureCard("Memory / OOM events", formatCount((group.counts.cgroupHigh ?? 0) + (group.counts.cgroupMax ?? 0) + (group.counts.cgroupOom ?? 0) + (group.counts.cgroupOomKill ?? 0)), `OOM ${formatCount(group.counts.cgroupOom)} · kill ${formatCount(group.counts.cgroupOomKill)}`)
    );

    const signals = groupPressureSignals(group);
    const gpu = group.metrics.gpuAvgPct.median;
    let narrative;
    if (!group.trendEligible) {
      narrative = "该并发含 measurement_complete=false 的 repetition，不进入自动趋势曲线；请先查看下方 invalid_reasons。";
    } else if (signals.length) {
      narrative = `观察到 ${signals.join("、")}。这些是压力或失败事实，但需要结合吞吐与延迟重复性判断是否构成 knee / boundary。`;
    } else {
      narrative = `未观察 waiting、preemption、失败、OOM、swap 或 reclaim。${gpu !== null ? `GPU 平均利用率中位数为 ${formatPercentValue(gpu, 1)}；高利用率本身不等于容量边界。` : "GPU utilization 不可用。"}`;
    }
    setText("pressureNarrative", narrative);
    renderRepeatTable(group);
  }

  function renderComparison() {
    const body = byId("comparisonBody");
    body.replaceChildren();
    const trendConcurrency = model.analysis.trendStep?.current.concurrency;

    for (const group of model.groups) {
      const row = document.createElement("tr");
      row.tabIndex = 0;
      row.setAttribute("aria-label", `查看 C${group.concurrency} repetition 明细`);
      if (group.concurrency === selectedConcurrencyValue) row.classList.add("is-selected");
      if (group.concurrency === trendConcurrency) row.classList.add("is-trend");
      if (!group.trendEligible) row.classList.add("is-incomplete");

      const status = group.trendEligible ? "参与趋势" : "不完整，排除出趋势";
      const configuredNotes = selectionNotes(group);
      const rowNotes = [
        group.concurrency === trendConcurrency ? "viewer 收益递减提示" : null,
        configuredNotes.length ? `criteria annotation: ${configuredNotes.join(" · ")}` : null
      ].filter(Boolean);
      row.append(createCell(
        `C${group.concurrency}`,
        rowNotes.length ? `${status} · ${rowNotes.join(" · ")}` : status,
        rowNotes.length ? "cell-warn" : ""
      ));
      row.append(createCell(`${group.completeCount} / ${group.repetitionCount}`, group.trendEligible ? "complete" : "measurement gap", group.trendEligible ? "cell-good" : "cell-warn"));
      row.append(createCell(
        `${formatNumber(group.metrics.outputTps.median, 0)} tok/s`,
        formatRange(group.metrics.outputTps, value => formatNumber(value, 0))
      ));

      const marginal = group.marginal;
      row.append(createCell(
        marginal ? `${marginal.deltaThroughput >= 0 ? "+" : ""}${formatNumber(marginal.deltaThroughput, 0)} tok/s` : "基准点",
        marginal ? `${formatSignedPercent(marginal.throughputGrowth)} · ${formatNumber(marginal.slope, 1)} tok/s / ΔC${marginal.slopeRatio !== null ? ` · 初段 ${formatPercentValue(marginal.slopeRatio * 100, 0)}` : ""}` : "—",
        marginal && marginal.slopeRatio !== null && marginal.slopeRatio <= 0.65 ? "cell-warn" : ""
      ));
      row.append(createCell(formatMilliseconds(group.metrics.ttftP95Ms.median), formatRange(group.metrics.ttftP95Ms, formatMilliseconds)));
      row.append(createCell(formatMilliseconds(group.metrics.tpotP95Ms.median), formatRange(group.metrics.tpotP95Ms, formatMilliseconds)));
      row.append(createCell(formatMilliseconds(group.metrics.e2eP95Ms.median), formatRange(group.metrics.e2eP95Ms, formatMilliseconds)));
      row.append(createCell(
        `${formatNumber(group.metrics.maxWaiting.max, 1)} / ${formatPercentValue(group.metrics.kvPct.median, 3)}`,
        "max waiting / median KV peak"
      ));
      row.append(createCell(
        formatPercentValue(group.metrics.gpuAvgPct.median, 1),
        `avg median · max ${formatPercentValue(group.metrics.gpuMaxPct.max, 1)}`
      ));
      row.append(createCell(formatGiB(group.metrics.nvmlGiB.median), "driver allocation · not VRAM"));

      const failed = group.counts.failed ?? 0;
      const timeouts = group.counts.timeouts ?? 0;
      row.append(createCell(
        `${formatCount(group.counts.successful)} / ${formatCount(group.counts.requests)}`,
        `failed ${formatCount(failed)} · timeout ${formatCount(timeouts)}`,
        failed > 0 || timeouts > 0 ? "cell-bad" : "cell-good"
      ));
      row.addEventListener("click", () => selectGroup(group.concurrency, true));
      row.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectGroup(group.concurrency, true);
        }
      });
      body.append(row);
    }

    const incomplete = model.groups.filter(group => !group.trendEligible).map(group => `C${group.concurrency}`);
    setText(
      "comparisonCaption",
      model.groups.length
        ? `统计值由 cases[] 在浏览器端重算，只聚合 measurement_complete=true 的 repeat。${incomplete.length ? ` ${incomplete.join("、")} 含不完整 case，整点不参与趋势。` : " 所有测试档位均采集完整。"} min–max 是 repetition 范围，不是置信区间。`
        : "该 summary 没有 measured case；表格为空，lifecycle/context evidence 仍可查看。"
    );
  }

  function quantileCell(item, prefix) {
    const client = item.client;
    return ["p50", "p95", "p99"]
      .map(quantile => formatSecondsAsMs(getPath(client, [`${prefix}_${quantile}_seconds`])))
      .join(" / ");
  }

  function renderRepeatTable(group) {
    setText("repeatHeadingSub", `C${group.concurrency} · ${group.completeCount}/${group.repetitionCount} repeats 采集完整 · 分位数只基于成功请求`);
    const body = byId("repeatBody");
    body.replaceChildren();
    for (const item of group.cases) {
      const row = document.createElement("tr");
      if (item.measurement_complete !== true) row.classList.add("is-incomplete");
      const invalidReasons = Array.isArray(item.invalid_reasons)
        ? item.invalid_reasons.map(reason => String(reason)).join(" · ")
        : "";
      const caseId = typeof item.case_id === "string" ? item.case_id : `repeat ${item.repetition ?? "—"}`;
      row.append(createCell(caseId, invalidReasons || `repetition ${item.repetition ?? "—"}`, item.measurement_complete === true ? "" : "cell-warn"));

      const requests = getPath(item, ["client", "request_count"]);
      const success = getPath(item, ["client", "successful_requests"]);
      const failed = getPath(item, ["client", "failed_requests"]);
      const timeout = getPath(item, ["client", "timeout_requests"]);
      row.append(createCell(`${formatCount(success)} / ${formatCount(requests)}`, `failed ${formatCount(failed)} · timeout ${formatCount(timeout)}`, (failed ?? 0) > 0 || (timeout ?? 0) > 0 ? "cell-bad" : "cell-good"));
      row.append(createCell(quantileCell(item, "ttft"), `n=${formatCount(getPath(item, ["client", "ttft_sample_count"]))}`));
      row.append(createCell(quantileCell(item, "tpot"), `n=${formatCount(getPath(item, ["client", "tpot_sample_count"]))}`));
      row.append(createCell(quantileCell(item, "e2e"), `n=${formatCount(getPath(item, ["client", "e2e_sample_count"]))}`));
      row.append(createCell(`${formatNumber(getPath(item, ["client", "output_token_throughput_tps"]), 1)} tok/s`, `${formatNumber(getPath(item, ["client", "request_throughput_rps"]), 2)} req/s`));

      const running = getPath(item, ["runtime_samples", "max_running_requests"]);
      const waiting = getPath(item, ["runtime_samples", "max_waiting_requests"]);
      const kv = getPath(item, ["runtime_samples", "max_kv_cache_usage_ratio"]);
      const preemption = counterDelta(item, "preemption_events_total");
      row.append(createCell(`run ${formatNumber(running, 1)} · wait ${formatNumber(waiting, 1)}`, `KV ${formatRatio(kv, 3)} · preempt ${formatCount(preemption)}`));

      const queue = histogramMean(item, "queue_seconds");
      const prefill = histogramMean(item, "prefill_seconds");
      const decode = histogramMean(item, "decode_seconds");
      row.append(createCell(`queue ${formatSecondsAsMs(queue)}`, `prefill ${formatSecondsAsMs(prefill)} · decode ${formatSecondsAsMs(decode)}`));

      const nvml = getPath(item, ["system", "max_container_nvml_process_gpu_memory_used_bytes"]);
      const cgroup = getPath(item, ["system", "max_cgroup_memory_current_bytes"]);
      const hostAvailable = getPath(item, ["system", "min_host_memory_available_bytes"]);
      row.append(createCell(`NVML ${formatBytesAsGiB(nvml)}`, `cgroup ${formatBytesAsGiB(cgroup)} · host avail ${formatBytesAsGiB(hostAvailable)}`));

      const runtimeFailures = getPath(item, ["runtime_samples", "scrape_failure_count"]);
      const systemFailures = getPath(item, ["system", "sample_failure_count"]);
      row.append(createCell(item.measurement_complete === true ? "完整" : "不完整", `runtime ${formatCount(runtimeFailures)} · system ${formatCount(systemFailures)} failures`, item.measurement_complete === true ? "cell-good" : "cell-warn"));
      body.append(row);
    }
  }

  function createHealthRow(label, state, detail) {
    const row = createElement("div", `health-row ${state}`);
    row.append(createElement("span", "health-dot"));
    row.append(createElement("strong", "", label));
    row.append(createElement("span", "", detail));
    return row;
  }

  function renderEvidence() {
    const container = byId("rawValidationList");
    container.replaceChildren();
    const validation = model.health.rawValidation;
    const orderedKeys = [...Object.keys(RAW_LABELS), ...Object.keys(validation).filter(key => !(key in RAW_LABELS))];
    const uniqueKeys = [...new Set(orderedKeys)];
    for (const key of uniqueKeys) {
      const result = isObject(validation[key]) ? validation[key] : null;
      const valid = result?.valid === true ? true : result?.valid === false ? false : null;
      const count = finite(result?.record_count) ?? finite(model.health.rawRecordCounts[key]);
      const errorCount = Array.isArray(result?.errors) ? result.errors.length : null;
      const state = valid === true ? "good" : valid === false ? "bad" : "warn";
      const detail = valid === true
        ? `${formatCount(count)} records · valid`
        : valid === false ? `${formatCount(count)} records · ${formatCount(errorCount)} errors` : `${formatCount(count)} records · 未记录校验`;
      container.append(createHealthRow(RAW_LABELS[key] || key, state, detail));
    }
    if (!uniqueKeys.length) container.append(createHealthRow("Raw validation", "warn", "summary 未记录"));

    const list = byId("qualityIssueList");
    list.replaceChildren();
    const appendIssue = (text, state = "") => list.append(createElement("li", state, text));
    if (model.health.rawValidationPassed === true) {
      appendIssue("raw_validation_passed=true：四类 JSONL 结构校验通过；这不代表 benchmark 结论自动有效。", "good");
    } else if (model.health.rawValidationPassed === false) {
      appendIssue("raw_validation_passed=false：先检查 raw_validation.errors，再进行趋势解释。", "bad");
    } else {
      appendIssue("summary 未记录 raw_validation_passed，无法确认原始 JSONL 结构校验状态。");
    }

    if (model.health.incompleteCases > 0) {
      const ids = model.allCases
        .filter(item => item.measurement_complete !== true)
        .slice(0, 6)
        .map(item => typeof item.case_id === "string" ? item.case_id : `C${item.concurrency}`);
      appendIssue(`${model.health.incompleteCases} 个 case 采集不完整：${ids.join("、")}${model.health.incompleteCases > ids.length ? "…" : ""}。对应并发点不进入趋势曲线。`);
    } else {
      appendIssue(`${model.health.completeCases}/${model.health.totalCases} 个 case 的 measurement_complete=true。`, "good");
    }

    if ((model.health.failed ?? 0) > 0 || (model.health.timeouts ?? 0) > 0) {
      appendIssue(`请求结果包含 failed ${formatCount(model.health.failed)}、timeout ${formatCount(model.health.timeouts)}；它们被保留为边界证据。`, "bad");
    } else {
      appendIssue(`${formatCount(model.health.requests)} 个请求中未记录 failed / timeout。`, "good");
    }

    const samplerFailures = (model.health.runtimeSampleFailures ?? 0) + (model.health.systemSampleFailures ?? 0);
    appendIssue(
      samplerFailures > 0
        ? `采集器失败合计 ${formatCount(samplerFailures)}：runtime ${formatCount(model.health.runtimeSampleFailures)}、system ${formatCount(model.health.systemSampleFailures)}。`
        : "runtime / system case-window summary 未记录 sampler failure。",
      samplerFailures > 0 ? "" : "good"
    );

    const framebuffer = model.groups.reduce((total, group) => ({
      ok: total.ok + group.framebuffer.ok,
      unsupported: total.unsupported + group.framebuffer.unsupported,
      error: total.error + group.framebuffer.error,
      recorded: total.recorded || group.framebuffer.recorded
    }), { ok: 0, unsupported: 0, error: 0, recorded: false });
    if (framebuffer.recorded && framebuffer.unsupported > 0) {
      appendIssue(`GPU aggregate framebuffer telemetry 有 ${formatCount(framebuffer.unsupported)} 个 unsupported sample；页面显示“—”，不会解释为 0。`);
    } else if (!framebuffer.recorded) {
      appendIssue("该 schema 未记录 gpu_fb_memory_status_counts；framebuffer 聚合状态未知。 ");
    } else if (framebuffer.error > 0) {
      appendIssue(`GPU framebuffer telemetry 记录 ${formatCount(framebuffer.error)} 个 query error。`, "bad");
    } else {
      appendIssue("GPU framebuffer telemetry 状态已记录且未见 unsupported / error。", "good");
    }

    if ((model.prefix.median ?? 0) >= 0.9) {
      appendIssue(`Prefix-cache token hit 中位数为 ${formatRatio(model.prefix.median)}。当前 TTFT / input TPS 只适用于重复共享 prompt 与当前 cache 配置，不能外推 uncached prefill。`);
    }
    if (model.selectionAnalysis) {
      const indicatorCount = Array.isArray(model.selectionAnalysis.criteria.pressure_indicators)
        ? model.selectionAnalysis.criteria.pressure_indicators.length
        : 0;
      appendIssue(`summary 记录了 selection criteria 和 ${indicatorCount} 个 pressure indicator；命中只作 post-run annotation，不会触发停止或自动选择 C_eff / C_pressure。`, "good");
    }
    const boundaryStopConditions = model.context?.experiment?.boundary_policy?.stop_conditions;
    if (Array.isArray(boundaryStopConditions) && boundaryStopConditions.length) {
      const stopOnFailure = model.context?.configuration?.orchestration?.stop_on_failure;
      appendIssue(`declared boundary stop conditions：${boundaryStopConditions.join(" / ")}；stop_on_failure=${String(stopOnFailure)}。它们是请求/服务生命周期故障类别，不是性能指标规则。`);
    }
    const runWarnings = model.context?.run?.warnings;
    if (Array.isArray(runWarnings) && runWarnings.length) {
      appendIssue(`run warnings：${runWarnings.join(" / ")}。这些是 evidence/telemetry 缺口，不会被解释为 workload failure。`);
    }
    const shutdown = model.context?.observed_server?.shutdown;
    if (isObject(shutdown)) {
      appendIssue(`observed shutdown：OOMKilled=${shutdown.oom_killed ?? "unknown"} · restart_count=${shutdown.restart_count ?? "unknown"} · exit_code=${shutdown.container_exit_code ?? "unknown"}。`);
    }
    const configuration = model.context?.configuration;
    if (isObject(configuration)) {
      const modelConfig = isObject(configuration.model) ? configuration.model : {};
      const runtimeConfig = isObject(configuration.runtime) ? configuration.runtime : {};
      appendIssue(`summary context：model ${modelConfig.id ?? modelConfig.served_name ?? "—"} · revision ${modelConfig.artifact_revision ?? "—"} · image ${runtimeConfig.image ?? "—"}。fingerprint 仅用于跨 run 匹配与差异提示。`, "good");
    } else {
      appendIssue("summary 未记录自包含 context；跨 run 对比需要 companion run.yaml。 ");
    }
  }

  function populateControls() {
    const concurrencySelect = byId("selectedConcurrency");
    concurrencySelect.replaceChildren();
    for (const group of model.groups) {
      const option = document.createElement("option");
      option.value = String(group.concurrency);
      option.textContent = `C${group.concurrency}${group.trendEligible ? "" : " · 不完整"}`;
      concurrencySelect.append(option);
    }

    const fallback = model.analysis.trendStep?.current.concurrency
      ?? model.analysis.peak?.concurrency
      ?? model.groups.at(-1)?.concurrency
      ?? null;
    selectedConcurrencyValue = model.groups.some(group => group.concurrency === selectedConcurrencyValue)
      ? selectedConcurrencyValue
      : fallback;
    concurrencySelect.disabled = model.groups.length === 0;
    concurrencySelect.value = selectedConcurrencyValue === null ? "" : String(selectedConcurrencyValue);

    const memorySelect = byId("memoryMetric");
    const currentMemoryMetric = memorySelect.value;
    const hasMetric = key => model.analysis.points.some(group => finite(group.metrics[key]?.median) !== null);
    if (!hasMetric(currentMemoryMetric)) {
      const fallbackMemory = ["nvmlGiB", "cgroupCurrentGiB", "cgroupPeakGiB", "hostUsedGiB", "hostAvailableGiB", "gpuFbGiB"].find(hasMetric);
      if (fallbackMemory) memorySelect.value = fallbackMemory;
    }
  }

  function renderAll() {
    renderMeta();
    renderScopeNote();
    renderQualityBanner();
    renderKpis();
    renderInsights();
    populateControls();
    renderCharts();
    renderComparison();
    renderEvidence();
    renderSelectedGroup();
    byId("landing").hidden = true;
    byId("dashboard").hidden = false;
    byId("changeFileButton").hidden = IS_EMBEDDED;
    document.documentElement.dataset.viewerState = "loaded";
    window.__BENCHMARK_VIEWER_READY__ = true;
    window.__BENCHMARK_VIEWER_SUMMARY__ = {
      runId: model.runId,
      schemaVersion: model.schemaVersion,
      groups: model.groups.length,
      completeCases: model.health.completeCases,
      trendConcurrency: model.analysis.trendStep?.current.concurrency ?? null,
      capacityFailureConcurrency: model.analysis.failureGroup?.concurrency ?? null,
      selectionCriteria: model.selectionAnalysis !== null,
      boundaryStopConditions: model.context?.experiment?.boundary_policy?.stop_conditions ?? []
    };
    byId("embeddedStatus").hidden = true;
    window.__BENCHMARK_VIEWER_MODE__ = VIEWER_MODE;
    notifyHost("loaded", window.__BENCHMARK_VIEWER_SUMMARY__);
  }

  function showLoadError(error) {
    const message = error instanceof Error ? error.message : String(error);
    const box = byId("loadError");
    box.textContent = `无法读取 summary.json\n${message}`;
    box.hidden = false;
    byId("landing").hidden = false;
    byId("dashboard").hidden = true;
    byId("embeddedStatus").hidden = true;
    model = null;
    selectedConcurrencyValue = null;
    document.documentElement.dataset.viewerState = "error";
    window.__BENCHMARK_VIEWER_READY__ = false;
    window.__BENCHMARK_VIEWER_SUMMARY__ = null;
    notifyHost("error", {message});
  }

  function hideLoadError() {
    byId("loadError").hidden = true;
    byId("loadError").textContent = "";
    byId("landing").hidden = false;
    byId("dashboard").hidden = true;
    document.documentElement.dataset.viewerState = "loading";
    window.__BENCHMARK_VIEWER_READY__ = false;
    window.__BENCHMARK_VIEWER_SUMMARY__ = null;
    if (IS_EMBEDDED) {
      byId("embeddedStatus").textContent = "正在加载 summary.json…";
      byId("embeddedStatus").hidden = false;
    }
  }

  function loadJsonText(text, sourceName) {
    let data;
    try {
      data = JSON.parse(text);
    } catch (error) {
      throw new Error(`JSON 解析失败：${error.message}`);
    }
    model = validateAndNormalize(data, sourceName);
    selectedConcurrencyValue = null;
    renderAll();
  }

  async function loadFile(file) {
    if (!file) return;
    hideLoadError();
    if (file.size > MAX_FILE_BYTES) {
      showLoadError(new Error(`文件大于 ${MAX_FILE_BYTES / 1024 / 1024} MiB；请选择 derived/summary.json，而不是 request-level raw JSONL。`));
      return;
    }
    try {
      loadJsonText(await file.text(), file.name);
    } catch (error) {
      showLoadError(error);
    }
  }

  async function loadQuerySource() {
    const source = QUERY.get("src");
    if (!source) {
      if (IS_EMBEDDED) {
        showLoadError(new Error("embedded 模式需要有效的 ?src=summary.json。"));
      }
      return;
    }
    try {
      if (window.location.protocol === "file:") {
        throw new Error(IS_EMBEDDED
          ? "embedded ?src 需要同源 HTTP(S) 页面；file:// 不支持嵌入加载。"
          : "?src 需要同源 HTTP(S)；file:// 请移除 ?src 后使用文件选择。");
      }
      const url = new URL(source, window.location.href);
      if (url.origin !== window.location.origin) {
        throw new Error("?src 仅允许同源地址，避免意外读取外部数据。 ");
      }
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw new Error(`读取 ${url.pathname} 返回 HTTP ${response.status}。`);
      const contentLength = Number(response.headers.get("content-length"));
      if (Number.isFinite(contentLength) && contentLength > MAX_FILE_BYTES) {
        throw new Error(`远程文件大于 ${MAX_FILE_BYTES / 1024 / 1024} MiB。`);
      }
      const text = await response.text();
      if (new TextEncoder().encode(text).byteLength > MAX_FILE_BYTES) {
        throw new Error(`远程文件大于 ${MAX_FILE_BYTES / 1024 / 1024} MiB。`);
      }
      loadJsonText(text, url.pathname.split("/").at(-1) || "summary.json");
    } catch (error) {
      showLoadError(error);
    }
  }

  function setupEvents() {
    const dropzone = byId("dropzone");
    const fileInput = byId("fileInput");
    const chooseFile = () => fileInput.click();
    dropzone.addEventListener("click", chooseFile);
    dropzone.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        chooseFile();
      }
    });
    fileInput.addEventListener("change", async event => {
      await loadFile(event.target.files?.[0]);
      event.target.value = "";
    });
    byId("changeFileButton").addEventListener("click", chooseFile);

    for (const eventName of ["dragenter", "dragover"]) {
      dropzone.addEventListener(eventName, event => {
        event.preventDefault();
        dropzone.classList.add("is-dragging");
      });
    }
    for (const eventName of ["dragleave", "drop"]) {
      dropzone.addEventListener(eventName, event => {
        event.preventDefault();
        dropzone.classList.remove("is-dragging");
      });
    }
    dropzone.addEventListener("drop", event => loadFile(event.dataTransfer?.files?.[0]));

    byId("throughputMetric").addEventListener("change", renderCharts);
    byId("latencyMetric").addEventListener("change", renderCharts);
    byId("memoryMetric").addEventListener("change", renderCharts);
    byId("selectedConcurrency").addEventListener("change", event => selectGroup(Number(event.target.value)));
  }

  window.__BENCHMARK_VIEWER_MODE__ = VIEWER_MODE;
  document.documentElement.dataset.viewerState = IS_EMBEDDED || QUERY.has("src") ? "loading" : "idle";
  window.__BENCHMARK_VIEWER_READY__ = false;
  window.__BENCHMARK_VIEWER_SUMMARY__ = null;
  setupEvents();
  loadQuerySource();
})();
