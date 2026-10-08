# M3 Kustomize 多 adapter 共池 smoke

**Observed Fact**：同一 worker Pod 加载4个真实 LoRA；各 adapter 的单独请求和 C4 mixed 请求共32次，HTTP与逐请求选模均通过。
**Interpretation**：结果支持 Kustomize 重放后 multi-LoRA 共池及请求显式指定 adapter 的功能路径。

## 请求结果（Observed Fact）

模型为 Qwen3-8B，启用 LoRA，`max-loras=4`、`max-cpu-loras=4`、`max-lora-rank=8`。单 adapter 为C1、各4个case；mixed 为C4、16个case，均属合成 development 数据。

| Adapter | 单独 HTTP / 选模 | Mixed HTTP / 选模 | 单独 / mixed 角色正确 |
|---|---|---|---|
| npc-merchant | 4/4 · 4/4 | 4/4 · 4/4 | 3/4 · 3/4 |
| npc-guard | 4/4 · 4/4 | 4/4 · 4/4 | 4/4 · 4/4 |
| quest-planner | 4/4 · 4/4 | 4/4 · 4/4 | 4/4 · 4/4 |
| lore-archivist | 4/4 · 4/4 | 4/4 · 4/4 | 4/4 · 4/4 |

32条记录均 HTTP 200、requested_model=returned_model、model_selection_pass=true；角色正确共30/32。Pod 最终 Ready，restartCount=3，lastState 为 exitCode=1 / Error。

## 原始依据与复核

以下路径相对 Tier B archive 解压根目录。

- 打包输入及实际 Pod：`20260920-m3-kustomization-r01/raw/rendered/stdout.log`、`20260920-m3-kustomization-r01/raw/pod-after/stdout.log`；模型列表及服务日志位于同 run 的 `raw/models/stdout.log`、`raw/server-log/stdout.log`。
- 单 adapter：`20260920-m3-kustomization-r01/raw/npc-merchant-smoke.jsonl`、`20260920-m3-kustomization-r01/raw/npc-guard-smoke.jsonl`、`20260920-m3-kustomization-r01/raw/quest-planner-smoke.jsonl`、`20260920-m3-kustomization-r01/raw/lore-archivist-smoke.jsonl`。
- Mixed：`20260920-m3-kustomization-r01/raw/mixed-smoke.jsonl`；输入数据为 `20260920-m3-kustomization-r01/raw/mixed-cases.jsonl`，实际C4命令见 `20260920-m3-kustomization-r01/raw/mixed-request/command.txt`。

逐行计数上述五个 smoke JSONL 的 http_status/http_success、requested_model/returned_model、model_selection_pass 和 correct_role，可重算表格；需复用评分口径时读取现有 `scripts/lora/lora_score.py`。

## 范围与限制

- 本轮只证明恢复后的serving功能；重启计数为3，仅最近一次退出码为1有直接记录，前两次退出码及各次原因未记录。
- 仅小型合成 development smoke；npc-merchant两条角色不符保留，HTTP/选模成功不证明语义全通过、泛化质量或性能。
