# LLM Inference Platform on DGX Spark

语言：中文 | [English](README-en.md)

两台 DGX Spark（GB10 Grace Blackwell / ARM64 / 统一内存）上的 LLM 推理平台工程实践。从单机 runtime 基线做起，逐步接入 Kubernetes、可观测性与控制回路。

**每个结论都由 request-level 原始数据支撑，失败数据全部保留。**

- 交互式结果 → [M1 Showcase](https://tennsoku.github.io/k8s-llm-serving-public/showcase/m1/)
- 执行计划 → [Roadmap](docs/Roadmap.md) · 当前进度 → [Status](docs/context/current-status.md)

---

## Results at a glance

Qwen2.5-0.5B-Instruct · BF16 · TP=1 · vLLM（digest-pinned NGC ARM64 镜像）· 单节点
四种 workload shape，每点 3 次重复，**10,368 个请求 0 失败 0 超时**。

| 场景 | in → out tokens | C1 TTFT p95 | C_eff | C_eff TTFT p95 | C_eff 输出 tok/s |
|---|---|---:|---:|---:|---:|
| short-short (e.g. NPC 对话) | 55 → 32 | **12.8 ms** | 8 | 27.4 ms | 1,364 |
| short-long (e.g. 剧情文本生成) | 60 → 512 | **13.3 ms** | 8 | 29.3 ms | 1,482 |
| long-short (e.g. 带世界状态的问答) | 5,890 → 32 | **133 ms** | 4 | 307 ms | 205 |
| long-long (e.g. 长会话) | 5,888 → 512 | **135 ms** | 8 | 274 ms | 749 |

`C_eff` = 吞吐边际收益仍显著、服务延迟仍可控的并发参考点，逐 workload 独立测定。

**中等模型对照** — Qwen2.5-7B-Instruct，同 workload（60 → 512）：

| 模型 | C1 输出 tok/s | C1 TTFT p95 | C8 输出 tok/s |
|---|---:|---:|---:|
| 0.5B | 148.2 | 14.3 ms | 1,493 |
| 7B | 12.7 | 80.1 ms | 126.1 |

7B 的 12.7 tok/s 达到统一内存带宽 roofline 的 **65%**（273 GB/s ÷ 14 GB BF16 权重 ≈ 19.5 tok/s）——decode 已接近带宽瓶颈，不是调度或 kernel 效率问题。

---

## 目前的3个代表性结论

### 1. Prefill 与 Decode 的成本结构完全不同

输入从 55 涨到 5,890 tokens，C1 的 TTFT 从 12.8 ms 涨到 133 ms（**10.4×**）——prefill 的一次性代价。

不过关键区别在于两者的**扩展行为**：

| 类型/token增长 | C1 → C_eff 输出吞吐 | 倍数 |
|---|---|---:|
| Decode-heavy（60 → 512） | 150.8 → 1,482 tok/s | **9.8×** |
| Prefill-heavy（5,890 → 32） | 92.4 → 205 tok/s | **2.2×** |

Decode-heavy 能靠 continuous batching 摊薄单请求开销，接近线性扩展；prefill-heavy 的计算量随并发线性增长，无法摊薄——C4 时等待队列已出现（峰值 2），C16 涨到 13。

**推论**：容量规划必须按 workload shape 分别做。用一个统一并发数覆盖所有场景，要么浪费 decode 场景的吞吐，要么压垮 prefill 场景的延迟。

### 2. 吞吐饱和点与延迟崩溃点不是同一个点

Long-long workload 的 bounded boundary test（C16 → C64）：

| 并发 | 输出 tok/s | TTFT p95 | 等待队列峰值 | KV cache 峰值 |
|---:|---:|---:|---:|---:|
| 16 | 920 | 1.56 s | 13 | 7.3% |
| 32 | 900 | 4.73 s | 27 | 14.6% |
| 48 | 916 | 9.88 s | 43 | 22.1% |
| 64 | 1,005 | **16.78 s** | 56 | 28.9% |

并发翻两番，吞吐只涨 9%，TTFT 涨 **10.7×**，等待队列线性增长——典型的排队饱和。

值得注意的是 **KV cache 峰值只有 28.9%**：容量瓶颈在调度排队，不在显存。只盯内存水位做容量判断，会在服务早已不可用之后才报警。

同理，M1.3 测量中 GPU utilization 在 C64/C96/C128 都稳定在 96%，**不随服务状态变化**。本项目因此明确不把 GPU 利用率作为饱和或容量判据。

### 3. 一次自我发现的测量错误

M1.3 首轮 concurrency sweep 得到 C64 输出 6,038 tok/s，数字很漂亮。

在复查 runtime counter 时发现：workload 使用固定 prompt，**prefix-cache token 命中率 99.31%**。绝大部分prefill工作因缓存命中被跳过，这个数字没有反馈真正的服务能力。

处理：

1. M1.3 结论**保留**，但范围限定为"该固定workload专属"，review 中写明命中率及其影响；
2. M1.4 引入 per-request `cache_salt`，为每个请求生成唯一 cache identity；
3. 重测后公开 summary 中 `prefix_cache_token_hit_ratio = 0.0`——上文表格是隔离缓存后的真实值。

`cache_salt` 只作 workload 控制字段：它隔离缓存身份，不承担证据真实性校验。

---

## 测量方法

支撑上述结论的工程约束：

| 维度 | 做法 |
|---|---|
| **时间** | duration 用 monotonic clock；wall-clock 仅用于跨日志关联 |
| **流式语义** | HTTP chunk 不等同于 model token。TTFT 取 first generated content；TPOT 由 decode 时长 ÷ 实际输出 token 数导出，不用 chunk 间隔冒充 ITL |
| **Token 计数** | 用 API 返回的实际 usage，不用目标值 |
| **缓存控制** | 每请求唯一 `cache_salt`；只在有 runtime counter 佐证时才声明命中率 |
| **重复** | canonical run 每点 3 次，报告中位数并保留 min/max |
| **失败** | timeout、OOM、non-zero exit、restart 全部保留在 `raw/`，不从 summary 过滤 |
| **可重算** | `derived/` 必须能从 `raw/` 重新生成；分析有误时修逻辑重算，不改 `raw/` |
| **配置固定** | 节点、镜像 digest、model revision、server 参数、workload 全部记录并指纹化 |

单入口重放：`serving/vllm/run-benchmark.sh --config <workload.yaml> --node-label <label>`

---

## Testbed

| | |
|---|---|
| 节点 | 2 × DGX Spark |
| Compute | NVIDIA GB10 Grace Blackwell · ARM64 |
| 内存 | CPU/GPU 共享统一内存，不按离散 VRAM 解释 |
| 网络 | ConnectX-7，实测 96.74 Gbit/s（4 streams / 30 s），RoCE 承载 NCCL collective |

M0 已验证 host CUDA、GPU 容器、TCP/NCCL 基线、NIC counter 与 RoCE 数据通路、四层 bootstrap 重放。

**已知边界**：GPUDirect RDMA 未启用（`GDR 0`）；跨节点模型并行未验证；Kubernetes GPU 集成待 M3 实测。两节点结果不外推到生产 DGX 集群。

---

## 仓库导航

| 路径 | 内容 |
|---|---|
| [`serving/vllm/`](serving/vllm/) | 服务生命周期脚本 + benchmark pipeline（streaming client、runtime/system 采集、summary 生成） |
| [`benchmarks/`](benchmarks/) | Workload 配置、公开原始结果、可重算 summary |
| [`showcase/m1/`](showcase/m1/) | M1 交互式报告 |
| [`labs/vllm-basics/`](labs/vllm-basics/README.md) | Runtime 机制学习实验（Labs 0–4） |
| [`docs/reviews/`](docs/reviews/) | 各 milestone 结论、限制与 unknowns |
| [`docs/experiments/`](docs/experiments/README.md) | 实验目录约定与脱敏流程 |
| [`docs/environment/`](docs/environment/) | 硬件、网络、NCCL 与兼容性基线 |
| [`deployments/bootstrap/`](deployments/bootstrap/) | 主机与 GPU 容器资格验证脚本 |
| [`AGENTS.md`](AGENTS.md) | AI 协作的行为契约 |

---

## AI 协作方式

本项目全程使用 AI 辅助，分工明确：

| | AI | 人工 |
|---|---|---|
| 设计 | 方案草拟、结构建议 | 取舍决策、范围裁定 |
| 代码 | 工具性代码落地 | 审阅与接受 |
| 审计 | 全程审计（一致性、证据缺口、越界结论） | — |
| 实验 | — | **全部实验执行** |
| 记录 | — | **全部结果记录与结论撰写** |
| 文档 | 草稿 | **文档控制与单一来源维护** |
| 边界 | — | **能力边界与不可外推声明的判定** |

所有实验在真实硬件上由本人执行并复核，AI 不产生任何 benchmark 数据。

[`AGENTS.md`](AGENTS.md) 是这套协作的行为契约，规定了预算约束、单一来源表、常设非目标与停手条件。它本身也是项目产出之一——M0 阶段出现过 1,137 行的 evidence 工具、为未建成组件写的规范文档等范围失控，该契约是对这些具体事故的结构性回应。

## License

除另有说明外，本仓库原创内容采用 Apache-2.0；第三方组件保留各自许可证。模型权重、容器镜像及其他外部资产不受本仓库许可证覆盖。
