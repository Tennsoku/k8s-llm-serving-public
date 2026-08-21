# M2 — Serving 优化实验室（执行计划，draft）

> 本文只定义 M2 的**执行顺序、实验 contract 与停手边界**；范围、工时和 Exit Criteria 只见 [Roadmap](../Roadmap.md)，当前进度只见 [current-status](../context/current-status.md)。
> 结果数据进入 benchmark / showcase，结论、限制与 unknowns 进入 `docs/reviews/m2-review.md`；本文不复制状态或结果。预算 ≤ 150 行。

---
## 交付物
| 类别 | 产出 |
|---|---|
| 实验配置 | `benchmarks/configs/vllm-single-node/m2/` — prefix cache、quantization、speculative decoding、long-context 的 versioned config |
| 工程增量 | 只在现有 `serving/vllm/` pipeline 中补 shared cache identity、deterministic suffix、可选 output evaluator、实际观测到的 metric 语义与最小测试；不另建 M2 runner |
| 原始证据 | `artifacts/private/m2/<run-id>/` 保存完整 run；代表性 canonical run 投影到 `benchmarks/raw-results/m2-serving-optimization/` |
| 结论 | `docs/reviews/m2-review.md`；`showcase/m2/` 保存 M2 contract 并复用 `showcase/shared/` 渲染器，不新建 UI |

---
## M2 要回答的问题

在固定 runtime、模型、workload 和测量边界下，**prefix reuse、量化与 speculative decoding 分别在什么条件下改善 TTFT、TPOT、吞吐、内存或成本；收益以什么质量、兼容性或额外开销为代价？**

长上下文只做 bounded boundary：确认实际输入长度上升时 KV 占用与 TTFT 如何变化，不把 `max_model_len` 配置值本身误写成已验证的上下文能力。

---
## 执行序列

```text
M2.0 冻结输入与 feature smoke
  → M2.1 prefix-cache hit/miss A/B
  → M2.2 quantization：兼容性 → 精度 → 性能
  → M2.3 speculative decoding：兼容性 → 正收益 hypothesis → 负收益边界
  → M2.4 long-context bounded checkpoint
  → 重算 derived → 选代表性证据 → review / comparison view → close
```

对照型工作包 M2.1–M2.3 遵循 `机制问题 → hypothesis → smoke → exploratory 选点 → canonical A/B → review`；M2.4 只做 bounded single-run checkpoints。**不先展开 Cartesian matrix**。学习组织约按 6:4 分配给机制/实验解释与实现/执行，M2.1–M2.4 分别使用独立 thread。

---
## 固定实验 contract

| 项 | 约束 |
|---|---|
| Runtime | 使用 M1 冻结的 digest-pinned NGC vLLM 镜像与 Spark A；每项 feature 先确认实际 flag、模型资产和 `/metrics` 支持；每个 server config 使用 fresh runtime 与独立 run directory |
| 模型 | Qwen2.5-7B 为主要 target；Qwen2.5-0.5B 只作 pipeline smoke 或 speculative draft。若 7B 在时限内不可执行，降级必须写清结论范围 |
| 基线 | 每个 M2 A/B 都在 M2 内重跑 baseline；M1 数据只作 prior，不与新 candidate 混成 causal comparison |
| 受控变量 | 一次只改变一个声明 axis；若 backend 强制同时改变 weight/KV dtype，标为 descriptive comparison，不拆分归因 |
| 运行等级 | smoke 验证端到端；exploratory 验证兼容性与选点；canonical 固定配置重复 3 次并保留 request-level evidence |
| 请求 | 固定 prompt corpus、generation config、sampling 与请求顺序；默认 deterministic decoding。A/B 的逻辑输入 token 必须一致；性能 request 不保存文本，只有配置 `output_evaluation` 时才另采逐题输出 |
| 指标 | client-observed TTFT/E2E/TPOT 与 token throughput 为主；runtime counter/histogram 为机制证据；统一内存按既有 cgroup/NVML/host 信号解释 |
| 失败 | readiness、timeout、OOM、restart、non-zero exit 全部保留；同一 run 中不静默 fallback。fallback 使用新 config、新 run-id |
| 表述 | metric 不存在是 telemetry 缺口，不写成 `Unknown`；只有完成声明范围测试但无直接证据时才使用 `Unknown` |

---
## M2.0 — 输入冻结与 compatibility inventory

1. 从 M1 的 7B short-long config 派生最小 smoke；冻结 image digest、model revision、tokenizer、dtype、generation config 与 sampler interval。
2. 分别启动 APC、FP8 KV cache、weight FP8、draft-model speculative decoding，保存 expanded command、readiness、server log 和原始 `/metrics` exposition。
3. 只把**实际出现**且 M2 结论需要的 metric 加入 `metrics_utils.py`；metric 缺失时保留 exposition，不从日志猜测 counter。
4. 记录 feature matrix：`supported / startup_failed / model_asset_missing / telemetry_unsupported`。关键 telemetry 缺失时保留执行证据、标记对应 Exit Criterion 未满足，并回到 Roadmap 决定范围，不以 `Unknown` close。

---
## M2.1 — Prefix cache hit vs miss A/B

**机制问题**：共享 prefix 的完整 KV block 可复用时，prefill 工作量减少能否稳定反映到 TTFT 与 allocated GPU-seconds；并发是否改变收益。

1. 构造一个面向角色扮演 / 智能 NPC 的 prefix-heavy workload：共享 system prompt + 固定世界设定/角色记忆 + 短 unique user suffix + 短输出。
2. 两组使用完全相同的 shared prefix、deterministic per-request suffix 和数量相同的未计入测量 warm-up，并各自使用 fresh runtime：
   - `miss-control`：`request_unique` identity，warm-up 与测量请求使用 request-unique `cache_salt`；
   - `hit-candidate`：`run_shared` identity，同一 run 的 warm-up 与测量共享 `cache_salt`，由 warm-up/priming request 填充 prefix。
3. 先以 0.5B/C1 做 pipeline smoke；canonical 优先使用 7B，在 C1 与一个 exploratory 选出的 bounded concurrent point 运行，7B 并发上探不超过 M1 已验证范围。
4. 预声明比较：TTFT p50/p95、server prefill time、prefix-cache hit/query counter delta、prompt throughput、失败数；counter 单位必须由 pinned runtime 的 HELP/TYPE 或版本文档确认。
5. counter 单位确认是 token 后，成本口径才报告 `allocated GPU-seconds / 1M logical prompt tokens` 与 `uncached prefill tokens / request`；分开呈现 measured post-priming 与含一次 priming 的摊销口径，前者是资源占用代理，不冒充实际能耗。
6. design control 与 observed hit ratio 分开写；runtime counter 不可用时，只能声明 workload identity 设计生效，不能声明实际命中率。

---
## M2.2 — Quantization + accuracy gate

**机制问题**：KV cache 与 weight quantization 优化的是不同资源；吞吐/容量收益是否伴随可观测的输出质量退化，以及 pinned ARM64/SM121 runtime 的兼容边界在哪里。

1. 受控候选按顺序执行：
   - baseline：BF16 weight + BF16 KV；
   - candidate A：BF16 weight + FP8 KV；
   - candidate B：FP8 W8A8 weight，KV dtype 尽量保持与 baseline 相同；
   - FP8 不可用时：INT4 AWQ/GPTQ；仍不可用则收敛为 reproducible compatibility boundary。
2. candidate B 若只能与 FP8 KV 绑定，明确记录两个 axis 同时变化，只作 end-to-end 配置比较，不分别归因。
3. 精度闸门使用冻结的本地 JSONL prompt set，覆盖短指令、事实抽取、格式约束、长上下文检索；temperature=0，只使用 `normalized_exact` / `json_exact` 的二元判分，保存逐题输入、输出、score 与 item-level flip。
4. evaluator 是 `run-benchmark` 的可选外挂：性能采样与 final metrics 结束后、服务停止前顺序执行，完整输出只进入私有 raw，summary 可由 raw 重算；未配置时不改变既有 run。**不为 M2 引入 lm-eval 依赖、语义打分模型或通用评测平台**。
5. 精度结果报告 aggregate score delta 与逐题变化；没有预声明容忍度时不自动贴“可接受/不可接受”标签，由 review 结合服务收益解释。
6. 性能测量保持小矩阵：KV candidate 用 long-input case 观察 KV 占用/TTFT；weight candidate 用 short-long case 观察 TPOT/output TPS；每个受支持的主 A/B 才进入 canonical。
7. 内存结论联合使用 runtime KV capacity、container cgroup、container-attributed NVML process allocation 与 host `MemAvailable`；不把 DGX Spark 不支持的 aggregate framebuffer 数值解释为 0。

---
## M2.3 — Speculative decoding

**机制问题**：draft token 被接受带来的 target decode 节省，何时大于 draft-model、verification 与调度开销。

1. 首选 Qwen2.5-0.5B draft + Qwen2.5-7B target；若 pinned runtime/model pairing 不支持，使用 n-gram 路径。EAGLE 仅在已有兼容资产时使用，不新增训练支线。
2. baseline 与 candidate 固定 target model、prompt、sampling、output length 和并发；candidate 只增加 speculative method 与其必要参数。
3. 选择两个预声明场景：
   - 正收益 hypothesis：decode-heavy `short-long`、低并发；
   - 负收益边界：短输出或较高并发场景，验证额外开销是否令 TPOT、E2E 或 output TPS 变差。
4. 先从原始 `/metrics` 确认 accepted/drafted token counter，再最小扩展 semantic mapping；报告 acceptance rate、mean accepted tokens/draft、TTFT、TPOT、output TPS、失败数。
5. acceptance rate 只解释“draft 命中程度”，不单独等价为端到端收益；最终判断必须同时看延迟和吞吐。
6. deterministic 请求额外比较 normalized output；若输出变化，先判定 sampling/compatibility 是否一致，再决定该 pair 是否仍可比较。

---
## M2.4 — Long-context bounded checkpoint

**机制问题**：实际输入 token 增长时，何处开始出现 TTFT 非线性增长、KV 压力或运行失败。

1. 先用 `max_model_len` OVAT 找到 pinned runtime 可启动的 bounded range；每个值使用新 runtime，不把 startup success 等价为长上下文推理成功。
2. 在 C1 下递增**实际 prompt token length**，最多选择 3 个点；每点单次 exploratory，记录实际 token、TTFT、prefill time、KV usage、统一内存与 outcome。
3. 首个 readiness/client/OOM/restart 失败即停止继续上探并保留失败；不外推未测试长度，不用单次运行声明 tail latency。
4. 本项只形成同屏 run set 与候选 knee；严格质量评测、RoPE scaling 与长上下文准确率不在 M2 范围。每点只需要单次 exploratory run，不必重复 canonical。

---
## 收敛、展示与交接

1. 所有 `derived/` 必须由 raw + frozen config 重算；comparison 只接 contract-compatible pair，不匹配 pair 标 descriptive。
2. 每项只发布能支撑 review 核心声明的 Tier A 代表性 run；完整 raw 进入 M2 单一 Tier B archive，失败证据不采样。
3. `m2-review.md` 按 `Observed Fact / Interpretation / Hypothesis / Unknown` 写结论，并明确 compatibility/telemetry/execution gap。
4. comparison view 至少覆盖：prefix hit/miss、量化 baseline/candidate、spec baseline/candidate。long-context 使用 run analysis 的 2–3 run 同屏 set；复用现有 UI，不扩展通用 x-axis。
5. 交给 M3/M4/M5/M6：受支持的 runtime flags 与模型资产、M2 canonical configs、量化后的资源基线、prefix/spec runtime metrics、成本折算输入。

---
## 明确不做

Chunked prefill、CUDA graph A/B、Nsight/kernel profiling、跨节点 TP、SGLang 对比、自动参数搜索、全局 accuracy framework、M2 专属 runner/evidence framework，以及为 showcase 新建 UI。
