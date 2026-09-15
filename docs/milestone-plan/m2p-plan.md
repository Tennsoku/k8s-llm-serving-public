# M2p — Multi-Adapter Workload 准备（执行计划）
> 本文负责执行顺序、证据、降级与停手条件。范围与 12 h 预算见 [Roadmap](../Roadmap.md)，
> 进度只见 [current-status](../context/current-status.md)，结论写入 `docs/reviews/m2p-review.md`。

## 研究问题
能否在单台 DGX Spark 上，以同一 exact-revision `Qwen/Qwen3-8B` post-trained base、固定 non-thinking
chat template 可复现地生成 4 个行为可区分的 LoRA，由 pinned vLLM 共池并仅通过 API `model` 选择？

M2p 为 M3.6 与 [后续路由对照](../Roadmap.md#8-m6--深度观测灰度与韧性扩展后续) 准备资产，不是训练性能 Milestone；吞吐与统一内存占用仅作有界单节点基线。

## 模型选择、进入条件与范围决定
1. 固定复用 M2.3 已验证的 `Qwen/Qwen3-8B` post-trained 本地 snapshot 与 exact revision；
   不下载第二份 7–8B base、不使用 `Qwen3-8B-Base`。
   相对 Roadmap 初定的 Qwen2.5，此调整用于复用资产与统一模型家族，不表示 Qwen2.5 LoRA 不兼容。
2. M2.3 只证明 pinned runtime 可运行 Qwen3 speculative 配置，不证明 Qwen3 LoRA 已兼容；
   本阶段仍需独立完成 training、single-LoRA 与 multi-LoRA compatibility gate。
3. `Qwen3-0.6B` 继续只承担 M3 Minimal workload 与 speculative draft，不作为 adapter base。
4. 使用独立 digest-pinned ARM64 PyTorch 容器做 BF16 LoRA；serving 用 pinned vLLM，不引入 QLoRA/bitsandbytes/Unsloth/第二训练框架。
5. 训练、PEFT smoke 与 vLLM evaluation 固定 non-thinking 语义；M2p/M3.6 不启用 speculative decoding。
6. 只做 4 个 adapter。4 已满足 Roadmap；第 5–6 个不提供新增验收价值。
7. M3.6 用独立 overlay 从 `Qwen3-0.6B` 切到 Qwen3-8B + adapters；仅验证功能，不与 Minimal run 比性能。

## Milestone 产出预期
```text
目标：     生成、加载并区分 4 个 Qwen3-8B LoRA adapter
产出：     docs/milestone-plan/m2p-plan.md
          scripts/lora/{lora_train,lora_score,smoke_vllm,test_lora,test_smoke_vllm,test_lora_eval}.py
          docs/reviews/m2p-review.md
预算：     计划 150 / train 260 / score 230 / smoke 240 / 测试 230、280、260 / review 120 行
本次不做：LoRA 超参 sweep；动态 adapter 热加载；speculative + LoRA；adapter-aware router
```
仅新增获准的 `scripts/lora/`；不新增 requirements、registry、manifest schema 或 showcase，不改 M1/M2 benchmark pipeline。

## Adapter fixture
四个 adapter 共用匿名合成的 RPG 后端输入；输入不含 persona system prompt，由 adapter 决定角色和 schema。

| Adapter | 可观察行为 | 必需字段 |
|---|---|---|
| `npc-merchant` | 商人答复与报价 | `role`, `dialogue`, `price_gold` |
| `npc-guard` | 通行判定 | `role`, `dialogue`, `access` |
| `quest-planner` | 任务目标与奖励 | `role`, `objective`, `reward_gold` |
| `lore-archivist` | 世界观档案摘要 | `role`, `summary`, `archive_tag` |

每个 adapter 生成 96 条 train + 24 条 eval；实体、数值和模板 split 分离，固定 seed，标注 `synthetic=true`。
eval 前 12 条固定为开发 smoke；后 12 条仅在配置冻结后评测。分组报告，不能把开发集得分称为独立测试准确率。
这些数据不是实际玩家数据，也不构成通用质量 benchmark。

## 初始训练配置
```text
base model:           Qwen/Qwen3-8B post-trained, exact local revision
reasoning mode:       non-thinking
chat template:        pinned base tokenizer template, enable_thinking=false
precision:            bf16
LoRA:                 r=8, alpha=16, dropout=0.05, bias=none
modules:              q_proj, k_proj, v_proj, o_proj
loss / max length:    completion-only / 512
micro batch / accum:  1 / 8
learning rate:        1e-4
max steps:            initial 40 / 80; correction A/B both 80, gated below
checkpointing:        gradient checkpointing on; no intermediate checkpoint retention
sampling for eval:    temperature=0, fixed max_tokens
```
## 首个 adapter gate 与 A/B 修正

1. 开发 smoke 固定同一 12 条；至少 **8/12** 同时通过 JSON、必需字段、正确 role、无 think block，且无运行异常。
   从逐条 raw 计算联合通过数；未启用显式 gate 时，`score` exit 0 只代表无运行异常，不代表行为通过。
2. 初始 40 steps 未达门槛时允许从 base 以 80 steps 重跑；仍未达标则暂停其余 adapter，先诊断。
3. A：12 类句式 × 8 条，各类四个 train state 各 2 条；保留事件/答案/eval，`LR=1e-4`、80 steps；修正初始化 seed，与旧 s080 不作严格数据单变量归因。
4. **A ≥8/12**：停止调参并冻结配置；**A 为 6–7/12**：允许 B；**A <6/12**：直接停止并讨论 closeout。
5. B 使用与 A 完全相同的数据、80 steps 及其余配置，只将 `LR` 改为 `5e-5`；B 未达到 smoke 门槛则停止，不追加轮次。
   A/B 均从 base 开始，固定 LoRA 初始化前的 seed 和数据顺序；记录实际学习率与衰减配置，B 仅检验局部 LR 敏感性。
   使用独立 attempt 路径并保留旧结果；不同时改变训练方案与正式评测解码，不挑选采样 seed。
6. “足够改善”以本节继续/停止分支为准，不作统计显著性声明。停止后讨论 M2p 未完成项的 closeout 和 M3.6 资产调整：
   可考虑现成 adapter 或推迟 handoff；不得自动改部署、以 prompt-only 冒充 multi-LoRA 或宣布已完成。
7. 达标后冻结配置给其余 adapter，其开发 smoke 沿用本节口径；最终验收仍按 M2p.6，不随 smoke 门槛自动降低。
   thinking/sampling 可作诊断，但不能替代固定 non-thinking 评测；若修改解码，须单独批准并记录 protocol 变化。

## Artifact contract
```text
artifacts/private/m2p/<run-id>/
  raw/environment/       # image/package/CUDA/model revision/chat-template/commands
  raw/datasets/          # generated train/eval JSONL
  raw/training/<name>/   # stdout/stderr, trainer metrics, exit code
  raw/telemetry/         # container memory + host MemAvailable samples
  raw/serving/           # command, payloads, /v1/models, responses, server log
  adapters/<name>/       # adapter_config.json + adapter_model.safetensors
  derived/               # adapter-summary.json + behavior-matrix.csv
```

`MemAvailable` delta 与峰值，不称为 dedicated VRAM。

## Details
### M2p.1 Compatibility gate
1. 捕获 host、镜像 digest、Python、PyTorch/CUDA、Transformers/PEFT 等 exact versions；Transformers ≥4.51.0 且识别 Qwen3，模型/tokenizer 同 revision。
2. 用 `enable_thinking=false` 应用 chat template；完成 BF16 load、LoRA 注入、单 batch
   forward/backward 与一次 optimizer step。
3. `save_pretrained()` 后确认 adapter config 与 safetensors 可由 PEFT 重新加载。
4. 用 one-step 临时 adapter 启动 pinned vLLM；确定性请求必须成功、无 think block、JSON 可解析。
5. 90 min 内未完成 optimizer step 或 vLLM load，立即进入 Path B；不改做 QLoRA。

### M2p.2 Dataset + runner
1. 唯一入口位于 `scripts/lora/`：train 负责 generate/train，score 负责 PEFT/HTTP/summary；不保留旧入口。
2. 生成四组 deterministic train/eval 数据；检查 JSONL/split overlap/chat-template 与 token length。
3. 输出每组 logical input tokens，供训练 tokens/s 计算；不建立全局 dataset schema。

### M2p.3 First-adapter vertical slice
1. 训练 `npc-merchant`，同时每 5s 捕获 container memory 与 host `MemAvailable`。
2. 计算 logical train tokens / monotonic training wall time；保留 trainer loss/steps。
3. 用 PEFT non-thinking inference 执行本计划的 first-adapter gate，通过后冻结配置。
4. 单 adapter 启动 pinned vLLM；`model=npc-merchant` 请求失败、出现 think block 或 JSON 不可解析时停止训练其余项。

### M2p.4 Remaining adapters
1. 按冻结配置依次训练另外三个 adapter；每个使用独立输出目录和 telemetry。
2. 每个 adapter 完成 12-case signature smoke；失败保留，不逐项调参。
3. 检查四份 `adapter_config.json` 的 Qwen3-8B base lineage、rank 与 target modules 一致。

### M2p.5 Static multi-LoRA serving
1. 以 exact Qwen3-8B base 启动 vLLM，静态注册四个 adapter；`max_loras=4`/
   `max_cpu_loras>=4`/`max_lora_rank=8`，实际 flag 以 pinned runtime `--help` 为准。
2. speculative decoding 必须关闭；完整展开 server command、reasoning mode 与 adapter paths 入 raw。
3. `/v1/models` 必须列出 base + 4 adapter；逐 adapter 发 1 个 non-thinking 确定性请求。
4. 跑 16-request、concurrency=4、四 adapter round-robin smoke；仅报告成功/失败、模型选择、think/JSON，不解读小样本 latency。
5. 不启用 runtime load/unload API、resolver plugin 或外部可写 adapter path。

### M2p.6 Behavior evaluation
对 base 与四个 adapter 运行各自 24-case eval，分开发/未参与调参两组报告 HTTP、JSON、no-think、fields、role 与 confusion matrix；base 仅作参考，fields/正确角色不适用。
`lora_score.py --backend summary --raw-input <全部 raw> --gate m2p6` 离线重算分组与 gate：核对五模型各自完整覆盖、HTTP/选模执行成功；失败 exit 1，普通评分退出语义不变。采集示例见 scorer 顶部 comments。
最终 24-case 验收：各 adapter correct-role rate 与 confusion matrix 对角线均 ≥80%；仅证明 synthetic fixture 可区分，不代表业务质量，也不代替其他 Exit Criteria。

### M2p.7 Closeout + M3 handoff
1. `M2p-review.md` 只写 Observed Fact、Interpretation、Limitations、M3 handoff。
2. 列出 adapter 只读路径、Qwen3-8B revision、rank、non-thinking 约束、pinned image 与启动参数。
3. 仅在满足 Exit Criteria 后将 `current-status.md` 中 M2p 标为完成；失败 closeout 如实保留未完成项，不复制状态。
4. M3.6 overlay 挂载 Qwen3-8B + adapters，并复用本阶段成功的 exact server command。

## Exit Criteria
- [ ] 4 个 adapter 均有可复现生成路径与同一 exact Qwen3-8B lineage
- [ ] 训练、PEFT 与 vLLM 请求均固定 non-thinking，输出无 think block
- [ ] 4 个 adapter 均能由 pinned vLLM 单独加载并成功请求
- [ ] base + 4 adapters 可静态共池，API 请求可通过 `model` 指定 adapter
- [ ] 16-request mixed-adapter smoke 无 HTTP/model-selection/JSON failure
- [ ] 四个 adapter 满足 M2p.6 行为验收，开发与未参与调参样本分组报告
- [ ] 每个训练 run 有 logical tokens/s 与统一内存 observed peak
- [ ] 失败、重试、版本与限制保留；M3.6 handoff 信息完整

## Path B 与停手条件
- 行为门槛未达时按 first-adapter gate 停止与讨论，不自动降级，不把可加载等同于行为达标。
- ARM64/GB10 栈在 90 min 内无法完成 optimizer step 或 vLLM compatibility smoke：用同一 base、明确 license/revision 的现成 LoRA，先单独 load 再共池。
- Prompt-only persona 仅作降级演示，不满足 M3.6 的真实 multi-LoRA Exit Criteria；review 记录缺口，完整 M3 不得判定完成。
- vLLM 无法加载、需要换 image/base 或预计工时超过 12 h：停止并报告；不升级 runtime/换模型家族/组合 speculative decoding/做超参搜索。
