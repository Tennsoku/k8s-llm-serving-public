# M1 — Single-Node vLLM Baseline（执行记录）

> 本文记录 M1 的**执行序列与方法学决策**；当前进度只见 [current-status](../context/current-status.md)。
> 结果数据在 [README](../../README.md#results-at-a-glance) 与 [showcase](../../showcase/m1/)，结论在 [reviews](../reviews/)，本文不复制。
> 预算 ≤ 150 行。

---

## 交付物

| 类别 | 产出 |
|---|---|
| Runtime 学习 | [Labs 0–4](../../labs/vllm-basics/README.md) — offline inference、online serving、并发基线、workload shape 探索 |
| 工程代码 | `serving/vllm/` — 服务生命周期脚本 + streaming benchmark pipeline + runtime/system 采集 + summary 生成 |
| 实验配置 | `benchmarks/configs/vllm-single-node/` — 四种 workload shape、OVAT、boundary、medium model 的 versioned config |
| 原始证据 | `benchmarks/raw-results/m1-vllm-baseline/` — 11 个 final-reference run 的公开抽查副本；[producer 与 public 投影对比](../reviews/m1-public-evidence-projection.md) |
| 结论 | [M1.3 review](../reviews/m1.3-review.md)、[showcase](../../showcase/m1/) |

---

## 执行序列

```text
Lab 0 环境交接 → Lab 1 offline → M1.1 runtime 基础
  → Lab 2 online serving → M1.2a 生命周期 → Lab 3 并发基线 → M1.2b 测量收敛
  → M1.3 concurrency sweep → Lab 4 fixed-C8 四形态探索
  → M1.4 per-workload benchmark → M1.5 OVAT + boundary
  → 统一内存 checkpoint → M1.6 medium model → close
```

每一步的产出都是下一步的输入：Lab 3 建立客户端能力后才冻结 M1.2b 的测量契约；Lab 4 用固定 C8 产出四个 hypothesis 后，M1.4 才为每种 workload 单独选点。**没有先建大矩阵再解释**。

---

## 方法学决策

这一节是 M1 真正的产出——**如何测**比测到什么更决定结论是否成立。

### 1. Operating reference 的五级分类

不用"饱和点"这种单一标签，因为它把不同强度的证据混为一谈：

| 级别 | 含义 |
|---|---|
| `C1` | 单请求参考 |
| `C_eff` | 吞吐边际收益仍显著、服务延迟仍可控 |
| `C_pressure` | 吞吐边际收益减弱，**且有直接证据**（延迟、队列、抢占或有效吞吐下降），同时仍可稳定复现 |
| `highest_tested` | 安全范围内未观测到压力时的最高测试点 |
| `Unknown` | 已在声明范围内测试但无直接证据 |

`Unknown` 是**合格结论**。在声明范围内完成测试但未观测到 `C_pressure` 时，如实记为 `Unknown + highest_tested`，而不是把 `highest_tested` 改写成容量上限。

### 2. 选点标准不自动执行

预声明的 criteria 与 pressure indicator **只写进 post-run summary annotation**，不自动停止 sweep、不自动命名 `C_eff` / `C_pressure`。

原因：让工具替人下判断会掩盖判断依据。sweep 只由**真实的失败**停止——client failure（含独立的 request-timeout 分类）、readiness failure，OOM/restart 由最终容器状态记录并使 lifecycle 失败。

### 3. Prefix cache：设计控制 ≠ 观测命中率

严格区分两种表述：

- **design control** — 请求使用隔离的 cache identity（可由配置证明）；
- **observed miss rate** — 只有 runtime counter 证据支持时才可声明。

M1.3 的教训直接催生了这条：固定 prompt 导致 99.31% 命中率，结论范围被迫限定。M1.4 起每请求生成唯一 `cache_salt`，公开 summary 中 `prefix_cache_token_hit_ratio = 0.0`。

`cache_salt` 是 workload 控制字段，不承担证据真实性校验。

### 4. Exploratory 与 canonical

两个用途标签，不是目录层级：

- **exploratory** — 验证 workload、兼容性、选点。可单次、可失败，但必须保留配置与失败。不用于最终 tail-latency 或 capacity 声明。
- **canonical** — 固定测量边界、同配置重复 3 次、保存 request-level 证据、只汇总预声明的信号。

canonical **不等于审计封包**。M1 明确不建设 cryptographic sealing、多级 manifest、staging lifecycle、per-milestone evidence adapter、global schema governance、publication attestation、clean-tree hard gate——这些在 M0 出现过，代价是一个 1,137 行的 evidence 工具。

### 5. 测量语义

见 [README 测量方法](../../README.md#测量方法)。核心一条：**HTTP streaming chunk 不默认等同于 model token**，因此 TPOT 由 decode 时长 ÷ 实际输出 token 数导出，不用 chunk 间隔冒充 ITL。

宁可少报一个数字，也不报一个语义不清的数字。

---

## 实验覆盖

| 组 | 内容 | 重复 |
|---|---|---|
| M1.3 | 固定 prompt 的 C1–C128 concurrency sweep | 3 |
| M1.4 | 四种 workload shape × C1/C_eff/highest_tested | 3 |
| M1.5 OVAT | `max_model_len`、`max_num_seqs`、memory utilization 各一个 alternate value，一次只改一个参数，无 Cartesian product | 1 |
| M1.5 boundary | long-long C16→C64，预声明起点/步进/上限与停止条件 | 1 |
| M1.6 | Qwen2.5-7B 与 0.5B 同 workload 两点对照 | 1 |

OVAT 的三个 alternate 均为 server 启动参数，各自使用新 runtime 实例。

---

## 已知限制

- 三个 OVAT pair 的 baseline 与 candidate 在 sampler interval 与 repetition 数上不同，case contract fingerprint 不匹配，只作 **descriptive comparison**，不构成 controlled causal conclusion。
- M1.5 的 boundary 与 M1.6 为单次运行，不用于 tail-latency 声明。
- Spark B 的对照重放未执行，node dependency 未检查。

---

## 交给后续 milestone

| 交付 | 用途 |
|---|---|
| 四种 workload 的 versioned config 与 operating reference | M2 优化实验的对照基线 |
| request-level 测量契约与 `metrics_utils.py` 的 Prometheus 解析 | M4 可观测性的指标语义基础 |
| "GPU utilization / KV cache 不作容量判据" | M4 SLO 的判据选择依据 |
| 裸机基线数据 | M3 隔离 Kubernetes 引入的开销 |
| 五级 operating reference 分类 | 后续所有容量结论的表述规范 |

---

## 未做（不阻塞 M1）

Prefix cache A/B、chunked prefill、CUDA graph A/B、量化、投机解码、70B 模型、Spark B 完整复现、Nsight profiling、tensor parallel、multi-runtime 对比。

其中量化、投机解码、prefix cache A/B 已提升为 [M2](../Roadmap.md) 的正文。
