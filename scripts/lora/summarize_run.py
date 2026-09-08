#!/usr/bin/env python3
"""Export the initial/final M2p run layouts as UNSANITIZED offline candidates."""

# 不启动模型，不改 private raw，不判断是否获准公开，也不自动修 run.yaml。
# initial: 旧模板 + merchant 40/80-step 诊断；final: 四 adapter + serving/eval。
# 原评分 JSONL 是生成结果，不是权重。权重、完整 telemetry 留在原始目录。
# 用法和 metadata 补写指引：docs/experiments/README.md 的 M2p 小节。

import argparse
import json
import sys
from pathlib import Path

from lora_train import ROLES, read_jsonl


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def merged(source, paths):
    # 例如同一个 case 在 single 与 mixed 各出现一次；source 保留阶段及行序来源。
    return b"".join(encoded({**row, "source": str(path.relative_to(source))})
                    for path in paths for row in read_jsonl(path))


def log_section(source, path, content=None):
    # bytes 拼接不改换行、stderr 或 traceback；来源标记不属于原始输出。
    body = path.read_bytes() if content is None else content
    return f"\n--- {path.relative_to(source)} ---\n".encode() + body + b"\n"


def build_bundle(source, phase):
    source = Path(source)
    if phase not in ("initial", "final"):
        raise ValueError("phase must be initial or final")
    output = {"run.yaml": (source / "run.yaml").read_bytes()}
    summary = {"training": {}, "serving": {}, "telemetry": {"by_attempt": {}}}
    runtime, failures, exit_codes = [], [], {}
    # 读取所有 capture 的结果，包括 environment 的真实 non-zero，不能只挑训练成功项。
    for command in sorted((source / "raw").rglob("command.txt")):
        folder = command.parent
        rc = int((folder / "exit-code.txt").read_text().strip())
        exit_codes[str(folder.relative_to(source))] = rc
        files = [folder / name for name in ("command.txt", "stdout.log", "stderr.log", "exit-code.txt")]
        contents = {path.name: path.read_bytes() for path in files}
        if rc:
            failures.extend(log_section(source, path, contents[path.name]) for path in files)
        runtime.extend(log_section(source, folder / name, contents[name])
                       for name in ("command.txt", "exit-code.txt"))
        if rc:
            continue  # 失败 stdout/stderr 全量保存在 failures.log，不重复复制。
        runtime.append(log_section(source, folder / "stderr.log", contents["stderr.log"]))
        # 训练数值和评分结果另有 JSONL；保留 environment、server log、health/models。
        if folder.parent.name == "environment" or folder.name in ("logs", "health", "models"):
            body = contents["stdout.log"]
            if folder.name in ("train-image", "vllm-image"):
                # 不导出 docker image inspect 中不相关的完整 Env/构建历史。
                body = encoded([{key: item[key] for key in ("Id", "RepoDigests", "Architecture", "Os")}
                                for item in json.loads(body)])
            runtime.append(log_section(source, folder / "stdout.log", body))

    datasets = [source / f"raw/datasets/{role}.{split}.jsonl"
                for role in ROLES for split in ("train", "eval")]
    output["raw/datasets.jsonl"] = merged(source, datasets)
    attempts = (["compat-train", "npc-merchant-s040", "npc-merchant-s080"] if phase == "initial"
                else [f"{role}-s080" for role in ROLES])
    training = []
    for attempt in attempts:
        folder = source / "raw/training" / attempt
        rc = exit_codes[str(folder.relative_to(source))]
        path = folder / "stdout.log"
        # stdout 前面含 Python repr 的逐步日志，只有成功运行的末行是完整 JSON。
        metrics = json.loads(path.read_text().splitlines()[-1]) if rc == 0 else None
        record = {"attempt": attempt, "source": str(path.relative_to(source)), "exit_code": rc, "metrics": metrics}
        training.append(record)
        values = metrics or {}
        item = {key: values.get(key) for key in
                ("max_steps", "logical_tokens", "wall_seconds", "logical_tokens_per_second")}
        losses = [entry["loss"] for entry in values.get("log_history", []) if "loss" in entry]
        item.update(source=record["source"], exit_code=rc, final_logged_loss=losses[-1] if losses else None)
        summary["training"][attempt] = item
    output["raw/training-metrics.jsonl"] = b"".join(encoded(row) for row in training)

    # 采样窗口包括 train() 外围；max 是所采样值的最大值，不是训练净增量。
    summary["telemetry"]["semantics"] = {
        "window_max": "max of non-null samples; null means no available measurement",
        "container_nvml_process_gpu_memory_used_bytes": "container GPU-process sum, not dedicated VRAM or training increment",
        "cgroup_memory_peak_bytes": "container lifetime high-water mark, may predate this attempt",
        "recompute": "full raw/telemetry JSONL required; time series are not in this candidate",
    }
    for attempt in (name for name in attempts if name != "compat-train"):
        path = source / f"raw/telemetry/{attempt}.jsonl"
        rows = read_jsonl(path)
        result = dict(line.split("=", 1) for line in Path(f"{path}.result").read_text().splitlines() if line)
        codes = {key: int(result[key]) for key in ("train_rc", "telemetry_rc")}
        for suffix in ("command.txt", "stdout.log", "stderr.log", "result"):
            sidecar = Path(f"{path}.{suffix}")
            section = log_section(source, sidecar)
            runtime.append(section)
            if any(codes.values()):
                failures.append(section)
        failed = [row for row in rows if row["sample_success"] is not True or row["errors"]]
        if failed:
            failures.append(log_section(source, path, b"".join(encoded(row) for row in failed)))
        item = {"source": str(path.relative_to(source)), "samples": len(rows),
                "successful_samples": sum(row["sample_success"] is True for row in rows),
                "failed_samples": len(failed), "exit_codes": codes,
                "first_timestamp_utc": rows[0]["timestamp_utc"], "last_timestamp_utc": rows[-1]["timestamp_utc"],
                "gpu_fb_memory_status": sorted({row["gpu_fb_memory_status"] for row in rows}),
                "window_max": {}, "valid_samples": {}}
        for key in ("container_nvml_process_gpu_memory_used_bytes", "cgroup_memory_current_bytes",
                    "cgroup_memory_peak_bytes", "gpu_memory_used_mib"):
            values = [row[key] for row in rows if row[key] is not None]
            item["window_max"][key] = max(values) if values else None
            item["valid_samples"][key] = len(values)
        # OOM counters 是累计量；首末值和差值并列保留，不把历史非零误报为本次 OOM。
        item["memory_events"] = {}
        for key in ("cgroup_memory_events_oom_total", "cgroup_memory_events_oom_kill_total"):
            first, last = rows[0][key], rows[-1][key]
            item["memory_events"][key] = {"first": first, "last": last,
                                           "delta": last - first if first is not None and last is not None else None}
        summary["telemetry"]["by_attempt"][attempt] = item

    if phase == "initial":
        for attempt in attempts[1:]:
            path = source / f"raw/score/{attempt}.peft.jsonl"
            output[f"raw/{path.name}"] = path.read_bytes()
        path = source / "raw/score/npc-merchant-s080/diagnostic-20260907.jsonl"
        output[f"raw/{path.name}"] = path.read_bytes()
        summary["serving"] = {"status": "not_run"}
    else:
        output["raw/peft-development.jsonl"] = merged(source,
            [source / f"raw/score/{attempt}/peft-raw.jsonl" for attempt in attempts])
        for name in ("adapters", "base"):
            output[f"raw/{name}.jsonl"] = (source / f"raw/serving/behavior-01/{name}.jsonl").read_bytes()
        # 行为 gate 仍归 lora_score.py；这两个既有文件原样复用，不另建第二份评分。
        for name in ("behavior-01.jsonl", "behavior-matrix-01.csv"):
            output[f"derived/{name}"] = (source / "derived" / name).read_bytes()
        smoke_paths = []
        for phase_name in [*(f"single-{role}-01" for role in ROLES), "multi-01", "behavior-01"]:
            folder = source / "raw/serving" / phase_name
            prefix = str(folder.relative_to(source)) + "/"
            item = {"capture_exit_codes": {key[len(prefix):]: rc for key, rc in exit_codes.items() if key.startswith(prefix)}}
            if phase_name == "behavior-01":
                models = json.loads((folder / "models/stdout.log").read_bytes())
                item["behavior_summary"] = "derived/behavior-01.jsonl"
                paths = []
            else:
                model_rows = read_jsonl(folder / "models.jsonl")
                observation = model_rows[-1]
                item["models_http_status"] = observation["http_status"]
                models = json.loads(observation["response_body"]) if observation["http_status"] == 200 else {"data": []}
                for name in ("models.jsonl", "health.jsonl"):
                    runtime.append(log_section(source, folder / name))
                paths = ([folder / "response.jsonl"] if phase_name.startswith("single-") else
                         [*(folder / f"response-{role}.jsonl" for role in ROLES), folder / "response-mixed.jsonl"])
            item["registered_models"] = [model["id"] for model in models["data"]]
            # State 原样保留：正常 stop 后 Running=false/ExitCode=0 不是运行失败。
            for moment in ("before-stop", "after-stop"):
                path = folder / f"inspect-{moment}/stdout.log"
                inspection, = json.loads(path.read_bytes())
                state = {"State": inspection["State"], "RestartCount": inspection["RestartCount"]}
                item[moment.replace("-", "_")] = state
                runtime.append(log_section(source, path, encoded(state)))
            item["response_checks"] = {}
            for path in paths:
                rows = read_jsonl(path)
                # compatibility counts 不含 correct_role；正式行为结果有单独的 owner。
                item["response_checks"][path.name] = {"rows": len(rows), **{
                    key: sum(row.get(key) is True for row in rows)
                    for key in ("http_success", "model_selection_pass", "json_valid", "no_think_block")}}
            smoke_paths.extend(paths)
            summary["serving"][phase_name] = item
        output["raw/smoke-responses.jsonl"] = merged(source, smoke_paths)
    output["raw/runtime.log"] = b"".join(runtime)
    if failures:
        output["raw/failures.log"] = b"".join(failures)
    output["derived/run-summary.json"] = encoded(summary)
    return output


def export_run(source, destination, phase):
    source, destination = Path(source).resolve(strict=True), Path(destination).resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("source and destination must not overlap")
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    # 先完成输入读取/解析；缺失 capture 或 malformed JSON 不留下看似完整的导出目录。
    bundle = build_bundle(source, phase)
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in bundle.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(content)
    return {"files": len(bundle), "bytes": sum(map(len, bundle.values())), "destination": str(destination)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path, help="new, private candidate directory; never overwritten")
    parser.add_argument("--phase", required=True, choices=("initial", "final"))
    args = parser.parse_args(argv)
    result = export_run(args.run_dir, args.output_dir, args.phase)
    print(json.dumps(result, sort_keys=True))
    print("UNSANITIZED candidate only; run.yaml copied unchanged. Review metadata/privacy before any git add.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"summarize_run.py: {exc}", file=sys.stderr)
        sys.exit(2)
