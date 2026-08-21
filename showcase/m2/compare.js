"use strict";

import {
  CORE_METRICS, formatNumber, formatSigned, startComparison
} from "../shared/compare-app.js";

function validCounterDelta(item, semantic) {
  const counter = item.runtime_counters?.[semantic];
  return counter?.valid === true ? counter.delta : null;
}

const prefixMetrics = [
  {
    id: "prefix_cache_token_hit_ratio",
    label: "Prefix cache token hit ratio",
    note: "case ratio · complete-repetition median",
    aggregateKey: null,
    caseValue: item => item.prefix_cache_token_hit_ratio,
    format: value => formatNumber(value * 100, 2) + "%",
    delta: value => formatSigned(value * 100, 2) + " pp"
  },
  {
    id: "prefix_cache_queries_total_delta",
    label: "Prefix cache query counter delta",
    note: "runtime counter · repetition median",
    aggregateKey: null,
    caseValue: item => validCounterDelta(item, "prefix_cache_queries_total"),
    format: value => formatNumber(value, 0),
    delta: value => formatSigned(value, 0)
  },
  {
    id: "prefix_cache_hits_total_delta",
    label: "Prefix cache hit counter delta",
    note: "runtime counter · repetition median",
    aggregateKey: null,
    caseValue: item => validCounterDelta(item, "prefix_cache_hits_total"),
    format: value => formatNumber(value, 0),
    delta: value => formatSigned(value, 0)
  },
  {
    id: "ttft_p50_seconds",
    label: "TTFT P50",
    note: "client-observed latency",
    aggregateKey: null,
    caseValue: item => item.client?.ttft_p50_seconds,
    format: value => formatNumber(value * 1000, 1) + " ms",
    delta: value => formatSigned(value * 1000, 1) + " ms"
  },
  {
    id: "server_prefill_mean_seconds",
    label: "Server mean prefill time",
    note: "server histogram mean · repetition median",
    aggregateKey: null,
    caseValue: item => item.server_histograms?.prefill_seconds?.valid === true
      ? item.server_histograms.prefill_seconds.mean
      : null,
    format: value => formatNumber(value * 1000, 1) + " ms",
    delta: value => formatSigned(value * 1000, 1) + " ms"
  },
  {
    id: "server_prompt_throughput_tps",
    label: "Server prompt throughput",
    note: "counter delta / case wall time · repetition median",
    aggregateKey: null,
    caseValue: item => item.server_prompt_throughput_tps,
    format: value => formatNumber(value, 1) + " tok/s",
    delta: value => formatSigned(value, 1) + " tok/s"
  }
];
const metrics = [...CORE_METRICS, ...prefixMetrics];
const coreMetricIds = CORE_METRICS.map(metric => metric.id);
const prefixMetricIds = metrics.map(metric => metric.id);

startComparison({
  metrics,
  policyContracts: {
    m2_prefix_cache_v1: {
      candidateExperimentKind: "canonical",
      metricSet: "m2_prefix_cache_v1",
      metricIds: prefixMetricIds,
      axes: {
        "workload.cache_identity": {
          label: "Prefix cache identity",
          paths: [
            "/workload/cache_identity/mode",
            "/workload/cache_identity/derivation"
          ]
        }
      }
    },
    m2_quantization_v1: {
      candidateExperimentKind: "canonical",
      metricSet: "m2_quantization_v1",
      metricIds: coreMetricIds,
      axes: {
        "runtime.kv_cache_dtype": {
          label: "KV cache dtype",
          paths: ["/runtime/extra_args"]
        },
        "runtime.weight_quantization": {
          label: "Weight quantization",
          paths: ["/runtime/quantization"]
        },
        "runtime.weight_and_kv_quantization": {
          label: "Weight and KV quantization",
          paths: ["/runtime/quantization", "/runtime/extra_args"]
        }
      }
    },
    m2_speculative_decoding_v1: {
      candidateExperimentKind: "canonical",
      metricSet: "m2_speculative_v1",
      metricIds: coreMetricIds,
      axes: {
        "runtime.speculative_decoding": {
          label: "Speculative decoding",
          paths: ["/runtime/extra_args"]
        }
      }
    }
  },
  matchedContextPaths: [
    "/model/id",
    "/model/artifact_revision",
    "/runtime/image",
    "/runtime/dtype",
    "/runtime/generation_config",
    "/workload/shape",
    "/workload/input_tokens_target",
    "/workload/max_output_tokens",
    "/workload/prompt_sha256",
    "/sampling/stream",
    "/sampling/temperature",
    "/sampling/seed"
  ]
});
