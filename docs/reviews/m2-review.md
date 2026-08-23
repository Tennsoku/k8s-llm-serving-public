# M2 Review

## M2.0 — Compatibility inventory

| Feature | 分类 | 证据 |
|---|---|---|
| APC | `supported` | [run](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-apc/run.yaml) · [summary](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-apc/derived/summary.json) |
| FP8 KV cache | `supported` | [run](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-kv-fp8/run.yaml) · [log](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-kv-fp8/raw/server/server.log) |
| Online FP8 weight | `supported` | [run](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-w-fp8/run.yaml) · [log](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-w-fp8/raw/server/server.log) |
| Draft speculative | Qwen2.5 `startup_failed`；Qwen3 `supported` | [failure](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-draft-speculative-qwen2.5/raw/server/server.log) · [success](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-draft-speculative-qwen3/run.yaml) · [summary](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-draft-speculative-qwen3/derived/summary.json) |

**Observed Fact：** 4 个 supported run 各完成 8/8 measured requests；APC metrics 将 query/hit 定义为 token counter，并提供 prefill histogram；Qwen3 暴露 drafted/accepted token counter。

**Interpretation / 限制：** APC telemetry 满足 M2.1 前置条件；其余只证明 pinned runtime 下的 compatibility，不证明性能或质量。

## M2.1 — Prefix-cache exploratory selection

**结论（Interpretation）：** 在固定 prefix-heavy workload 中，run-shared candidate 的 token hit、prefill 与 TTFT 读数共同支持“prefix reuse 减少 measured prefill 工作”的解释。C16 是双方完整且 pressure 分离最明显的 tested point，建议作为下一轮 bounded canonical 非 C1 选点；它不是 capacity、`C_eff` 或全局最优点。

证据：[control summary](../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-apc-baseline-7b-exp/derived/summary.json) · [candidate summary](../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-apc-candidate-7b-exp/derived/summary.json) · [comparison](../../showcase/m2/compare.html?study=m2.1-prefix-cache-exploratory&c=16)

| C | Hit ratio control→candidate | Uncached prefill tok/req | TTFT p95 | Prefill mean | Max waiting |
|---:|---:|---:|---:|---:|---:|
| 1 | 0% → 98.746% | 1037 → 13 | 0.270 → 0.148 s | 0.190 → 0.067 s | 0 → 0 |
| 8 | 0% → 98.746% | 1037 → 13 | 1.557 → 0.227 s | 0.724 → 0.135 s | 3 → 0 |
| 16 | 0% → 98.746% | 1037 → 13 | 3.197 → 0.244 s | 0.867 → 0.145 s | 7.5 → 0 |

**Observed Fact：** 两侧均在 fresh runtime 上完成 C1/C8/C16 × 4 repetitions；各 12/12 cases 完整、192/192 requests 成功且 raw validation passed。对应请求的 input tokens 全部匹配，Prometheus `HELP` 将 prefix query/hit 定义为 token counter。

**Observed Fact：** C1 的 E2E p95 median 为 4.304→4.921 秒，没有观测到端到端收益。192 对请求中有 21 对 output token 数不同，因此 throughput、TPOT 与 E2E 的归因弱于 counter、prefill 和 TTFT。

**Hypothesis：** 冻结 C1+C16 并按 canonical contract 每侧运行 3 repetitions 后，高 hit ratio 与 TTFT/prefill 分离仍可复现。验证时使用 fresh runtime，并同时计算 post-priming 与含一次 priming 的 allocated GPU-s/1M logical prompt tokens。

**范围与执行缺口：**

- 当前只有 exploratory pair，canonical 尚未执行；不得发布 canonical stability 或 capacity 结论。
- Priming-inclusive 成本尚未物化，公开投影也未保留 warm-up evidence，因此当前不发布成本结论。
- 性能 run 不保存输出文本；结果不能用于输出质量结论，也不能外推到其他 prompt 或实际 hit-rate 分布。
