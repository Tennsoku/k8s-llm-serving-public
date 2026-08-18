# vLLM Basics Labs

Labs 0–4 **已完成**。这个模块的目的不是"跑起一个 OpenAI 兼容端点"，而是通过五个受控实验搞清 vLLM 的执行路径——模型怎么加载、请求怎么调度、KV Cache 怎么管理、不同 workload shape 为什么产生不同压力。

M1 的正式 benchmark（[结果](../../README.md#results-at-a-glance)）建立在这五个实验的结论之上。

## 各 Lab 建立了什么

| Lab | 建立的结论 | 产出 |
|---|---|---|
| **0 — 环境** | 固定 M1 的 runtime 身份：镜像 digest、vLLM/PyTorch/CUDA 版本、model revision。明确哪些环境事实继承自 M0，不重复 qualification | [环境记录](lab0-environment/environment.md) |
| **1 — Offline inference** | 绕过 HTTP 层，直接用 Python API 区分 **model initialization 成本**与 **execution 成本**；观察多 prompt 是否一起进入 engine | [观察](lab1-offline-inference/observations.md) |
| **2 — Online serving** | 区分 **server startup latency**（模型加载 → ready）与 **TTFT**（ready 后的排队 + prefill）。确立 failure path 的 HTTP 行为；服务生命周期与 benchmark 客户端生命周期分离 | [观察](lab2-online-serving/observations.md) |
| **3 — 并发基线** | C1–C16 下 throughput 与 latency 同时上升的机制；确认 **client concurrency ≠ vLLM active batch**；RPS 不足以描述 LLM 容量 | [观察](lab3-concurrency/results/observations.md) |
| **4 — Workload shape** | 固定 C8 对比四种 in/out 形态，为 M1.4 的逐 workload 选点产出四个 hypothesis；首次引入 per-request `cache_salt` 做 cache identity 隔离 | [观察](lab4-workload-analysis/results/observations.md) |

Lab 3 之后才冻结正式的测量契约（M1.2b），Lab 4 之后才为每种 workload 单独选并发点。**先建立能力，再固定契约，最后才下结论。**

## 核心机制

五个概念决定了后续所有测量口径：

- **Prefill** — 一次处理全部 prompt token，为每层每个 token 写入 K/V。因此长输入的代价集中在首 token 之前，是一次性的。
- **Decode** — 每轮只处理一个新 token，读取已有 KV 并追加。因此长输出的代价随输出长度线性累积，与长输入的压力形态不同。
- **KV Cache** — 占用 ≈ sequence length × concurrency。这是容量问题的来源：单请求很小，但并发下会成为主要内存消耗。
- **PagedAttention** — 解决的是 KV Cache 的**内存管理**问题（分块分配、消除外部碎片、支持共享），不是注意力计算本身的加速。
- **Continuous Batching** — 请求随时加入和离开正在执行的 batch，不等整批完成。这是 decode-heavy 负载能接近线性扩展、而 prefill-heavy 不能的直接原因（见 [README](../../README.md#1-prefill-与-decode-的成本结构完全不同)）。

## 运行

所有命令从 `labs/vllm-basics/` 执行，默认 served model 为 `Qwen/Qwen2.5-0.5B-Instruct`。

| Lab | 入口 |
|---|---|
| 0 | `lab0-environment/commands/verify-environment.sh` |
| 1 | `lab1-offline-inference/offline_inference.py` |
| 2 | `lab2-online-serving/commands/start-server.sh` |
| 3 | `lab3-concurrency/concurrent_client.py` |
| 4 | `lab4-workload-analysis/run_workloads.py` |

可复用的正式 pipeline 在 [`serving/vllm/`](../../serving/vllm/)——labs 是学习实现，不是生产路径。

---

# 附录 — 各 Lab 规格

以下是执行时使用的 lab 规格（目标、步骤、验收标准、复盘问题）。作为**执行记录**保留，不是当前阅读路径。

# Lab 0 — Environment Validation

## Objective

Establish a reproducible hardware and software baseline before running inference experiments.

## Tasks

1. Confirm operating system and kernel.
2. Confirm Python version.
3. Confirm GPU availability.
4. Confirm NVIDIA driver and CUDA compatibility.
5. Create an isolated Python environment.
6. Install vLLM and required dependencies.
7. Record all versions used.
8. Verify that Python can detect the GPU.
9. Verify that vLLM imports successfully.

## Suggested Environment

```text
Operating System: Linux or WSL2
Python: 3.10–3.12
GPU: NVIDIA CUDA-capable GPU
VRAM: Preferably 8 GB or more for small-model experiments
```

Exact requirements depend on the selected model and current vLLM release.

## Required Evidence

`environment.md` should include:

```text
Date:
Host operating system:
Kernel:
CPU:
System memory:
GPU:
GPU VRAM:
NVIDIA driver:
CUDA runtime:
Python:
PyTorch:
vLLM:
Model:
Model revision:
```

## Suggested Commands

```bash
uname -a
python --version
nvidia-smi
python -c "import torch; print(torch.__version__)"
python -c "import torch; print(torch.cuda.is_available())"
python -c "import vllm; print(vllm.__version__)"
```

## Acceptance Criteria

- The GPU is visible from the selected environment.
- PyTorch reports CUDA availability.
- vLLM imports successfully.
- All relevant versions are recorded.
- The setup can be reproduced from documented commands.

## Review Questions

1. Which CUDA version is reported by the driver?
2. Which CUDA runtime does PyTorch use?
3. Are these necessarily the same value?
4. How much VRAM is available before model loading?
5. Which parts of the environment could affect benchmark reproducibility?

---

# Lab 1 — Offline Inference

## Objective

Run vLLM directly through its Python API without starting an HTTP server.

This lab isolates model execution from network and API overhead.

## Tasks

1. Load a small instruction-tuned model.
2. Define deterministic sampling parameters.
3. Run one prompt.
4. Run multiple prompts in one call.
5. Compare short and long output limits.
6. Observe model startup time.
7. Observe GPU memory before and after model loading.
8. Record output and runtime behavior.

## Suggested Model

A small model should be used initially, for example:

```text
Qwen/Qwen2.5-0.5B-Instruct
```

A different model may be selected if hardware or compatibility requires it. The exact model revision must be recorded.

## Expected Implementation

`offline_inference.py` should:

- Define the model name in one configuration location.
- Use deterministic sampling where possible.
- Accept multiple prompts.
- Print each prompt and generated output.
- Report elapsed time.
- Handle model-loading or generation failures clearly.
- Avoid embedding secrets or local absolute paths.

## Suggested Experiment Matrix

| Case | Prompt Count | Prompt Length | Max Output Tokens |
|---|---:|---|---:|
| A | 1 | Short | 32 |
| B | 4 | Short | 32 |
| C | 8 | Short | 64 |
| D | 4 | Medium | 128 |

## Required Observations

Record:

- Model initialization time
- First generation latency
- Subsequent generation latency
- GPU memory after model loading
- GPU memory during generation
- Whether prompts appear to be processed together
- Effect of increasing `max_tokens`
- Effect of increasing prompt count

## Acceptance Criteria

- The model loads successfully.
- At least two prompts are processed in one generation call.
- Deterministic output is demonstrated or deviations are explained.
- Timing and memory observations are recorded.
- The learner can distinguish model initialization cost from request execution cost.

## Review Questions

1. What is contained in the vLLM `LLM` object conceptually?
2. What does `SamplingParams` control?
3. Which parameters affect output quality?
4. Which parameters affect runtime and memory use?
5. Why is the first execution often slower?
6. What overhead exists in offline inference that is absent from subsequent calls?

---

# Lab 2 — OpenAI-Compatible Online Serving

## Objective

Run vLLM as a persistent inference service and invoke it through HTTP.

## Tasks

1. Start a vLLM server.
2. Query the model-list endpoint.
3. Send a non-streaming chat-completion request.
4. Send a streaming chat-completion request.
5. Test an invalid model name.
6. Test malformed input.
7. Observe startup logs.
8. Observe idle GPU memory after model loading.
9. Stop and restart the service using documented commands.

## Required Files

### `commands/start-server.sh`

Should:

- Use strict shell settings.
- Define model, host, and port through variables.
- Fail clearly when prerequisites are missing.
- Print the final startup command.
- Avoid hard-coding machine-specific paths where possible.

### `commands/curl-examples.sh`

Should include:

- `/v1/models`
- Non-streaming `/v1/chat/completions`
- Streaming `/v1/chat/completions`
- One expected failure case

## Suggested Startup Command

```bash
vllm serve Qwen/Qwen2.5-0.5B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype auto
```

The Codex implementation should confirm the current CLI syntax against the installed vLLM version.

## Required Observations

Record:

- Server startup time
- Model loading stages
- Exposed model name
- Idle GPU memory
- Behavior of streaming responses
- HTTP status codes
- Error behavior
- Whether GPU memory is released when the server stops

## Acceptance Criteria

- The server starts reliably from the supplied script.
- `/v1/models` returns the served model.
- Streaming and non-streaming requests succeed.
- Failure behavior is documented.
- Startup and shutdown procedures are reproducible.

## Review Questions

1. Why does vLLM retain GPU memory while idle?
2. What is the difference between server startup latency and TTFT?
3. What work happens before the first output token is returned?
4. Which concerns should be handled by vLLM?
5. Which concerns should be handled by an external gateway?

---

# Lab 3 — Concurrent Request Baseline

## Objective

Generate concurrent traffic and establish a basic latency and throughput baseline.

## Tasks

1. Implement an asynchronous HTTP client.
2. Send requests at concurrency levels 1, 2, 4, 8, and 16.
3. Record total wall-clock time.
4. Record per-request latency.
5. Record success and failure counts.
6. Calculate request throughput.
7. Calculate p50, p95, and p99 latency.
8. Save results to CSV.
9. Repeat each test enough times to reduce one-run noise.
10. Document warm-up behavior.

## Minimum Metrics

| Metric | Description |
|---|---|
| Concurrency | Number of simultaneous in-flight requests |
| Request count | Total requests issued |
| Success rate | Percentage of successful requests |
| Wall time | Total test duration |
| Average latency | Mean end-to-end request latency |
| p50 latency | Median request latency |
| p95 latency | Tail-latency indicator |
| p99 latency | High-percentile tail latency |
| Request throughput | Completed requests per second |

## Recommended CSV Schema

```csv
timestamp,model,concurrency,request_count,successful_requests,failed_requests,wall_time_seconds,throughput_rps,avg_latency_seconds,p50_latency_seconds,p95_latency_seconds,p99_latency_seconds
```

## Implementation Requirements

`concurrent_client.py` should:

- Use asynchronous I/O.
- Support configurable concurrency.
- Support configurable request count.
- Support configurable prompt and `max_tokens`.
- Use request timeouts.
- Record non-200 responses.
- Print a readable summary.
- Write machine-readable CSV output.
- Avoid silently ignoring failed requests.
- Separate warm-up requests from measured requests.

## Acceptance Criteria

- Tests run at all required concurrency levels.
- Results are written to `baseline.csv`.
- Latency percentiles are calculated correctly.
- Failures are counted and explained.
- The test can be rerun without editing source code.
- Warm-up behavior is documented.

## Review Questions

1. Why can throughput increase while average latency also increases?
2. Why are p95 and p99 important for online inference?
3. What does client-side concurrency actually measure?
4. Does a completed request per second metric fully describe LLM throughput?
5. Why must input and output token counts eventually be added?

---

# Lab 4 — Fixed-C8 Workload Shape Analysis

## Objective

Compare four prefill/decode workload candidates once at C8 with request-level cache identity isolation. This lab does not search for saturation or capacity. Follow the executable [Lab 4 manual](lab4-workload-analysis/README.md).

## Workload Cases

### Case A — Short Input, Short Output

```text
Prompt: 32–64 tokens
Output: 32 tokens
Concurrency: 8
```

Purpose:

- Establish a lightweight request baseline
- Observe request-management overhead
- Measure low-token latency behavior

### Case B — Short Input, Long Output

```text
Prompt: 32–64 tokens
Output: 512 tokens
Concurrency: 8
```

Purpose:

- Create a decode-heavy workload
- Observe sustained token generation
- Compare end-to-end latency and GPU activity

### Case C — Long Input, Short Output

```text
Prompt: 2,000 or more tokens
Output: 32 tokens
Concurrency: 8
```

Purpose:

- Create a prefill-heavy workload
- Form a TTFT/prefill hypothesis for later streaming validation
- Compare prompt-processing cost

### Case D — Long Input, Long Output

```text
Prompt: 2,000 or more tokens
Output: 512 tokens
Concurrency: 8
```

Purpose:

- Stress both prefill and decode
- Increase KV Cache pressure
- Observe memory and scheduling limits

## Required Measurements

For each case, record:

- Input token count
- Output token count
- Concurrency
- Request count
- End-to-end latency
- Request throughput
- Input-token throughput
- Output-token throughput
- Failure count
- Optional supporting telemetry or an explicit unsupported/not-collected note

## Recommended CSV Schema

```csv
timestamp,case_name,model,concurrency,request_count,input_tokens_per_request,output_tokens_per_request,wall_time_seconds,request_throughput_rps,input_token_throughput_tps,output_token_throughput_tps,avg_latency_seconds,p50_latency_seconds,p95_latency_seconds,p99_latency_seconds,peak_gpu_memory_mb,avg_gpu_utilization_percent,successful_requests,failed_requests,notes
```

## Acceptance Criteria

- All four workload cases are executed once at C8.
- Prompt and output sizes are documented.
- Results are stored in machine-readable form.
- The pinned API accepts the cache-isolation field; optional telemetry is not a pass gate.
- At least one bottleneck hypothesis is written for each case.
- The learner distinguishes prefill-heavy and decode-heavy behavior.

## Review Questions

1. Which case produces the highest client-side E2E latency?
2. Which case produces the highest total latency?
3. Which case places the greatest pressure on KV Cache?
4. Which case appears most compute-bound?
5. Which case appears most memory-bandwidth-bound?
6. Does high GPU utilization necessarily imply good service quality?
7. Which signal should M1.4 use to bracket each workload?
8. What cannot be concluded from one non-streaming C8 point?

---

## 6. Metric Definitions

### Time to First Token

Time from request submission until the first generated token is received.

```text
TTFT = First Token Timestamp - Request Start Timestamp
```

TTFT is strongly influenced by:

- Queueing delay
- Prompt length
- Prefill scheduling
- Batch composition
- Server load

### Inter-Token Latency

Delay between consecutive generated tokens.

```text
ITL_i = Token Timestamp_i - Token Timestamp_(i-1)
```

ITL is strongly influenced by:

- Decode scheduling
- Active batch size
- GPU memory bandwidth
- Model size
- Runtime implementation

### Time per Output Token

Average time spent per generated output token after the first token.

```text
TPOT = Decode Duration / Number of Generated Tokens
```

### End-to-End Latency

Total request duration from submission until the full response completes.

```text
E2E Latency = Completion Timestamp - Request Start Timestamp
```

### Request Throughput

```text
Request Throughput = Completed Requests / Total Wall Time
```

### Input-Token Throughput

```text
Input Token Throughput = Total Input Tokens / Total Wall Time
```

### Output-Token Throughput

```text
Output Token Throughput = Total Generated Tokens / Total Wall Time
```

### Goodput

In this project, unqualified Goodput means output-token throughput contributed only by requests that satisfy the defined service-level objective. A compliant-request rate is a separate request/s metric; see the [SLO semantics](../../docs/SLO/inference-service-slo.md#7-goodput-与-raw-throughput-的区别).

Illustrative eligibility example (not a project objective):

```text
A request is considered good when:

TTFT <= 2 seconds
AND
p95 ITL <= 100 milliseconds
```

A system can have high raw throughput but poor goodput if latency becomes unacceptable.

---

## 7. Experiment Rules

All labs should follow these rules.

### Reproducibility

Every result must record:

- Hardware
- Software versions
- Model name
- Model revision
- Runtime arguments
- Prompt characteristics
- Output-token limit
- Concurrency
- Request count
- Warm-up procedure

### One Variable at a Time

Avoid changing several parameters in one comparison.

Bad comparison:

```text
Change model, concurrency, prompt length, quantization, and output length together.
```

Better comparison:

```text
Keep model, prompt, and output length fixed.
Change only concurrency.
```

### Warm-Up

Model initialization, CUDA kernel initialization, graph capture, cache population, and filesystem effects can distort first-run results.

Every measured experiment should distinguish:

- Cold start
- Warm-up run
- Measured runs

### Repetition

Run each measured case multiple times.

Recommended starting point:

```text
Warm-up runs: 1–3
Measured runs: 3–5
```

### Failure Recording

Do not delete failed results.

Record:

- HTTP status
- Exception
- Timeout
- OOM
- Server log excerpt
- Concurrency
- Workload shape
- Recovery behavior

---

## 8. Codex Implementation Guidance

Codex should treat each lab as an independently reviewable unit.

For every lab, Codex should produce:

1. A lab-specific `README.md`
2. Executable code or shell commands
3. Configuration instructions
4. Expected output
5. Acceptance criteria
6. Error-handling behavior
7. Result templates
8. Open questions for human review

Codex should not invent benchmark numbers.

Generated code should:

- Use explicit configuration
- Avoid unnecessary abstractions
- Include type hints where practical
- Fail clearly
- Preserve raw measurement data
- Avoid machine-specific paths
- Separate experiment configuration from logic
- Produce both human-readable and machine-readable output

Codex should mark version-sensitive vLLM CLI or API usage clearly.

---

## 9. Module Deliverables

The completed module should contain:

- Reproducible environment setup
- Offline inference example
- Online serving scripts
- Streaming and non-streaming request examples
- Concurrent benchmark client
- Workload generator
- Baseline CSV results
- GPU and memory observations
- Lab-specific notes
- Parent-level summary
- Identified bottlenecks
- Recommended next experiments

---

## 10. Completion Checklist

### Environment

- [ ] GPU detected
- [ ] CUDA available through PyTorch
- [ ] vLLM installed
- [ ] Environment versions recorded
- [ ] Model revision recorded

### Offline Inference

- [ ] Single-prompt inference completed
- [ ] Multi-prompt inference completed
- [ ] Runtime measured
- [ ] Memory observed
- [ ] Initialization overhead documented

### Online Serving

- [ ] vLLM server started
- [ ] `/v1/models` verified
- [ ] Non-streaming request completed
- [ ] Streaming request completed
- [ ] Failure case tested
- [ ] Idle GPU memory documented

### Concurrency

- [ ] Concurrency 1 tested
- [ ] Concurrency 2 tested
- [ ] Concurrency 4 tested
- [ ] Concurrency 8 tested
- [ ] Concurrency 16 tested
- [ ] p50/p95/p99 calculated
- [ ] Results saved to CSV
- [ ] Failed requests recorded

### Workload Analysis

- [ ] Short-input/short-output case completed
- [ ] Short-input/long-output case completed
- [ ] Long-input/short-output case completed
- [ ] Long-input/long-output case completed
- [ ] GPU utilization observed
- [ ] GPU memory observed
- [ ] Bottleneck hypotheses documented

### Review

- [ ] Prefill and decode explained
- [ ] KV Cache impact explained
- [ ] PagedAttention explained
- [ ] Continuous batching explained
- [ ] Throughput-latency trade-off explained
- [ ] Next experiment selected

---

## 11. Final Review Questions

At the end of the module, the learner should answer:

1. Where does vLLM sit within an AI inference platform?
2. What is the difference between offline inference and online serving?
3. What work occurs during prefill?
4. What work occurs during decode?
5. Why does KV Cache limit concurrency?
6. What problem does PagedAttention solve?
7. Why is continuous batching useful for LLM workloads?
8. Why can request throughput improve while tail latency worsens?
9. Why is request throughput alone insufficient for comparing LLM systems?
10. Which workload first exposes the local system bottleneck?
11. What evidence supports that bottleneck hypothesis?
12. Which vLLM parameter or platform component should be investigated next?

---

## 12. Exit Criteria

This module is complete when:

- All labs can be reproduced from documentation.
- Raw results are preserved.
- The learner can explain observed behavior rather than only report numbers.
- A single-node serving baseline has been established.
- The next bottleneck has been selected using evidence.
- The project is ready to proceed into deeper vLLM scheduling, KV Cache, benchmarking, or Kubernetes integration work.

The expected outcome is not simply:

> vLLM successfully served a model.

The expected outcome is:

> A reproducible single-node inference baseline was established, key serving behaviors were measured, and the first capacity or scheduling bottleneck was identified with supporting evidence.
