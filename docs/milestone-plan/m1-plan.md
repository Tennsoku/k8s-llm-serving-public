# M1 Plan — Single-Node vLLM Serving Baseline

> **用途**：作为 M1 新 Thread 的起始 Context 与执行计划。  
> **当前状态**：M0 已完成并归档；M1 尚未正式开始 vLLM Basics Labs。  
> **执行原则**：按小 Step 推进，每完成一个 Step 再进入下一个，不提前建设暂时不需要的框架。

---

## 1. M1 定位

M1 的目标是在 **脱离 Kubernetes** 的情况下，理解 vLLM 的核心执行路径，并建立可信的单节点推理 Baseline。

本阶段重点不是“把模型服务跑起来”，而是回答：

1. vLLM 如何完成 Model Loading、Prefill、Decode 和 KV Cache 管理？
2. Offline inference 与 Online serving 的执行边界是什么？
3. 并发增加时，TTFT、TPOT、E2E 和 Token Throughput 如何变化？
4. Prefill-heavy 与 Decode-heavy workload 为什么表现不同？
5. 系统从有效并发进入 saturation 的位置在哪里？
6. 第一个 **performance knee** 和 **capacity boundary** 是什么？
7. 哪些结果应成为 M2 Kubernetes Deployment 和 M3 Observability/SLO 的输入？

M1 仍然是：

> **Single-node / Single-runtime / Controlled Benchmark**

以下内容不属于 M1 主线：

- Kubernetes 编排；
- 双节点 Tensor Parallel；
- Multi-runtime benchmark；
- Gateway / Routing；
- Autoscaling；
- 自定义 Controller；
- 完整 Prometheus / Grafana stack；
- 为公开发布建设复杂的 evidence/audit framework。

---

# 2. 已确定的工程原则

## 2.1 优先 AI Infra 学习，不优先 Repository Governance

此前 M0 closeout 因真实基础设施信息、SSH、IP、MAC、网络拓扑和远程采集等因素，建立过较严格的 evidence/publication workflow。

该实现继续保留，但：

> **M0 的 audit-style closeout workflow 不再作为 M1–M10 的默认模板。**

从 M1 开始，只保留必要的工程严谨性：

- 固定实验条件；
- 保存 raw results；
- 记录 runtime/model/workload；
- 区分 warm-up 与 measured run；
- 不删除失败结果；
- raw 与 derived 分离；
- public release 前做简单脱敏与人工检查。

不再强制：

- cryptographic sealing；
- 多级 manifest；
- staging lifecycle；
- per-milestone evidence adapter；
- global schema governance；
- publication attestation；
- clean Git tree hard gate。

---

## 2.2 Experiment Repository Convention

从 M1 起正式实验使用：

```text
artifacts/private/<milestone>/<run-id>/
├── run.yaml
├── raw/
└── derived/
```

其中：

### `run.yaml`

记录实验上下文，例如：

```yaml
run_id:
milestone: m1
experiment:
timestamp_utc:

git:
  commit:
  dirty:

environment:
  node: spark-a

runtime:
  name: vllm
  image:
  model:
  model_revision:
  args: {}

workload: {}

repeat:
outcome:
```

这是模板，不是严格 schema。

### `raw/`

保存实验直接产生的数据，例如：

```text
requests.jsonl
server.log
metrics.prom
runtime.log
system-memory.log
```

原则：

> **Raw evidence 不原地修改。**

### `derived/`

保存可由 raw data 重新生成的数据：

```text
summary.json
summary.csv
percentiles.csv
plots/
```

---

## 2.3 Exploratory vs Canonical

### Exploratory Run

用途：

- 学习；
- 调试；
- 参数探索；
- hypothesis formation。

允许：

- dirty working tree；
- incomplete telemetry；
- failure；
- 临时实验参数。

### Canonical Run

用途：

> 支撑最终 Benchmark Report / Milestone conclusion。

只要求：

- config 固定；
- runtime/model revision 已记录；
- workload 明确；
- raw data 保留；
- failure 不删除；
- result 可以重算和解释。

Canonical **不等于审计封包**。

---

# 3. M1 Execution Flow

```text
M1.0a  Lightweight Experiment Convention
   ↓
Lab 0   Environment Handoff
   ↓
Lab 1   Offline Inference
   ↓
M1.1    Runtime Fundamentals
   ↓
Lab 2   Online Serving
   ↓
M1.2a   Serving Lifecycle
   ↓
Lab 3   Concurrent Request Baseline
   ↓
M1.2b   Measurement Hardening
   ↓
M1.3    Canonical Concurrency Sweep
   ↓
Lab 4   Workload Shape Exploration
   ↓
M1.4    Canonical Workload Benchmark
   ↓
M1.5    Runtime Parameters & Capacity
   ↓
M1.6    Representative Model Scale Check
   ↓
M1 Close
```

`vllm-basics` 不作为 M1 前置课程，而是 M1 的学习骨架。

基本节奏：

```text
Learning Lab
    ↓
观察现象
    ↓
形成 mental model / hypothesis
    ↓
只把真正需要复用的部分工程化
    ↓
Controlled Benchmark
```

---

# 4. M1.0a — Lightweight Experiment Convention

## 目标

固定整个 M1+ 项目长期复用的最小实验流程。

重点只解决：

```text
实验放哪里
metadata 怎么记录
raw / derived 怎么分
publish 前怎么做最小脱敏
```

## 预计产出

```text
docs/experiments/
└── README.md

docs/notes/
└── 2026-08-experiment-workflow-simplification.md

templates/experiments/
└── run.yaml

scripts/experiments/
├── capture-command.sh       # optional
└── sanitize-public.sh

artifacts/private/           # gitignored
```

同时更新：

```text
README.md
.gitignore
```

Parent README 应改为中文为主、面向 2–5 分钟快速审阅的 AI Infra showcase 页面。

## 明确 Non-Goals

不建设：

```text
Evidence Platform
SEAL.json
manifest lifecycle
global JSON schema
per-milestone adapter
publication staging framework
artifact signing
workflow engine
```

## Exit Criteria

- [x] Experiment Convention 文档完成；
- [x] `run.yaml` template 可直接使用；
- [x] `artifacts/private/` 正确 gitignore；
- [x] lightweight sanitizer 可用，或已有简单安全流程明确；
- [x] Parent README 已完成中文化和展示逻辑调整；
- [x] M0 legacy closeout workflow 保留但不作为后续标准；
- [x] fake run 可以按 `run.yaml + raw/ + derived/` 结构落地。

**完成后立即停止 Repository Governance 工作，进入 Lab 0。**

---

# 5. Lab 0 — Environment Handoff

M0 已经完成比普通 Lab 0 更严格的环境 qualification。

因此 Lab 0 不重复：

- CUDA smoke；
- GPU container qualification；
- TCP/NCCL qualification；
- 全量 hardware inventory。

## 只确认 M1 的 Runtime Context

记录：

```text
Primary node:
Runtime image:
vLLM version:
PyTorch version:
CUDA runtime:
Model:
Model revision:
Tokenizer revision:
```

推荐 primary node：

```text
spark-a
```

Spark B 保留给后期代表性 replay。

## 最小检查

- PyTorch CUDA visible；
- vLLM runtime 可执行；
- model 可访问；
- 当前 runtime/image identity 明确。

## 产出

```text
labs/vllm-basics/lab0-environment/environment.md
```

## Exit Criteria

- [x] M1 runtime 环境明确；
- [x] baseline model 与 revision 固定；
- [x] 能说明哪些环境事实继承自 M0；
- [x] 不重复进行 M0 qualification。

---

# 6. Lab 1 — Offline Inference

这是 M1 真正开始学习 vLLM 的位置。

## 目标

绕过 HTTP server，直接通过 vLLM Python API 理解：

```text
Model Initialization
       ↓
Prompt Input
       ↓
Tokenization
  ↓
Prefill
  ├─ 一次处理全部 prompt tokens
  └─ 为每层、每个 token 生成并写入 K/V
             ↓
        KV Cache
             ↑
Decode loop
  ├─ 每轮处理一个新 token
  ├─ 读取已有 KV
  ├─ 追加新 token 的 KV
  └─ sampling → next token
       ↓
Output
```

## 初始实验矩阵

| Case | Prompt Count | Prompt Shape | Max Output |
|---|---:|---|---:|
| A | 1 | Short | 32 |
| B | 4 | Short | 32 |
| C | 8 | Short | 64 |
| D | 4 | Medium | 128 |

## 观察

- model initialization time；
- first generation；
- subsequent generation；
- 多 prompt 是否一起进入 engine；
- `max_tokens` 增长后的运行时间；
- prompt count 增长后的行为；
- model load 前后内存变化。

## 学习重点

必须能够逐步回答：

### Model Loading

`LLM` object 初始化阶段包含哪些工作？

### Prefill

长 prompt 为什么主要影响首 token 之前的工作？

### Decode

长 output 为什么形成不同于长 prompt 的性能压力？

### KV Cache

为什么 sequence length × concurrency 最终会形成容量问题？

### PagedAttention

它优化的是什么内存管理问题，而不是什么计算问题？

### Continuous Batching

为什么 LLM serving 不适合传统固定 batch 生命周期？

## 产出

```text
labs/vllm-basics/lab1-offline-inference/
├── offline_inference.py
├── observations.md
└── README.md
```

## Exit Criteria

- [x] 单 prompt inference；
- [x] multi-prompt inference；
- [x] initialization 与 execution cost 可区分；
- [x] timing/memory observations 已记录；
- [x] 能从 execution path 解释 Prefill / Decode / KV Cache。

---

# 7. M1.1 — Runtime Fundamentals Consolidation

Lab 1 完成后才决定哪些内容进入正式工程目录。

## 目标

将学习型实现与真正可复用的 Serving Runtime 代码分离。

推荐：

```text
serving/vllm/
├── README.md
├── config/
└── offline_example.py       # only if reusable
```

不要复制所有 Lab exploratory code。

## Exit Criteria

能够清楚描述：

> 一次 vLLM inference 从 model 已加载到 output 完成，大致经过哪些阶段，以及 input/output shape 为什么会影响不同阶段。

---

# 8. Lab 2 — OpenAI-Compatible Online Serving

## 目标

将 vLLM 从 offline engine 转换为 persistent inference service。

## 必做

- server startup；
- `/v1/models`；
- non-streaming completion；
- streaming completion；
- invalid model；
- malformed request；
- graceful stop；
- restart。

## 重点理解

```text
HTTP Request
     ↓
Request Queue
     ↓
Scheduler
     ↓
Prefill
     ↓
First Token
     ↓
Decode
     ↓
Streaming / Final Response
```

明确区分：

### Server Startup Latency

模型加载 → 服务 ready。

### TTFT

服务 ready 后：

```text
request submitted
→ waiting/scheduling
→ prefill
→ first generated content
```

## 工程产出

```text
serving/vllm/
├── start-server.sh
├── stop-server.sh
├── wait-ready.sh
└── README.md
```

保持脚本简单。

## Exit Criteria

- [x] server 可重复 start / stop；
- [x] restart 正常；
- [x] streaming / non-streaming 都通过；
- [x] failure path 有明确 HTTP 行为；
- [x] startup latency 与 TTFT 能区分。

---

# 9. M1.2a — Serving Lifecycle

M0 曾出现：

```text
HTTP 200
但 outer wrapper exit 141
```

M1 只吸取一个教训：

> Server 生命周期与 benchmark client 生命周期分离。

不要再围绕它建设复杂 evidence framework。

推荐：

```text
start server
    ↓
wait ready
    ↓
run requests
    ↓
stop server
```

Server logs 单独保存。

## Exit Criteria

- [x] server lifecycle 脚本稳定；
- [x] failure 不会因为 shell pipe 行为被误判；
- [x] 正常 shutdown 能识别。

---

# 10. Lab 3 — Concurrent Request Baseline

这是第一次真正进入性能测量。

## 第一版 Client 保持简单

配置：

```text
concurrency
request_count
prompt
max_tokens
timeout
```

初始记录：

```text
request_id
start
end
latency
http_status
success
failure
```

汇总：

```text
wall_time
request throughput
p50
p95
p99
success/failure
```

## 初始 Concurrency

```text
1
2
4
8
16
```

## 学习重点

回答：

1. 为什么 concurrency 增加时 throughput 可以增加？
2. 为什么 latency 同时也可能增加？
3. RPS 为什么不足以描述 LLM inference capacity？
4. input/output token 数为什么必须加入？
5. client concurrency 与 vLLM active batch 是不是同一个概念？

## Exit Criteria

- [ ] async client 可用；
- [ ] C1/2/4/8/16 可执行；
- [ ] p50/p95/p99 正确；
- [ ] failure 不会被 silent ignore；
- [ ] warm-up 与 measured run 能区分。

---

# 11. M1.2b — Measurement Hardening

只有完成 Lab 3 后，才冻结正式 measurement contract。

## 第一优先级 Metric

Canonical client 至少记录：

```text
request_id

start timestamp
first generated content timestamp
end timestamp

input_tokens
output_tokens

TTFT
E2E
TPOT

HTTP status
success
timeout
error
```

推荐 raw：

```text
raw/requests.jsonl
```

## Timing

Duration 使用 monotonic clock。

Wall-clock timestamp 只用于跨日志关联。

## Streaming 边界

重要约束：

> HTTP streaming chunk 不默认等于 model token。

因此：

- first non-empty generated content 可用于 client-side TTFT；
- chunk inter-arrival 不直接宣称为 ITL；
- TPOT 可以由 decode duration / output token count 计算；
- 真正 ITL 可以结合 vLLM server metric。

正确 metric semantics 比“多测一个数字”更重要。

## Runtime-side Supporting Metrics

逐步加入：

```text
running requests
waiting requests
KV Cache usage
prompt tokens
generation tokens
TTFT server histogram
ITL / decode metric
preemption if available
```

不要求完整 M3 Observability stack。

## Exit Criteria

- [ ] measurement boundary 写清楚；
- [ ] request-level JSONL 可用；
- [ ] TTFT/E2E/TPOT 可稳定计算；
- [ ] token count 可靠；
- [ ] timeout/error 分类明确；
- [ ] client 与 server metric 可以进行基本 cross-check。

---

# 12. M1.3 — Canonical Concurrency Sweep

到这里才产生最终报告使用的数据。

## Baseline Workload

推荐：

```text
Input:  ~128 tokens
Output: ~64 tokens
Sampling: deterministic / controlled
```

固定：

```text
node
runtime image
model
model revision
runtime args
prompt shape
output length
sampling
```

唯一主要变量：

```text
Concurrency
```

## Sweep

先：

```text
1 / 2 / 4 / 8 / 16
```

如果还没有明显 saturation，再：

```text
32 / 64 / ...
```

按观察扩展，不提前定义巨大矩阵。

## Repeat

起步：

```text
warm-up: 1–3
measured repeats: 3
```

## Metrics

Client：

- P50/P95/P99 TTFT；
- P50/P95 TPOT；
- P50/P95 E2E；
- Request Throughput；
- Input Token Throughput；
- Output Token Throughput；
- success/timeout/error。

Runtime/System：

- running requests；
- waiting requests；
- KV Cache usage；
- GPU utilization；
- system memory；
- swap/reclaim signal where useful。

## Performance Knee

不要定义为“最高能成功运行的 concurrency”。

重点找：

> 从某个并发开始，吞吐边际收益显著下降，而 TTFT / queue / resource pressure 出现非线性恶化。

核心图建议：

```text
Concurrency
vs
Output Token Throughput
+
P95 TTFT
```

## Exit Criteria

- [ ] C1–16 baseline 完成；
- [ ] 必要时扩到 saturation；
- [ ] request-level raw data 保留；
- [ ] benchmark 可重复；
- [ ] 至少形成一个 performance-knee hypothesis。

---

# 13. Lab 4 — Workload Shape Exploration

## Workload Matrix

| Workload | Input | Output | 重点 |
|---|---:|---:|---|
| Short–Short | short | short | scheduler/request overhead |
| Short–Long | short | long | Decode |
| Long–Short | long | short | Prefill |
| Long–Long | long | long | KV + combined pressure |

初始 exploratory concurrency 可以固定：

```text
C = 8
```

或使用 Lab 3 得出的合理中间点。

## 每个 Case 形成

```text
Observed Fact
Interpretation
Hypothesis
Follow-up
```

例如：

```text
Fact:
Long–Short 的 P95 TTFT 明显高于 Short–Short。

Interpretation:
first-token 前的工作显著增加。

Hypothesis:
prefill 是主要来源。

Follow-up:
固定 output，仅扫描 input token length。
```

## Exit Criteria

- [ ] 四种 workload 均完成 exploratory run；
- [ ] 能区分 Prefill-heavy / Decode-heavy；
- [ ] 每种 workload 至少有一个明确 hypothesis；
- [ ] 不把 correlation 直接写成 causality。

---

# 14. M1.4 — Canonical Workload Benchmark

正式 workload benchmark 不需要对四种 workload 全量 concurrency sweep。

每种 workload 建议只测：

```text
C = 1
C = efficient operating point
C = knee point
```

目标：

> workload shape 如何改变 latency、throughput、queue 和 memory behavior？

重点比较：

### Short–Long

- TPOT / decode；
- output TPS；
- active sequences。

### Long–Short

- TTFT；
- prefill；
- queue interaction。

### Long–Long

- KV Cache；
- memory pressure；
- preemption；
- timeout/failure boundary。

## Exit Criteria

- [ ] 四种 workload 有可比较 canonical result；
- [ ] Prefill / Decode 差异由数据支撑；
- [ ] 至少一个 workload-specific bottleneck 得到较高置信度解释。

---

# 15. M1.5 — Runtime Parameters & Capacity Boundary

只有 baseline 完成后再调参。

## 必做参数

Roadmap 要求：

```text
max_model_len
max_num_seqs
memory utilization
```

## 原则

One Variable at a Time。

不要做：

```text
3 × 3 × 3 Cartesian Product
```

而是：

```text
baseline
  ↓
change max_num_seqs only
  ↓
back to baseline
  ↓
change memory utilization only
```

## 关注

```text
parameter
  ↓
scheduler / KV / memory behavior
  ↓
queue / latency / throughput
  ↓
capacity boundary
```

目标不是寻找“最佳 benchmark 参数”，而是建立参数与系统行为之间的工程理解。

---

# 16. Unified Memory Focus

DGX Spark 的 Unified Memory 是 M1 与普通 discrete GPU baseline 的重要区别。

至少观察：

```text
model size
context length
concurrency
      ↓
system memory
KV Cache
swap/reclaim
latency
failure
```

M1 的目标只是理解和测量。

不要提前实现 M5 Memory Supervisor。

最终要能够回答：

> 在当前 Grace Blackwell Unified Memory testbed 上，模型权重、KV Cache、上下文与并发如何共同影响可用容量？

---

# 17. M1.6 — Representative Model Scale Check

## Small Model

负责：

- Lab；
- client development；
- full concurrency sweep；
- workload shape；
- parameter experiments。

## Medium Model

只做代表性验证：

```text
C1
efficient point
knee / pressure point
```

以及至少：

```text
Short–Short
Long–Short
Short–Long
```

目的：

> 当 model weights 增大后，前面观察到的 scheduler/memory/capacity behavior 如何变化？

M1 不做完整 Multi-Model Benchmark。

Multi-runtime / comprehensive model comparison 属于 M8。

---

# 18. Spark B 的使用

M1 仍然是 Single-Node Baseline。

因此：

```text
Spark A = primary M1 benchmark node
```

Spark B 不进入主实验矩阵。

如果时间允许，在 M1 close 前 replay：

```text
same image
same model
same config
same workload
```

选择：

- 一个普通 baseline；
- 一个 pressure case。

作用是验证脚本与结论没有明显 node-specific dependency。

这是加分项，不是 blocker。

---

# 19. M1 目标仓库结构

```text
labs/vllm-basics/
├── lab0-environment/
├── lab1-offline-inference/
├── lab2-online-serving/
├── lab3-concurrency/
└── lab4-workload-analysis/

serving/vllm/
├── README.md
├── start-server.sh
├── stop-server.sh
├── wait-ready.sh
└── ...

workloads/
├── contracts/
└── ...

benchmarks/configs/vllm-single-node/
├── baseline.yaml
├── concurrency.yaml
├── workload-shapes.yaml
└── capacity.yaml

benchmarks/raw-results/vllm-single-node/
└── <representative-public-runs>/

benchmarks/analysis/vllm-single-node/
└── ...

benchmarks/reports/
└── vllm-single-node-baseline.md
```

不要为 M1 新增大型 closeout hierarchy。

---

# 20. M1 Final Report

最终：

```text
benchmarks/reports/vllm-single-node-baseline.md
```

正文尽量只回答六个问题。

## 1. 测了什么？

- hardware；
- Runtime；
- model；
- workload。

## 2. 怎么测？

- controlled variables；
- warm-up；
- repeats；
- measurement boundary。

## 3. Concurrency scaling 怎么变化？

展示核心 curve。

## 4. Prefill-heavy / Decode-heavy 有什么区别？

展示 workload comparison。

## 5. Performance Knee / Capacity Boundary 在哪里？

给出最重要结论和 evidence。

## 6. M2 / M3 应该继承什么？

例如：

- runtime args baseline；
- readiness semantics；
- expected concurrency range；
- metrics contract input；
- initial SLO calibration input。

详细 raw data 用链接，不复制进报告。

---

# 21. M1 Exit Criteria

M1 完成时只要求：

- [ ] Offline inference 可以复现，并能解释 initialization / generation boundary；
- [ ] Online serving 可以稳定 start / serve / stop / restart；
- [ ] Streaming client 可以可靠测量 TTFT，decode metric 边界明确；
- [ ] 正式 benchmark 区分 warm-up 与 measured run，并保存 request-level raw data；
- [ ] Concurrency sweep 得到稳定的 latency / token throughput / failure 数据；
- [ ] 能解释 Prefill-heavy 与 Decode-heavy workload 的主要差异；
- [ ] 至少识别一个 performance knee；
- [ ] 至少识别一个 capacity boundary；
- [ ] 结论有 raw data 支撑，并明确 Fact / Interpretation / Hypothesis；
- [ ] 有一份简洁 M1 baseline report；
- [ ] M2/M3 输入已明确。

完成这些即可 close M1。

---

# 22. M1 Optional Extensions

以下均不阻塞 M1：

- Prefix Cache；
- Chunked Prefill；
- CUDA Graph on/off；
- Quantization；
- FP8 / INT4；
- Speculative Decoding；
- 70B model；
- 完整 Spark B replication；
- Nsight profiling；
- Tensor Parallel；
- Multi-runtime comparison。

如核心 Exit Criteria 已完成，不因这些内容继续拖延 M1。

---

# 23. Working Rules for New Threads

M1 后续每个小步骤建议单独 Thread。

每个新 Thread 开始时：

1. 指明当前 Step，例如 `Lab 1 — Offline Inference`；
2. 只处理当前 Step；
3. 遇到新的知识点，可继续拆独立 Thread；
4. 实验结果和长期结论写回仓库；
5. Chat 主要用于：
   - 理论学习；
   - 实验设计；
   - Debug；
   - 结果解释；
   - Review。

如果当前 Step 尚未完成，不提前设计两个 Milestone 之后的框架。

---

# 24. Immediate Next Step

当前执行顺序：

```text
Step 1
M1.0a — Lightweight Experiment Convention
        ↓
Step 2
vLLM Basics Lab 0 — Environment Handoff
        ↓
Step 3
Lab 1 — Offline Inference
```

M1.0a 完成后，不再继续优化 evidence/repository governance。

新的技术学习主线从 **Lab 0 → Lab 1** 正式开始。

---

## Guiding Principle

> **先获得理解，再抽象。**

> **先产生实验，再建设刚好够用的工具。**

> **保留 Raw Evidence，但不要让 Evidence Packaging 成为项目本身。**

> **M1 的核心成果是理解并量化 vLLM 的性能、容量和调度行为，而不是建设一个审计系统。**
