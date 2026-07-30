# Kubernetes-Native LLM Inference Platform

A production-oriented AI infrastructure project for learning and implementing the core components of an LLM inference platform on Kubernetes.

The project focuses on four major areas:

1. **Serving Data Plane** — running and benchmarking LLM inference engines
2. **Control Plane** — managing scheduling, memory pressure, and elasticity
3. **Observability Plane** — monitoring infrastructure, GPUs, inference runtimes, and SLOs
4. **Workload & Experiment Plane** — generating reproducible traffic, failure, and resource-contention scenarios

The primary goal is not to build a full commercial inference platform, but to implement and validate representative production mechanisms behind modern AI infrastructure systems.

---

## Project Objectives

- Deploy LLM inference workloads on Kubernetes
- Understand the architecture and performance characteristics of modern inference engines
- Build Kubernetes controllers for LLM-specific resource management
- Establish production-style metrics, dashboards, alerts, and operational runbooks
- Reproduce common inference-platform bottlenecks and failure scenarios
- Evaluate design decisions through controlled benchmarks
- Produce reusable architecture documents, experiment reports, and postmortems

---

# Architecture Overview

```text
                         Client / Load Generator
                                   |
                                   v
                         API / Gateway Layer
                                   |
                                   v
+----------------------------------------------------------------+
|                    Serving Data Plane                          |
|       vLLM / SGLang / llama.cpp / TensorRT-LLM                 |
+----------------------------------------------------------------+
            |                                  ^
            | metrics / state                  | control actions
            v                                  |
+---------------------------+      +-----------------------------+
| Observability Plane       |      | Control Plane               |
| Prometheus / Grafana      |      | Memory Supervisor           |
| GPU Exporter / SLO        |      | Scheduler Plugin            |
| Alerts / Runbooks         |      | LLM-Aware Autoscaler        |
+---------------------------+      +-----------------------------+
            ^                                  ^
            |                                  |
            +----------------------------------+
                           |
+----------------------------------------------------------------+
|               Workload & Experiment Plane                      |
| benchmark / burst / long-context / noisy-neighbor / failures   |
+----------------------------------------------------------------+
```

The **Workload & Experiment Plane** interacts with all other planes by generating traffic, resource contention, failures, and benchmark scenarios.

---

# 1. Serving Data Plane

## Purpose

The Serving Data Plane hosts the model inference runtimes that receive requests and execute model inference.

This plane provides the workload being managed, observed, and optimized by the rest of the platform.

## Main Goals

- Deploy the same or equivalent model across multiple inference runtimes
- Standardize runtime configuration and deployment
- Measure latency, throughput, resource consumption, and stability
- Understand why runtimes perform differently under different workloads
- Identify suitable runtime choices for different production scenarios

## Target Runtimes

- [ ] vLLM
- [ ] SGLang
- [ ] llama.cpp
- [ ] TensorRT-LLM

## Benchmark Dimensions

- Time to First Token — TTFT
- Time per Output Token — TPOT
- End-to-end latency
- Request throughput
- Input and output token throughput
- Maximum stable concurrency
- GPU utilization
- GPU memory utilization
- Host memory and CPU utilization
- KV-cache utilization
- Prefix-cache effectiveness
- Cold-start and model-loading time
- Failure, timeout, and OOM rate

## Completion Criteria

- [ ] A model can be deployed and queried through each selected runtime
- [ ] Runtime deployments use reproducible configurations
- [ ] Benchmark conditions are documented and controlled
- [ ] Raw benchmark results are retained
- [ ] Runtime differences are explained through architecture and workload analysis
- [ ] A final runtime comparison report is produced

---

# 2. Control Plane

## Purpose

The Control Plane manages the lifecycle and resource behavior of inference workloads running on Kubernetes.

It introduces LLM-aware control mechanisms beyond standard CPU-based Kubernetes scheduling and autoscaling.

## Main Components

### 2.1 Memory Supervisor

Monitors memory pressure and protects inference workloads from resource exhaustion and noisy-neighbor interference.

Target resources include:

- Container memory
- Node memory
- cgroup v2 memory pressure
- GPU VRAM
- KV-cache pressure
- Pinned host memory
- Pod eviction and OOM risk

Progress:

- [ ] Define memory-pressure signals
- [ ] Implement metrics collection
- [ ] Define workload priority classes
- [ ] Detect memory-pressure conditions
- [ ] Implement protective control actions
- [ ] Test noisy-neighbor scenarios
- [ ] Document recovery and failure behavior

### 2.2 Scheduler Extension

Places inference workloads according to GPU capacity, workload requirements, and runtime locality.

Potential scheduling signals include:

- GPU model and VRAM capacity
- Available GPU memory
- Existing model placement
- NUMA topology
- Node utilization
- Model-loading cost
- Request queue state
- Workload priority

The initial implementation should use Kubernetes scheduling extensions rather than replacing the complete scheduler.

Progress:

- [ ] Define scheduling requirements
- [ ] Build a basic Scheduler Framework plugin
- [ ] Implement Filter logic
- [ ] Implement Score logic
- [ ] Add GPU-aware scheduling signals
- [ ] Add model-locality awareness
- [ ] Compare custom scheduling with the default scheduler

### 2.3 LLM-Aware Autoscaler

Scales inference replicas according to serving demand and latency objectives rather than CPU utilization alone.

Candidate signals include:

- Waiting request count
- Running request count
- Queue latency
- TTFT
- TPOT
- Token throughput
- KV-cache utilization
- GPU utilization
- SLO violation rate

Progress:

- [ ] Establish an HPA baseline
- [ ] Test Prometheus Adapter or KEDA
- [ ] Define LLM-specific scaling signals
- [ ] Implement a custom autoscaling controller
- [ ] Add stabilization and cooldown policies
- [ ] Evaluate scaling under burst traffic
- [ ] Compare HPA, KEDA, and custom autoscaling

## Completion Criteria

- [ ] Controllers reconcile resources through Kubernetes APIs
- [ ] Control decisions are driven by observable metrics
- [ ] Each controller has a clearly defined policy and failure model
- [ ] Control behavior is validated through repeatable experiments
- [ ] Default Kubernetes mechanisms are used as comparison baselines
- [ ] Design trade-offs are documented through ADRs

---

# 3. Observability Plane

## Purpose

The Observability Plane provides the metrics, dashboards, alerts, and operational information required to understand and manage the platform.

It must support both human operations and automated control-plane decisions.

## Monitoring Layers

### Kubernetes Layer

- Node CPU and memory
- Pod CPU and memory
- Pod restart count
- OOMKilled events
- Pending pods
- Evictions
- Node pressure
- cgroup throttling

### GPU Layer

- GPU utilization
- GPU memory usage
- SM utilization
- Tensor Core utilization
- Temperature and power
- PCIe or NVLink activity
- GPU error events

### Inference Runtime Layer

- Request rate
- Running and waiting requests
- TTFT
- TPOT
- Token throughput
- Batch size
- Queue length
- KV-cache utilization
- Prefix-cache statistics
- Request failure rate

### Service-Level Layer

- Availability
- P95 and P99 latency
- SLO compliance
- Error-budget consumption
- Capacity saturation
- Scaling effectiveness

## Target Stack

- [ ] Prometheus
- [ ] Grafana
- [ ] kube-state-metrics
- [ ] Node Exporter
- [ ] NVIDIA DCGM Exporter
- [ ] Alertmanager
- [ ] Prometheus Adapter or KEDA metrics integration

## Operational Deliverables

- [ ] Kubernetes cluster dashboard
- [ ] GPU utilization dashboard
- [ ] LLM inference dashboard
- [ ] SLO dashboard
- [ ] Alert rules
- [ ] Recording rules
- [ ] Capacity-planning report
- [ ] Incident runbooks

## Completion Criteria

- [ ] Infrastructure, GPU, runtime, and SLO metrics are correlated
- [ ] Dashboards support diagnosis rather than visualization only
- [ ] Alerts identify actionable conditions
- [ ] Controller metrics and decisions are observable
- [ ] Benchmark results can be associated with platform metrics
- [ ] At least one failure scenario is diagnosed using the monitoring stack

---

# 4. Workload & Experiment Plane

## Purpose

The Workload & Experiment Plane generates reproducible production-like conditions for validating the Serving, Control, and Observability planes.

It ensures that platform decisions are supported by measurable evidence rather than isolated demonstrations.

## Target Workload Scenarios

- [ ] Constant low-concurrency traffic
- [ ] Gradually increasing concurrency
- [ ] Burst traffic
- [ ] Long-context requests
- [ ] Mixed input and output lengths
- [ ] Shared-prefix workloads
- [ ] Mixed-priority tenants
- [ ] CPU and memory noisy neighbors
- [ ] GPU memory pressure
- [ ] Model cold start
- [ ] Pod termination and node failure
- [ ] Rolling update
- [ ] Autoscaling oscillation
- [ ] Partial runtime degradation

## Experiment Requirements

Each experiment should define:

- Hypothesis
- Environment
- Hardware and software versions
- Model and precision
- Request distribution
- Independent variables
- Controlled variables
- Metrics collected
- Success criteria
- Results
- Interpretation
- Limitations
- Follow-up actions

## Completion Criteria

- [ ] Workloads are reproducible
- [ ] Experiment configurations are version-controlled
- [ ] Raw results are preserved
- [ ] Results can be connected to Prometheus metrics
- [ ] Each control-plane component has at least one validation scenario
- [ ] Major findings are documented in benchmark or postmortem reports

---

# Cross-Plane Deliverables

The following outputs should be maintained throughout the project:

## Architecture

- [ ] System context diagram
- [ ] Component architecture
- [ ] Request-flow diagram
- [ ] Metrics-flow diagram
- [ ] Control-loop diagrams
- [ ] Failure-domain analysis

## Engineering Documentation

- [ ] Architecture Decision Records
- [ ] Deployment instructions
- [ ] Local development guide
- [ ] Benchmark methodology
- [ ] Operational runbooks
- [ ] Incident postmortems
- [ ] Known limitations

## Production Readiness

- [ ] Health checks
- [ ] Resource requests and limits
- [ ] Graceful shutdown
- [ ] Pod disruption handling
- [ ] Configuration management
- [ ] Upgrade strategy
- [ ] Failure recovery
- [ ] Security boundaries
- [ ] SLO definitions

---

# Repository Structure

```text
ai-inference-platform/
├── control-plane/
│   ├── memory-supervisor/
│   ├── scheduler-plugin/
│   └── llm-autoscaler/
│
├── serving/
│   ├── vllm/
│   ├── sglang/
│   ├── llama-cpp/
│   └── tensorrt-llm/
│
├── observability/
│   ├── prometheus/
│   ├── grafana/
│   ├── alertmanager/
│   └── recording-rules/
│
├── workloads/
│   ├── load-generator/
│   ├── scenarios/
│   └── datasets/
│
├── benchmarks/
│   ├── configs/
│   ├── raw-results/
│   ├── analysis/
│   └── reports/
│
├── deployments/
│   ├── kind/
│   ├── kubernetes/
│   └── helm/
│
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── runbooks/
│   └── postmortems/
│
└── README.md
```

# Roadmap

See [ROADMAP.md](docs/Roadmap.md) for a detailed plan and milestones.

---

# Showcase Reading Guide

| Review Focus | Recommended Evidence |
|---|---|
| LLM Serving | `serving/`、M1/M4/M8 benchmark reports |
| Kubernetes / Platform Engineering | `deployments/`、M2、`control-plane/` |
| GPU & Memory Management | M0 environment report、M5 Memory Supervisor |
| Scheduling & Distributed Systems | M6 Scheduler、M10 distributed experiments |
| Elastic Serving | M7 Autoscaler、burst traffic report |
| Observability / SRE | M3 dashboards、M9 Runbooks and Postmortems |
| Architecture Decision-Making | `docs/adr/`、runtime and control-policy reports |
| Production Readiness | M4 failure handling、M9 final simulation |
