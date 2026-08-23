# M2 — Serving 优化实验（执行计划）

> 该文档为 M2 的执行顺序、实验约束和停手条件。范围、工时与 Exit Criteria 见 [Roadmap](../Roadmap.md)，当前进度见 [current-status](../context/current-status.md)，实验结论见 [M2 review](../reviews/m2-review.md)。
> 预算 ≤ 150 行。

## 研究

M2 分别研究prefix caching、量化和speculative decoding：它们能节省多少 prefill、计算或内存，又会带来哪些兼容性、输出质量或额外开销？

长上下文只做边界检查：观察实际输入变长后 TTFT、KV cache 和统一内存的变化，不把 `max_model_len` 配置值当成已经验证的上下文能力。

## 执行顺序

```text
M2.0 兼容性检查
  → M2.1 prefix caching hit / miss A/B
  → M2.2 量化：兼容性 → 输出检查 → 性能 A/B
  → M2.3 speculative decoding：兼容性 → 场景选择 → 性能 A/B
  → M2.4 长上下文边界检查
  → 重算 derived → 选择代表性证据 → 更新 review 和 showcase
```

M2.1–M2.3 都按 `smoke → exploratory → canonical` 执行。Smoke 只检查流程能否跑通；exploratory 只选择少量测试点；canonical 固定配置运行 3 次。不要展开全参数组合。

## 所有实验共同遵守的规则

1. 使用 M1 冻结的 vLLM image digest 和 Spark A；每个 server config 都启动新的 runtime，并使用独立 run ID。
2. 除speculative decoding外，Qwen2.5-7B 是默认 target。speculative decoding使用 M2.0 选出的兼容组合，并为实际 target 单独重跑 baseline。
3. 每组 A/B 都在 M2 内重跑 baseline；M1 结果只能作为背景，不能与 M2 candidate 组成因果比较。
4. A/B 只改变预先声明的实验因素。模型、prompt、sampling、请求顺序和对应请求的输入 token 必须一致。
5. 主要读数是 client 侧 TTFT、TPOT、E2E、吞吐和失败数；runtime counter 与 histogram 用来确认机制是否实际生效。
6. Readiness failure、timeout、OOM、restart 和 non-zero exit 都保留。失败后使用新 run ID，不覆盖原目录。
7. `revision`、fingerprint 和 `cache_salt` 是描述与对齐信息，不是运行许可。
8. `/metrics` 中没有所需 metric 时，记录为 telemetry 缺口；不要从日志推算不存在的 counter。
9. 性能请求不保存输出文本。只有配置了输出检查时，才把输入、输出和评分保存在私有 raw 中。

## M2.0 — 兼容性检查

1. 分别检查 APC、FP8 KV cache、online FP8 weight 和 draft-model speculative decoding；每个配置只启用一项待测能力。
2. 每项都保留 frozen config、完整命令、readiness、server log、原始 `/metrics`、request JSONL、final state 和可重算 summary。
3. 只使用 `supported`、`startup_failed`、`model_asset_missing` 和 `telemetry_unsupported` 分类。APC 必须完成请求，并提供单位明确的 prefix query/hit counter，才能进入 M2.1。结果见 [M2 review](../reviews/m2-review.md)。

## M2.1 — Prefix caching hit / miss A/B

> 大量请求共享同一段长前缀时，缓存命中能否减少 prefill token，并降低 TTFT 和单位请求成本？

1. 构造 prefix-heavy NPC workload：长且固定的 instruction、世界设定和角色记忆，加一个短的 request-specific suffix，输出保持较短。
2. 两侧都启用 APC，并保持 prompt、suffix 规则、warm-up、请求数和并发顺序相同。唯一差异是 cache identity：
   - `miss-control`：每个请求使用不同的 `cache_salt`；
   - `hit-candidate`：同一 run 的 warm-up 和 measured request 共享 `cache_salt`，由 warm-up 先填充缓存。
3. 先用 0.5B / C1 smoke 检查 prompt、salt、请求完整性和 counter。Candidate 没有产生更高的实际 hit ratio 时，不进入 7B。
4. 7B exploratory 只测试 C1 和 M1 已验证范围内的少量并发点，再选择一个双方都完整的非 C1 点。
5. Canonical 只保留 C1 与该非 C1 点，每侧运行 3 次；冻结后不再修改 workload。
6. 比较 TTFT p50/p95、prefill time、prefix query/hit token、prompt throughput 和失败数。设计上允许复用，不等于 runtime 已经命中，必须以 counter 为准。
7. Counter 单位确认为 token 后，才计算 `uncached prefill tokens/request` 和 `allocated GPU-s/1M logical prompt tokens`。
8. 分开报告不含 priming 的 measured 结果，以及把一次 priming 分摊进去的结果。Allocated GPU-seconds 是资源占用口径，不是实际能耗。

## M2.2 — Quantization 与输出检查

> KV cache 和权重量化分别能节省多少资源，这些变化是否伴随输出退化？

1. 按顺序测试：
   - baseline：BF16 weight + BF16 KV；
   - candidate A：BF16 weight + FP8 KV；
   - candidate B：online FP8 weight，实际 weight/activation dtype 以 runtime log 为准。
2. 若 runtime 强制同时改变 weight 与 KV dtype，只比较整套配置，不分别归因。
3. 先做兼容性 smoke，再做输出检查；通过这两步的候选才进入性能 A/B。
4. 输出检查使用冻结的本地 JSONL prompt set，覆盖短指令、事实抽取、格式约束和长上下文检索。`temperature=0`，只使用 `normalized_exact` 和 `json_exact` 二元评分。
5. 保存每题输出、评分和 baseline/candidate flip；报告总分变化。没有预先声明阈值时，不自动写成“可接受”或“不可接受”。
6. FP8 KV 重点观察长输入下的 KV capacity、TTFT 和内存；online FP8 weight 重点观察 short-long workload 的 TPOT、output TPS 和内存。
7. 内存结论联合使用 runtime KV capacity、container cgroup、container 对应的 NVML process allocation 和 host `MemAvailable`。不把缺失的 framebuffer telemetry 当成 0。
8. FP8 不可用时再测试 INT4 AWQ/GPTQ；仍不可用就记录兼容性边界，不继续扩展量化路径。

## M2.3 — Speculative Decoding

> Speculative Decoding 只有在节省的 target 解码时间大于 draft 推理和 token 验证开销时才有收益。本step要找出它何时更快、何时反而更慢。

1. 根据 [M2 review](../reviews/m2-review.md) 选择已通过兼容性检查的 model pair。Baseline 与 candidate 使用相同 target；candidate 只增加 speculative 配置及 backend 必需的变化。
2. 若 model-based 路径不可比较，改用 Qwen2.5-7B 的 n-gram 路径。EAGLE 只在已有兼容资产时使用，不新增训练工作。
3. 固定两个场景：decode-heavy、低并发场景用于验证可能的正收益；短输出或较高并发场景用于寻找无收益或负收益边界。
4. 从原始 `/metrics` 确认 drafted/accepted token counter 后，再加入最小 metric mapping。
5. 报告 acceptance rate、mean accepted tokens/draft、TTFT、TPOT、output TPS 和失败数。Acceptance rate 只能说明草稿命中程度，不能单独证明端到端收益。
6. Deterministic 请求还要比较 normalized output。若输出不同，先检查模型、tokenizer 和 sampling 是否一致，再判断 A/B 是否可比较。
7. Backend 若自动切换 scheduler、model runner 或其他执行路径，把它列为必要的配置差异；无法隔离时只报告整套配置结果。

## M2.4 — 长上下文边界检查

> 实际输入越来越长时，TTFT、KV cache 和统一内存在哪个范围开始出现明显压力或运行失败？

1. 先用 `max_model_len` OVAT 找到能够启动的范围，但不把启动成功当成长上下文请求成功。
2. 在 C1 下最多选择 3 个实际 prompt length，每点运行一次 exploratory。
3. 记录实际 input token、TTFT、prefill time、KV usage、统一内存和 outcome。
4. 出现首个 readiness、client、OOM 或 restart 失败后停止上探并保留证据；不外推未测试长度，也不用单次运行声明 tail latency。
5. 本项不做长上下文准确率、RoPE scaling 或新的质量评测框架。

## 收尾

1. 所有 `derived/` 必须能从 raw 和 frozen config 重算。
2. 只有实验条件一致的 A/B 才做对照；条件不同的 run 只能并列展示。
3. 完整 private run 按 [evidence retention](../experiments/evidence-retention.md) 保留，只投影足以支撑核心结论的代表性结果。
4. Observed Fact 指向具体 raw/derived；Interpretation 与 Hypothesis 必须明确标出。
5. Showcase 复用已有 comparison / run analysis 页面，不增加新的通用 UI 或 x-axis。

## 不做

不做 Chunked prefill、CUDA graph A/B、Nsight/kernel profiling、跨节点 TP、SGLang 对比、自动参数搜索、全局 accuracy framework、M2 专属 runner/evidence framework，也不为 M2 新建展示 UI。
