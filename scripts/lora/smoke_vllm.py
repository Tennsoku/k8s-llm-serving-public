#!/usr/bin/env python3
"""Single/static multi-adapter vLLM smoke for the private M2p guide, section 9."""

# 启动独立容器 -> health -> models -> 每个 adapter 首条 eval -> multi 时再混合 16 请求。
# 最后 logs/inspect -> stop；不训练、不复制权重、不运行性能 benchmark 或最终行为评测。
# 输入目录只读挂载；输出目录必须是新路径，失败也保留。停止后不自动 docker rm。

import argparse
import json
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep
from urllib import error as urlerror, request as urlrequest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lora_train import BASE_MODEL, ROLES, read_jsonl, write_jsonl

REPO = Path(__file__).resolve().parents[2]
URL = "http://127.0.0.1:8041"


def capture(output, name, command):
    # 复用已有 helper：command/stdout/stderr/exit-code 全部落盘，非零立即报错。
    result = subprocess.run(["bash", str(REPO / "scripts/experiments/capture-command.sh"),
                             str(output), name, "--", *command])
    if result.returncode:
        raise RuntimeError(f"{name} exited {result.returncode}; see {output / name}")
    return (output / name / "stdout.log").read_text(encoding="utf-8")


def get(url):
    # health 的连接失败是启动期观察，必须保留；models 的失败由调用方终止 smoke。
    status, body, error = None, None, None
    try:
        with urlrequest.urlopen(url, timeout=10) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
    except urlerror.HTTPError as exc:
        status, body, error = exc.code, exc.read().decode("utf-8", errors="replace"), str(exc)
    except OSError as exc:
        error = str(exc)
    return {"url": url, "http_status": status, "response_body": body, "error": error}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("single", "multi"), default="single")
    parser.add_argument("--image", required=True, help="Existing digest-pinned vLLM image; never pulled")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--adapter-dir", required=True, nargs="+", help="Directories in the same order as --adapter")
    parser.add_argument("--adapter", required=True, nargs="+", choices=ROLES)
    parser.add_argument("--cases", required=True, nargs="+", help="Eval files in adapter order; first 1/4 rows for single/multi")
    parser.add_argument("--output-dir", required=True, help="New raw/serving attempt directory")
    parser.add_argument("--container", required=True, help="Fresh container name; no existing container is replaced")
    args = parser.parse_args(argv)
    count = 1 if args.mode == "single" else 4
    if any(len(values) != count for values in (args.adapter, args.adapter_dir, args.cases)):
        raise ValueError(f"{args.mode} requires {count} aligned --adapter, --adapter-dir and --cases values")
    if args.mode == "multi" and set(args.adapter) != set(ROLES):
        raise ValueError("multi requires all four distinct adapters")
    model_dir = Path(args.model_dir).resolve(strict=True)
    if not model_dir.is_dir():
        raise ValueError("--model-dir must be a directory")
    mounts, modules, inputs = [], [], []
    for role, directory, path in zip(args.adapter, args.adapter_dir, args.cases):
        adapter_dir, cases = Path(directory).resolve(strict=True), Path(path).resolve(strict=True)
        if not adapter_dir.is_dir():
            raise ValueError(f"adapter directory required: {adapter_dir}")
        selected = read_jsonl(cases)[:count]
        if len(selected) != count or any(not isinstance(row, dict) or row.get("expected_role") != role
                or not isinstance(row.get("case_id"), str) or not isinstance(row.get("messages"), list) for row in selected):
            raise ValueError(f"{cases}: need {count} valid cases with expected_role={role}")
        target = "/adapter" if args.mode == "single" else f"/adapters/{role}"
        mounts.extend(["--mount", f"type=bind,src={adapter_dir},dst={target},readonly"])
        modules.append(f"{role}={target}")
        inputs.append((role, cases, selected))
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)

    # create 成功拿到 ID 后才取得该容器的管理权；后续失败也只停止这个 ID。
    # create/start 分开留痕，使端口冲突等 start 失败仍能保留 inspect 和日志。
    # 资源参数来自既有 M2 canonical 起点，不是性能最优值；不加入 speculative。
    container_id, exit_code = None, 1
    try:
        container_id = capture(output, "create", [
            "docker", "create", "--pull", "never", "--name", args.container,
            "--init", "--stop-signal", "SIGTERM", "--stop-timeout", "60",
            "--gpus", "all", "--ipc=host", "--memory", "64g", "-p", "127.0.0.1:8041:8041",
            "--mount", f"type=bind,src={model_dir},dst={BASE_MODEL},readonly",
            *mounts,
            "--label", "owner=tensoku",
            "--entrypoint", "vllm", args.image,
            "serve", BASE_MODEL, "--host", "0.0.0.0", "--port", "8041", "--dtype", "bfloat16",
            "--served-model-name", "qwen3-8b", "--generation-config", "vllm",
            "--gpu-memory-utilization", "0.25", "--max-model-len", "8192",
            "--enable-lora", "--lora-modules", *modules,
            "--max-loras", str(count), "--max-cpu-loras", str(count), "--max-lora-rank", "8"
        ]).strip()
        capture(output, "start", ["docker", "start", container_id])
        started = monotonic()
        # 900 s ready budget，180 s 间隔；每次失败和响应都即时 flush，而不是只存最终 200。
        with (output / "health.jsonl").open("x", encoding="utf-8") as health:
            while True:
                observation = get(f"{URL}/health")
                observation["elapsed_seconds"] = monotonic() - started
                health.write(json.dumps(observation, ensure_ascii=False) + "\n")
                health.flush()
                print(f"health: status={observation['http_status']} elapsed={observation['elapsed_seconds']:.1f}s", flush=True)
                if observation["http_status"] == 200 and not observation["error"]:
                    break
                remaining = 900 - (monotonic() - started)
                if remaining <= 0:
                    raise RuntimeError("vLLM did not become ready within 900 seconds")
                sleep(min(180, remaining))

        observed = get(f"{URL}/v1/models")
        write_jsonl(output / "models.jsonl", [observed])
        if observed["http_status"] != 200 or observed["error"]:
            raise RuntimeError("GET /v1/models failed; see models.jsonl")
        model_ids = {item["id"] for item in json.loads(observed["response_body"])["data"]}
        if not {"qwen3-8b", *args.adapter} <= model_ids:
            raise RuntimeError(f"base/adapter missing from /v1/models: {sorted(model_ids)}")

        # 每份先在当前池中单独发首条 eval；任何一步失败都不进入后续 mixed 阶段。
        # tuple: capture 名、输入文件、请求数、并发、固定 model（None 表示逐行选）、raw 文件名。
        phases = [("score" if count == 1 else f"score-{role}", cases, 1, 1, role,
                   "response.jsonl" if count == 1 else f"response-{role}.jsonl") for role, cases, _ in inputs]
        if args.mode == "multi":
            # round-robin 输入：merchant-000, guard-000, planner-000, archivist-000,
            # merchant-001, ...，每角色 4 条，均来自开发段；不触碰后 12 条独立评测样本。
            # 不能把四个完整文件直接给 scorer 再 limit=16：那会全取第一个文件。
            mixed = output / "mixed-cases.jsonl"
            write_jsonl(mixed, [rows[index] for index in range(4) for _, _, rows in inputs])
            phases.append(("score-mixed", mixed, 16, 4, None, "response-mixed.jsonl"))
        keys = ("http_success", "model_selection_pass", "json_valid", "no_think_block")
        for name, cases, total, concurrency, model, raw_name in phases:
            # 复用 scorer：temperature=0、enable_thinking=false、max_tokens=128。
            # mixed 不传 --model，由每行 expected_role 选 adapter；并发是客户端上限，不保证 GPU 同步执行。
            capture(output, name, [sys.executable, "-B", str(Path(__file__).with_name("lora_score.py")),
                    "--backend", "vllm", "--endpoint", f"{URL}/v1/chat/completions",
                    "--cases", str(cases), "--limit", str(total), "--concurrency", str(concurrency),
                    *(["--model", model] if model else []), "--raw-output", str(output / raw_name)])
            rows = read_jsonl(output / raw_name)
            # exit 0 只代表无运行异常；此处要求所有请求联合通过，不过滤失败。
            # fields/role 仍留在 raw 和 scorer stdout，按已有行为 gate 判断，不在此加新门槛。
            if len(rows) != total or any(row.get("error") or not all(row.get(key) for key in keys) for row in rows):
                raise RuntimeError(f"{name} failed the joint gate; see {raw_name}")
        exit_code = 0
    except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
        print(f"smoke_vllm: {exc}", file=sys.stderr)
    finally:
        if container_id:
            # 清理期间单步失败仍记录并继续采证/停止；不访问其他容器，不自动 rm。
            for name, command in (
                ("logs", ["docker", "logs", "--timestamps", container_id]),
                ("inspect-before-stop", ["docker", "inspect", container_id]),
                ("stop", ["docker", "stop", "--time", "60", container_id]),
                ("inspect-after-stop", ["docker", "inspect", container_id]),
            ):
                try:
                    capture(output, name, command)
                except (OSError, RuntimeError) as exc:
                    exit_code = 1
                    print(f"smoke_vllm cleanup: {exc}", file=sys.stderr)
            print(f"Container retained for inspection: {container_id}", flush=True)
    print(f"{'PASS' if exit_code == 0 else 'FAIL'} {args.mode}-adapter smoke; evidence: {output}")
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("smoke_vllm: interrupted", file=sys.stderr)
        sys.exit(130)
    except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
        print(f"smoke_vllm: {exc}", file=sys.stderr)
        sys.exit(2)
