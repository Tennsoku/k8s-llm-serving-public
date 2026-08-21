"use strict";

import {CORE_METRICS, startComparison} from "../shared/compare-app.js";

const metricIds = CORE_METRICS.map(metric => metric.id);
const policyContracts = {
  runtime_ovat_v1: {
    candidateExperimentKind: "ovat",
    metricSet: "m1_core_v1",
    metricIds,
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
    metricIds,
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

startComparison({
  metrics: CORE_METRICS,
  policyContracts,
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
    "/workload/cache_identity/mode",
    "/sampling/stream",
    "/sampling/temperature",
    "/sampling/seed"
  ]
});
