# M2.1 Priming Metrics 重算记录

> 本文只记录 M2.1 canonical pair 的成本重算方法与中间值；正式实验结论仍以 [M2 review](m2-review.md) 为 owner。`raw/` 不因本文而修改。

## 定义统一 + 口径冻结

- `priming phase` 是 config 中完整的 2-request warm-up，不拆分第一、第二个请求。
- `post-priming` 只计算一个 measured case；`priming-inclusive` episode = 同一 priming phase + 该 measured case 的 16 个请求。
- Warm-up 是前置成本：其 wall time 与 uncached counter 加入分子，但 2,064 warm-up logical tokens 不加入 measured-workload 分母。
- 每个 repetition 都用同一条实际 priming evidence 构造可比 episode；inclusive 数值是摊销场景，不能跨 repetition 相加还原真实 run timeline。
- `G=1`：`raw/server/server-command.txt` 记录 `--gpus all`，Spark A 的 inventory 记录单个 NVIDIA GB10。`gpu_memory_utilization: 0.25` 不是 0.25 GPU。

Run 的 private evidence 根目录分别为：

- `<B> = artifacts/private/m2/20260823-m2-apc-baseline-7b-canonical`
- `<C> = artifacts/private/m2/20260823-m2-apc-candidate-7b-canonical`

## 符号与数据来源

| 符号 | 含义 | 可重算来源 |
|---|---|---|
| `Q_r` | measured case 查询 token delta | `derived/cases.jsonl`: `.runtime_counters.prefix_cache_queries_total.after - .before` |
| `H_r` | measured case 命中 token delta | `derived/cases.jsonl`: `.runtime_counters.prefix_cache_hits_total.after - .before` |
| `N_r` | measured 成功请求数 | `derived/cases.jsonl`: `.client.successful_requests`；可由 `raw/requests.jsonl` 的成功记录复核 |
| `L_r` | measured logical input tokens | `derived/cases.jsonl`: `.client.input_tokens`；等于对应 raw request 的 `.input_tokens` 之和 |
| `T_r` | measured case wall seconds | `derived/cases.jsonl`: `.client.wall_time_seconds`；来自 `raw/case-events.jsonl` 的 end event |
| `Q_p/H_p` | 完整 priming phase 的 query/hit delta | `raw/cases/c001-r01/metrics-before.prom - raw/exposition/run-initial.prom` |
| `N_p/L_p` | priming 请求数/logical tokens | `raw/warmup-case-events.jsonl`；`raw/warmup-requests.jsonl` 成功记录及其 `.input_tokens` 之和 |
| `T_p` | 完整 priming phase wall seconds | `raw/warmup-case-events.jsonl` 的 end event `.wall_time_seconds` |
| `G` | allocated GPU count | `raw/server/server-command.txt` + `docs/environment/dgx-spark-inventory.private.md` |

`case_contract_fingerprint` 是 case contract 的标量 hash，不包含 metrics；counter 的 JSON 路径直接位于 `.runtime_counters`。

## 公式

对每个 concurrency `c`、repetition `r` 独立计算：

```text
U_post(c,r) = (Q_r - H_r) / N_r
U_incl(c,r) = [(Q_p - H_p) + (Q_r - H_r)] / N_r

C_post(c,r) = T_r × G × 1e6 / L_r
C_incl(c,r) = (T_p + T_r) × G × 1e6 / L_r
```

`U_*` 单位为 uncached prefill tokens/measured request；`C_*` 单位为 allocated GPU-s/1M measured logical prompt tokens。`C_*` 使用整个 request batch wall time，包含 prefill 与 decode，不是 prefill-only GPU 成本。

## Priming phase 输入

`run-initial.prom` 的 query/hit 均为 0；首个 measured case 的 `.before` 与其差值即完整 warm-up phase delta。

| Variant | `T_p` s | `N_p` | `L_p` | `Q_p` | `H_p` | `Q_p-H_p` |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 8.900308351 | 2 | 2,064 | 2,064 | 0 | 2,064 |
| Candidate | 8.788105967 | 2 | 2,064 | 2,064 | 1,024 | 1,040 |

## Repetition-level 重算结果

每个 measured case 都有 `N_r=16`、`L_r=16,592`、`Q_r=16,592`、`G=1`。表中成本保留 1 位小数。

| Variant | Case | `H_r` | `U_post` | `U_incl` | `C_post` | `C_incl` |
|---|---|---:|---:|---:|---:|---:|
| Baseline | C1 r1 | 0 | 1,037 | 1,166 | 4,097.3 | 4,633.7 |
| Baseline | C1 r2 | 0 | 1,037 | 1,166 | 3,933.4 | 4,469.8 |
| Baseline | C1 r3 | 0 | 1,037 | 1,166 | 3,933.1 | 4,469.5 |
| Baseline | C16 r1 | 0 | 1,037 | 1,166 | 440.6 | 977.0 |
| Baseline | C16 r2 | 0 | 1,037 | 1,166 | 441.0 | 977.4 |
| Baseline | C16 r3 | 0 | 1,037 | 1,166 | 445.1 | 981.6 |
| Candidate | C1 r1 | 16,368 | 14 | 79 | 3,848.5 | 4,378.1 |
| Candidate | C1 r2 | 16,384 | 13 | 78 | 3,865.7 | 4,395.3 |
| Candidate | C1 r3 | 16,384 | 13 | 78 | 3,937.0 | 4,466.7 |
| Candidate | C16 r1 | 16,368 | 14 | 79 | 259.5 | 789.1 |
| Candidate | C16 r2 | 16,384 | 13 | 78 | 206.7 | 736.4 |
| Candidate | C16 r3 | 16,384 | 13 | 78 | 270.0 | 799.6 |

按每项 metric 独立取 3 个 repetition 的 median：

| Concurrency | Variant | `U_post` | `U_incl` | `C_post` | `C_incl` |
|---|---|---:|---:|---:|---:|
| C1 | Baseline | 1,037 | 1,166 | 3,933.4 | 4,469.8 |
| C1 | Candidate | 13 | 78 | 3,865.7 | 4,395.3 |
| C16 | Baseline | 1,037 | 1,166 | 441.0 | 977.4 |
| C16 | Candidate | 13 | 78 | 259.5 | 789.1 |

## Candidate C16 r1 展开示例

```text
Q_r = 68,432 - 51,840 = 16,592
H_r = 66,528 - 50,160 = 16,368
U_post = (16,592 - 16,368) / 16 = 14
U_incl = [(2,064 - 1,024) + 224] / 16 = 79
C_post = 4.305275324 × 1e6 / 16,592 = 259.5
C_incl = (8.788105967 + 4.305275324) × 1e6 / 16,592 = 789.1
```

## 解读边界

- **Observed Fact**：上述 raw/derived 字段、逐 repetition 数值及 median 可直接重算。
- **Interpretation**：inclusive episode 表示“完整 2-request priming phase 摊销到随后 16 个 measured requests”，不是实际 run 总成本。
- C1 的 wall-time 成本主要受完整生成过程影响；prefix hit 改善不能自动推出同等比例的 allocated GPU-s 改善。
- 两侧 96 对请求中有 17 对 output token 数不同，因此 wall-time 成本差异的归因弱于 query/hit 与 prefill counter。
- Public projection 未保留 warm-up raw；priming-inclusive 重算目前依赖 private producer evidence。
