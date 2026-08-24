# M2 Review

## M2.0 — Compatibility inventory

| Feature | 分类 | 证据 |
|---|---|---|
| APC | `supported` | [run](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-apc/run.yaml) · [summary](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-apc/derived/summary.json) |
| FP8 KV cache | `supported` | [run](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-kv-fp8/run.yaml) · [log](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-kv-fp8/raw/server/server.log) |
| Online FP8 weight | `supported` | [run](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-w-fp8/run.yaml) · [log](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-w-fp8/raw/server/server.log) |
| Draft speculative | Qwen2.5 `startup_failed`；Qwen3 `supported` | [failure](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-draft-speculative-qwen2.5/raw/server/server.log) · [success](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-draft-speculative-qwen3/run.yaml) · [summary](../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-draft-speculative-qwen3/derived/summary.json) |

**Observed Fact：** 4 个 supported run 各完成 8/8 measured requests；public summaries 保留 APC query/hit counter、prefill histogram 与 Qwen3 drafted/accepted token counter。private raw exposition 的 HELP 将 query/hit 定义为 token counter，Tier A 未保留该 HELP line。

**Interpretation / 限制：** APC telemetry 满足 M2.1 前置条件；其余只证明 pinned runtime 下的 compatibility，不证明性能或质量。

## M2.1 — Prefix-cache canonical comparison

**结论（Interpretation）：** 在固定 prefix-heavy workload 的 C1/C16 canonical A/B 中，run-shared candidate 的 token hit、prefill、TTFT 与 waiting 读数共同支持“prefix reuse 减少 measured prefill 工作”的解释。C16 确认了 bounded concurrency 下的机制收益，但不是 capacity、`C_eff` 或全局最优点。

证据：[control summary](../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-apc-baseline-7b-canonical/derived/summary.json) · [candidate summary](../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-apc-candidate-7b-canonical/derived/summary.json) · [comparison](../../showcase/m2/compare.html?study=m2.1-prefix-cache-canonical&c=16)

| C | Hit ratio control→candidate | Uncached prefill tok/req | TTFT p95 | Prefill mean | Max waiting |
|---:|---:|---:|---:|---:|---:|
| 1 | 0% → 98.746% | 1037 → 13 | 0.267 → 0.145 s | 0.185 → 0.067 s | 0 → 0 |
| 16 | 0% → 98.746% | 1037 → 13 | 3.175 → 0.244 s | 0.862 → 0.144 s | 9 → 0 |

**Observed Fact：** 两侧均在 fresh runtime 上完成 C1/C16 × 3 repetitions；各 6/6 cases 完整、96/96 requests 成功且 raw validation passed。对应请求的 input tokens 全部匹配，public summaries 保留 query/hit counter delta 与 derived hit ratio。

**Observed Fact：** C1 的 E2E p95 median 为 4.291→4.961 秒，没有观测到端到端收益。96 对请求中有 17 对 output token 数不同，因此 throughput、TPOT 与 E2E 的归因弱于 counter、prefill 和 TTFT。

**范围与执行缺口：**

- Priming-inclusive 成本尚未物化，公开投影也未保留 warm-up evidence，因此当前不发布成本结论。
- 性能 run 不保存输出文本；结果不能用于输出质量结论，也不能外推到其他 prompt 或实际 hit-rate 分布。

## M2.2 — Quantization canonical comparison（draft）

**结论（Interpretation）：** 在 pinned runtime 与 C1 workload 下，FP8 KV 将 runtime 报告的 KV capacity 提高约 92.7%，但冻结质量集出现负向 flip，不能视为透明替代；online FP8 weight 的 decode 指标改善，4-case 质量集未观测到 flip。后者的 runtime 实际为 FP8 weight、`activation=None`、BF16 compute 与 KV auto，不是已验证的 W8A8；两组结果均不外推为全局性能或质量结论。

证据：

- KV：[baseline summary](../../artifacts/private/m2/20260823-m2-quant-output-kv-baseline-canonical/derived/summary.json) · [candidate summary](../../artifacts/private/m2/20260823-m2-quant-output-kv-candidate-canonical/derived/summary.json) · [baseline output](../../artifacts/private/m2/20260823-m2-quant-output-kv-baseline-canonical/derived/output-evaluation-summary.json) · [candidate output](../../artifacts/private/m2/20260823-m2-quant-output-kv-candidate-canonical/derived/output-evaluation-summary.json) · [baseline runtime](../../artifacts/private/m2/20260823-m2-quant-output-kv-baseline-canonical/raw/server/server.log) · [candidate runtime](../../artifacts/private/m2/20260823-m2-quant-output-kv-candidate-canonical/raw/server/server.log)
- Weight：[baseline summary](../../artifacts/private/m2/20260823-m2-quant-output-weight-baseline-canonical/derived/summary.json) · [candidate summary](../../artifacts/private/m2/20260823-m2-quant-output-weight-candidate-canonical/derived/summary.json) · [baseline output](../../artifacts/private/m2/20260823-m2-quant-output-weight-baseline-canonical/derived/output-evaluation-summary.json) · [candidate output](../../artifacts/private/m2/20260823-m2-quant-output-weight-candidate-canonical/derived/output-evaluation-summary.json) · [baseline runtime](../../artifacts/private/m2/20260823-m2-quant-output-weight-baseline-canonical/raw/server/server.log) · [candidate runtime](../../artifacts/private/m2/20260823-m2-quant-output-weight-candidate-canonical/raw/server/server.log)

| Axis | Strict quality baseline→candidate | C1 median / runtime capacity baseline→candidate |
|---|---:|---|
| BF16 weight + FP8 KV | 3/4 → 2/4 | KV capacity 254,384 → 490,224 tokens；TTFT p95 265.42 → 273.59 ms；TPOT p95 74.77 → 76.57 ms |
| Online FP8 weight | 3/4 → 3/4 | Output TPS 13.096 → 27.477；TPOT p95 76.38 → 36.38 ms；KV capacity 248,288 → 369,584 tokens |

**Observed Fact：** 四条 canonical run 均使用 fresh runtime，完成 C1 × 3 repetitions；每条 24/24 measured requests 成功、raw validation passed、lifecycle graceful。四份 frozen case 文件相同，均捕获 4/4 case、0 request error；主 summary 与 output-evaluation summary 可从 raw 重算，A/B frozen config 除 metadata 与预声明 axis 外一致。

**Observed Fact：** FP8 KV 的 `long-01` 为 `true→false`，candidate 输出出现重复乱码。`format-01` 在四侧的 strict `json_exact` 都为 false；KV baseline 与 weight 两侧只是合法 JSON 外包 Markdown fence，KV candidate 的 fence 内部也已损坏。

**Secondary diagnostic（post-hoc，不替代 canonical primary）：** 若只剥除一层完整 Markdown fence 后再严格解析 JSON，KV pair 为 4/4 → 2/4，weight pair 为 4/4 → 4/4。当前 `json_exact` 仍按完整响应解析，canonical correct 值不改写；没有预声明质量阈值，因此这里只报告变化，不判定“可接受”或“不可接受”。

**范围与执行缺口：**

- 性能证据只有 C1 canonical，未执行 checklist 中的额外 bounded exploratory 点；不据此声称并发收益、capacity 点或全局最优。
- KV pair 的 measured output tokens 为 1,200 → 1,483，E2E 与 request/output throughput 不能作干净 A/B 归因；TTFT、TPOT 只作为该有界请求集的观测。
- 质量结论仅覆盖固定 4 cases；`long-01` 约为 957 chat-template tokens，只代表约 1K retrieval case，不代表 8K long-context accuracy。
