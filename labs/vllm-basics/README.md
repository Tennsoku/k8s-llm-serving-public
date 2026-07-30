# vLLM Basics Labs

> **Implementation status:** Labs 0–4 are implemented in the module directories below. Start with [Lab 0](lab0-environment/README.md), then proceed in numeric order. Each lab README contains exact steps, expected behavior, submission artifacts, pass/revise criteria, and a human-review prompt. Result CSV files contain headers only until a learner runs the experiments; no benchmark values are fabricated.

## Quick navigation

| Lab | Step guide | Primary executable | Submission notes |
|---|---|---|---|
| 0 — Environment | [Guide](lab0-environment/README.md) | `commands/verify-environment.sh` | [Environment evidence](lab0-environment/environment.md) |
| 1 — Offline inference | [Guide](lab1-offline-inference/README.md) | `offline_inference.py` | [Observations](lab1-offline-inference/observations.md) |
| 2 — Online serving | [Guide](lab2-online-serving/README.md) | `commands/start-server.sh` | [Observations](lab2-online-serving/observations.md) |
| 3 — Concurrency | [Guide](lab3-concurrency/README.md) | `concurrent_client.py` | [Review notes](lab3-concurrency/results/observations.md) |
| 4 — Workload analysis | [Guide](lab4-workload-analysis/README.md) | `run_workloads.py` | [Review notes](lab4-workload-analysis/results/observations.md) |

Run all commands from `labs/vllm-basics/` unless a guide says otherwise. The executable defaults share the served model name `Qwen/Qwen2.5-0.5B-Instruct`.

This module establishes a practical and conceptual foundation for using **vLLM as an LLM inference runtime and serving engine**.

The purpose is not merely to start an OpenAI-compatible endpoint. Each lab is designed to produce repeatable evidence about how vLLM loads models, schedules requests, manages KV Cache, exposes inference APIs, and behaves under different workloads.

This module serves as the baseline for later work in:

- Kubernetes-based inference deployment
- GPU resource management
- Observability and benchmarking
- Autoscaling and admission control
- KV Cache-aware scheduling
- Multi-runtime comparisons
- Custom AI infrastructure operators

---

## 1. Learning Objectives

After completing this module, the learner should be able to:

1. Explain where vLLM sits within an AI inference platform.
2. Distinguish model execution, inference serving, orchestration, and application layers.
3. Explain the difference between prefill and decode workloads.
4. Describe how KV Cache affects inference memory consumption and concurrency.
5. Explain the purpose of PagedAttention and continuous batching.
6. Run vLLM in offline inference and online serving modes.
7. Invoke vLLM through an OpenAI-compatible API.
8. Generate concurrent inference traffic.
9. Measure baseline latency, throughput, GPU utilization, and memory usage.
10. Document reproducible benchmark conditions and observations.
11. Identify the next bottleneck to investigate before moving into Kubernetes deployment.

---

## 2. Scope

This module focuses on **single-node, single-runtime vLLM fundamentals**.

Included:

- Local environment validation
- vLLM installation
- Offline inference
- OpenAI-compatible serving
- Streaming and non-streaming requests
- Basic concurrency testing
- GPU and memory observation
- Workload comparison
- Baseline result collection

Deferred to later modules:

- Kubernetes deployment
- Tensor parallelism
- Pipeline parallelism
- Multi-node serving
- Distributed execution
- Production gateways
- Authentication and rate limiting
- Prometheus and Grafana integration
- Autoscaling
- Prefix caching experiments
- Chunked prefill tuning
- Quantization comparisons
- Speculative decoding
- vLLM versus SGLang or TensorRT-LLM benchmarking

---

## 3. vLLM in the Serving Stack

vLLM is an inference runtime and serving engine.

```text
Client / Agent / Application
            |
            v
API Gateway or Model Router
            |
            v
OpenAI-Compatible Inference API
            |
            v
          vLLM
   ┌────────┴────────┐
   │ Request Scheduler
   │ KV Cache Manager
   │ Model Executor
   │ Sampling Engine
   └────────┬────────┘
            |
            v
       GPU / Accelerator
```

vLLM is responsible for:

- Loading model weights
- Tokenizing and scheduling inference requests
- Executing prefill and decode operations
- Managing KV Cache
- Applying batching and memory-management policies
- Sampling output tokens
- Returning generated output
- Exposing inference APIs and runtime metrics

vLLM is not responsible for the complete production platform.

A production AI inference platform usually also requires:

- API gateway
- Authentication and authorization
- Rate limiting
- Tenant isolation
- Request routing
- Model registry
- Deployment orchestration
- Health management
- Autoscaling
- Monitoring and alerting
- Cost accounting
- Canary deployment
- Failure recovery

---

## 4. Core Concepts

### 4.1 Prefill

During prefill, the model processes the input prompt and creates the initial KV Cache.

Typical characteristics:

- Processes many input tokens in parallel
- Strongly affected by prompt length
- Often more compute-intensive
- Major contributor to Time to First Token
- Long prompts can consume a large scheduling budget

### 4.2 Decode

During decode, the model generates output one token at a time.

Typical characteristics:

- Adds one or a small number of tokens per iteration
- Repeatedly reads model weights and KV Cache
- Often constrained by memory bandwidth
- Major contributor to inter-token latency
- Long outputs increase total decode workload

### 4.3 KV Cache

KV Cache stores previously computed attention Key and Value tensors so that earlier tokens do not need to be recomputed for every generated token.

Its memory consumption grows approximately with:

```text
Concurrent Sequences
× Sequence Length
× Transformer Layers
× KV Heads
× Head Dimension
× Data Type Size
```

KV Cache therefore directly influences:

- Maximum active concurrency
- Maximum context length
- GPU memory pressure
- Request admission
- Preemption behavior
- Throughput under load

### 4.4 PagedAttention

PagedAttention organizes KV Cache into fixed-size blocks rather than requiring one large contiguous allocation per sequence.

This improves:

- Memory utilization
- Allocation flexibility
- Fragmentation behavior
- Dynamic request growth
- Potential prefix sharing
- Effective batch capacity

PagedAttention primarily optimizes KV Cache memory organization. It does not remove the fundamental computational cost of Transformer attention.

### 4.5 Continuous Batching

Traditional static batching groups requests into a fixed batch and processes them together until completion.

Continuous batching performs scheduling at inference-iteration granularity.

At each iteration, the runtime may:

- Remove completed sequences
- Admit new requests
- Continue active decode requests
- Process prefill work
- Adjust the active batch according to token and memory budgets

This is important because LLM requests have variable arrival times, prompt lengths, and output lengths.

---

## 5. Lab Structure

Recommended repository layout:

```text
ai-inference-platform/
└── labs/
    └── vllm-basics/
        ├── README.md
        ├── lab0-environment/
        │   ├── README.md
        │   ├── environment.md
        │   └── commands/
        │       ├── verify-environment.sh
        │       └── install-vllm.sh
        ├── lab1-offline-inference/
        │   ├── README.md
        │   ├── offline_inference.py
        │   └── observations.md
        ├── lab2-online-serving/
        │   ├── README.md
        │   ├── commands/
        │   │   ├── start-server.sh
        │   │   └── curl-examples.sh
        │   └── observations.md
        ├── lab3-concurrency/
        │   ├── README.md
        │   ├── concurrent_client.py
        │   ├── requirements.txt
        │   └── results/
        │       ├── baseline.csv
        │       └── observations.md
        ├── lab4-workload-analysis/
        │   ├── README.md
        │   ├── workload_cases.md
        │   ├── run_workloads.py
        │   └── results/
        │       ├── workload-results.csv
        │       └── observations.md
        └── shared/
            ├── prompts/
            ├── schemas/
            └── scripts/
```

The original compact structure is workable, but separating offline inference, online serving, concurrency testing, and workload analysis makes each experiment easier to reproduce and review.

In particular, `start-server.sh` and `curl-examples.sh` belong under the online-serving lab rather than the environment lab.

---

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

# Lab 4 — Workload Shape Analysis

## Objective

Compare prefill-heavy, decode-heavy, and mixed workloads.

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
- Observe TTFT sensitivity
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
- GPU utilization
- GPU memory usage
- Failure count
- OOM occurrence
- Service stability
- Qualitative scheduling observations

## Recommended CSV Schema

```csv
timestamp,case_name,model,concurrency,request_count,input_tokens_per_request,output_tokens_per_request,wall_time_seconds,request_throughput_rps,input_token_throughput_tps,output_token_throughput_tps,avg_latency_seconds,p50_latency_seconds,p95_latency_seconds,p99_latency_seconds,peak_gpu_memory_mb,avg_gpu_utilization_percent,successful_requests,failed_requests,notes
```

## Acceptance Criteria

- All four workload cases are executed.
- Prompt and output sizes are documented.
- Results are stored in machine-readable form.
- GPU memory and utilization are observed.
- At least one bottleneck hypothesis is written for each case.
- The learner distinguishes prefill-heavy and decode-heavy behavior.

## Review Questions

1. Which case produces the highest TTFT?
2. Which case produces the highest total latency?
3. Which case places the greatest pressure on KV Cache?
4. Which case appears most compute-bound?
5. Which case appears most memory-bandwidth-bound?
6. Does high GPU utilization necessarily imply good service quality?
7. At what point does concurrency stop improving useful throughput?
8. Which additional metric is required before making capacity decisions?

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

Goodput measures only requests that satisfy a defined service-level objective.

Example:

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
