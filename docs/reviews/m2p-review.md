# M2p Review — Multi-Adapter Workload

**结论：** 进行了 4 个预设场景的 LoRA 训练，已验证基于 single/static multi vLLM 的加载与行为区分并固定证据，支持后续作为 M3.6 的功能接入资产；merchant case 残余了两条验证错误但已可以证明功能可行性和区分度，当前 milestone 不进行追加训练。

*Note:* 一个训练过程中的主要发现：在持续低训练 loss 的情况下仍得到了很低的行为通过率。分析后发现主要是训练集句式过度单一导致出现训练过程快速拟合，泛化不足。在扩展训练句式后，固定验证集的行为通过数大幅增加。不作为严格的数据单变量因果归因，但是可以体现 LoRA 训练中同拟合速率时训练集泛化度对行为通过率的显著影响。

## Observed Fact

### 最终行为与 serving

最终验收 run 为 `20260907-m2p-lora-r01`；输入为匿名 synthetic fixture，四个角色使用相同输入，由 API `model` 字段选择 adapter，不在输入中追加 persona 提示。
每个 adapter 的 eval 前半用于开发、后半在配置冻结后评测；下表分母不剔除失败，合计不是独立测试准确率。

| Adapter | 开发组 | 留出组 | 合计正确 role |
|---|---:|---:|---:|
| npc-merchant | 11/12 | 11/12 | 22/24 |
| npc-guard | 12/12 | 12/12 | 24/24 |
| quest-planner | 12/12 | 12/12 | 24/24 |
| lore-archivist | 12/12 | 12/12 | 24/24 |

- [正式 raw][behavior-raw] 的 96 条 adapter 请求均通过 HTTP、模型选择、JSON、必需字段及 no-think；[summary][behavior-summary] 与 [matrix][behavior-matrix] 可从 raw 重算，满足 [M2p.6 gate](../milestone-plan/m2p-plan.md#m2p6-behavior-evaluation)。
- 失败组：merchant 的 `eval-002`／`eval-012` 分别输出 `role=eval-site-016`／`eval-site-019`；dialogue 与 price_gold 均匹配参考答案，API 返回模型仍为 merchant，可以判定行为框架无误，但是存在部分混淆。两条均属 `eval-0` 句式，分别落在开发组和留出组。
- [Base reference][base-raw] 共 24 条：HTTP、模型选择、no-think 均通过，但是 JSON 完整度为 21/24；未指定 persona，正确角色／必需字段不适用，不进入 adapter 行为门槛。matrix 的 failure 列不等于 base 正确率为零，但是在有限输入的前提下该数据有较大参考性。
- [Serving 汇总][serving] 中四个 `single-<role>-01` 阶段各完成一次独立加载／请求；`multi-01` 注册 base + 四 adapter，逐个请求后完成 C4、16-request round-robin smoke，HTTP／选模／JSON／no-think 均通过。
- [mixed smoke][smoke-raw] 的 role 为 15/16；`behavior-01` 采用 C1，两个采集批次共 120 条，无 operational failure。其 11 项 capture 退出码均为 0，停止后 inspect 为 Exited(0)、无 OOM。

### 训练修正与诊断

- 旧 run `20260904-m2p-lora-r01` 的 merchant 开发联合 gate：40 steps 为 [0/12][old40]，80 steps 为 [5/12][old80]；80-step [训练记录][old-train] 的末步 loss 已为 0.0001。该 run 已经被列为未丰富的训练数据产生的低于预期的通过率典型。
- 在落地训练集修正以后保留 96 条事件、答案与全部 eval，将 train 从 4 类句式改为 12 类，各类覆盖四种 state；实际数据见 [旧 dataset][old-data] 与 [A dataset][new-data]。80 steps、初始 LR 不变，同时把 seed 设置移到 LoRA 初始化之前。
- 训练集修正后的 [PEFT 开发评分][peft] 为 merchant 11/12、其余三个各 12/12；达标后沿用 [冻结配置](../milestone-plan/m2p-plan.md#首个-adapter-gate-与-ab-修正)，因训练集修正的结果高于预期，未进行进一步的学习率或训练步数调整。
- 追加证据：[诊断 raw][diagnostic] 中，同一失败事件仅换句式即可从 128-token 未闭合输出变为 33-token 精确匹配；只换 state 未修复。该观察只覆盖所测事件，不是全量消融。

### 单节点训练与内存观测

下表由 [training 记录][training] 与 [telemetry 汇总][telemetry] 得到；训练与采样返回码均为 0。

| Adapter | Logical tokens | Train wall (s) | Logical tokens/s | 容器 NVML 窗口峰 (GiB) |
|---|---:|---:|---:|---:|
| npc-merchant | 48,488 | 166.483 | 291.249 | 21.853 |
| npc-guard | 44,008 | 164.002 | 268.338 | 16.141 |
| quest-planner | 44,008 | 163.319 | 269.461 | 16.141 |
| lore-archivist | 47,848 | 165.902 | 288.410 | 16.162 |

Logical tokens 为实际 micro-batch 的 prompt + 答案、排除 padding，重复训练重复计数；wall time 仅包围 `trainer.train()`，不含加载／保存，口径见 [训练实现](../../scripts/lora/lora_train.py)。
NVML 使用 `container_nvml_process_gpu_memory_used_bytes`，按目标容器 cgroup 筛选 GPU 进程求和；5s 间隔采样分别有 53／51／53／52 条，均成功。表值是采样窗口峰，不是专用 VRAM、净训练增量或 optimizer 阶段的精确峰值。
四次训练中复用同一 long-running 容器，`cgroup_memory_peak_bytes` 为跨 run 采集的高水位；merchant 首样本也不是空载基线，不能据此把峰值差异归因于训练 persona 的差别。设备 framebuffer 计量为 unsupported，不代表零占用。

## Interpretation

1. 仅看 loss 或增加 steps 不足以验收训练行为，低多样性输入分布导致的句式泛化不足使得实际验证通过率低于预期，是本轮证据最支持的解释。改进方向优先检查了训练分布与任务表达，而非调高学习率。修正后观察到行为通过率提升。
2. merchant 的残余问题是生成 JSON 内的 role／实体字段混淆，不是 API 选模失败；其余表现仍支持了本 milestone 的有界行为区分的目标。
3. 资产目标已经有功能证据支持。不继续追求零错误，直接转入 M3.6 接入验证。

## Limitations / Unknowns

- synthetic 小样本只证明指定角色／格式可区分；required-fields 只检查键存在，不检查业务值或类型，不支持实际生产环境下真实游戏任务质量或通用能力。
- 修正案同时修正了初始化 seed，未彻底隔离；第二修正案未执行，学习率影响未单独验证。
- thinking／采样诊断不能替代冻结的 non-thinking 协议；所测对照不足以确定 Qwen3-8B 或关闭 thinking 是否是残余根因（思维链不足等导致性能下降？Unknown）
- single/mixed 与 C1 行为评测为 smoke tests，不是性能 benchmark；K8s 生命周期、M3.6 overlay、动态 adapter 加载和 speculative + LoRA 均未在本阶段执行。

## M3 handoff

- Base 为 `Qwen/Qwen3-8B` post-trained，记录的 revision 为 `b968826d9c46dd6066d109eabc6255188de91218`；容器内使用 `/models/Qwen3-8B` 只读挂载。
- 本地 adapter 资产的四个同名子目录均有 config + safetensors；分别只读挂载到 `/adapters/<role>`。四份[配置][adapters]均为 rank 8、alpha 16，targets 为 q/k/v/o projection；这些 JSON 配置文件不是推理评分 JSONL。
- [训练 runtime 版本][versions]：PyTorch `2.13.0a0+9186a08b2c.nv26.07`／CUDA `13.3`／Transformers `4.57.6`／PEFT `0.20.0`；训练镜像与挂载见 [实际启动命令][train-start]。
- serving 镜像、入口、资源参数与完整展开命令以 [multi-01/create][serve-command] 为准；已测静态四 adapter、`max_loras=4`、`max_cpu_loras=4`、`max_lora_rank=8`、BF16，speculative 关闭。不要复制 M2 speculative config 的整组 extra_args。
- M3.6 保留现有 model 名与 non-thinking 约束：`enable_thinking=false`、temperature 0、max_tokens 128；重用 [smoke](../../scripts/lora/smoke_vllm.py) 与 [score](../../scripts/lora/lora_score.py) 的功能判定，不把 Docker 成功当作 K8s 已验证。
- 原始失败、诊断和重试均留在两个 run 中；离线重算入口为 `lora_score.py --backend summary --raw-input <adapters raw> <base raw> --gate m2p6`，派生输出使用新路径，不覆盖 raw。

[behavior-raw]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/raw/adapters.jsonl
[base-raw]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/raw/base.jsonl
[behavior-summary]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/derived/behavior-01.jsonl
[behavior-matrix]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/derived/behavior-matrix-01.csv
[serving]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/derived/run-summary.json
[smoke-raw]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/raw/smoke-responses.jsonl
[old40]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260904-m2p-lora-r01-candidate/raw/npc-merchant-s040.peft.jsonl
[old80]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260904-m2p-lora-r01-candidate/raw/npc-merchant-s080.peft.jsonl
[old-train]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260904-m2p-lora-r01-candidate/raw/training-metrics.jsonl
[old-data]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260904-m2p-lora-r01-candidate/raw/datasets.jsonl
[new-data]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/raw/datasets.jsonl
[peft]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/raw/peft-development.jsonl
[diagnostic]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260904-m2p-lora-r01-candidate/raw/diagnostic-20260907.jsonl
[training]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/raw/training-metrics.jsonl
[telemetry]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/derived/run-summary.json
[adapters]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/run.yaml
[versions]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/raw/runtime.log
[train-start]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/raw/runtime.log
[serve-command]: ../../benchmarks/raw-results/m2p-lora-multi-adapter/20260907-m2p-lora-r01-candidate/raw/runtime.log
