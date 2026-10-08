# M3 单副本 K8s / Docker 对照

**Observed Fact**：两侧各完成 64/64 measured 请求，失败与 timeout 均为 0；另有各 16/16 warmup 成功。下表已从原始请求记录独立复算，与原 derived 一致。
**Interpretation**：结果支持同模型、负载下两套部署路径的单次并列观察。

## 请求指标（Observed Fact）

两侧同 pinned image、Qwen2.5-7B-Instruct BF16，60 input / 512 output tokens，temperature=0、seed=42、stream/include_usage、request-unique cache identity，C8、repetition=1。

| Measured 指标 | Docker | K8s |
|---|---:|---:|
| 成功 / 总请求 | 64 / 64 | 64 / 64 |
| TTFT p95 (ms) | 256.868 | 248.287 |
| TPOT p95 (ms) | 64.939 | 64.519 |
| E2E p95 (s) | 33.390 | 33.212 |
| Output throughput (tok/s) | 122.773 | 123.614 |

Measured wall time：Docker 266.898098s / K8s 265.084191s。K8s 实际 Pod 在 worker，GPU request=1、QoS=Burstable；末态 Running/Ready、restartCount=0。Pod created/scheduled→Ready 为140s，container started→Ready 为139s；Docker server start→health ready 为136.228s。

## 原始依据与复算

以下路径相对 Tier B archive 解压根目录；仓库保留 [Docker derived summary](../../20260927-m3-docker-comp-r01/derived/summary.json)。

- K8s：`20260927-m3-k8s-comp-r01/raw/measured-requests.jsonl` 与 `20260927-m3-k8s-comp-r01/raw/measured-events.jsonl`；预热读取同位置的 `warmup-requests.jsonl` / `warmup-events.jsonl`。
- 实际配置与启动：`20260927-m3-k8s-comp-r01/raw/pod-after/stdout.log`、`20260927-m3-k8s-comp-r01/raw/comparison-config/stdout.log`、`20260927-m3-k8s-comp-r01/raw/measured-client/command.txt`。
- Docker：`20260927-m3-docker-comp-r01/raw/requests.jsonl`、`20260927-m3-docker-comp-r01/raw/case-events.jsonl`、`20260927-m3-docker-comp-r01/raw/server/ready-time.txt`、`20260927-m3-docker-comp-r01/raw/server/server-command.txt`。

仓库根目录执行下例，将 archive 参数改为实际解压位置；Docker 用其 run ID，并将文件名改为 `case-events.jsonl` / `requests.jsonl`。R-7 分位数仅纳入成功请求，吞吐为成功 output tokens / measured case wall time，warmup 不合并。

```bash
PYTHONPATH=serving/vllm/benchmark python3 -B - /path/to/extracted/archive <<'PY'
import sys; from pathlib import Path
from benchmark_utils import read_jsonl, summarize_request_records
raw = Path(sys.argv[1]) / "20260927-m3-k8s-comp-r01/raw"
end = next(e for e in read_jsonl(raw / "measured-events.jsonl") if e["event_type"] == "end")
print(summarize_request_records(read_jsonl(raw / "measured-requests.jsonl"), end["wall_time_seconds"]))
PY
```

## 范围与限制

- 只有一个 C8 repetition；配置包含 C1 不代表执行过 C1，不推导稳定 tail latency、capacity 或统计显著收益。
- Docker client 位于 worker，经 loopback/bridge、`--ipc=host`；K8s client 位于 control plane，经跨节点 ClusterIP/containerd/probes，请求 ID 配置也不同。无法隔离 Kubernetes、网络、runtime 或 control-plane noise 的开销。
- K8s request_id_verified=false，缺与 Docker 对称的 runtime/system 曲线；启动早于采集开始，两侧起止事件和探测口径不同，不计算启动开销。
- 三个 watch exit=143、server follow exit=1 均保留主动 SIGTERM 记录；它们是采集器退出，不计为请求失败。
