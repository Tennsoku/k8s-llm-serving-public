#!/usr/bin/env python3
"""Summarize the existing M3 probe/PVC runs from a full Tier B run directory."""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml


def capture(run, name):
    path = run / 'raw' / name / 'stdout.log'
    return yaml.safe_load(path.read_text())


def watch(run, name):
    path = run / 'raw' / name / 'stdout.log'
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            rows.append((row['observed_epoch'], row['watch']['object']))
        except (json.JSONDecodeError, KeyError) as error:
            raise ValueError(f'{path}:{number}: {error}') from error
    return rows


def container(pod):
    return pod['status']['containerStatuses'][0]


def ready_condition(pod):
    return next((c for c in pod['status'].get('conditions', [])
                 if c['type'] == 'Ready' and c['status'] == 'True'), None)


def utc(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def observed_time(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime('%H:%M:%S')


def smoke(run, suffix='request'):
    models = ['qwen3-8b', 'npc-merchant', 'npc-guard', 'quest-planner', 'lore-archivist']
    complete = 0
    for model in models:
        root = run / 'raw' / f'{model}-{suffix}'
        text = (root / 'stdout.log').read_text()
        response = json.loads(text[text.index('{'):])
        choice = response['choices'][0]
        complete += (text.startswith('HTTP/1.1 200 ')
                     and int((root / 'exit-code.txt').read_text()) == 0
                     and response['model'] == model
                     and choice['finish_reason'] == 'stop'
                     and bool(choice['message']['content']))
    return f'{complete}/{len(models)}'


def probe_summary(run, metadata):
    kind = metadata['workload']['probe']
    key = kind + 'Probe'
    pods = watch(run, 'pod-watch')
    failure_path = metadata['workload']['failure_path']
    injected = [(time, pod) for time, pod in pods
                if pod['spec']['containers'][0][key]['httpGet']['path'] == failure_path]
    uid = injected[0][1]['metadata']['uid']
    injected = [(time, pod) for time, pod in injected if pod['metadata']['uid'] == uid]
    running = [(time, pod) for time, pod in injected
               if pod['status'].get('containerStatuses')]
    started = next(time for time, pod in running if container(pod).get('started'))
    restarts = [container(pod)['restartCount'] for _, pod in running]
    events = [event for _, event in watch(run, 'event-watch')
              if event.get('involvedObject', {}).get('uid') == uid]
    failures = [event for event in events
                if event.get('reason') == 'Unhealthy'
                and event.get('message', '').startswith(kind.capitalize() + ' probe failed')]
    endpoints = [endpoint for _, obj in watch(run, 'endpoint-watch')
                 for endpoint in (obj.get('endpoints') or [])
                 if endpoint.get('targetRef', {}).get('uid') == uid]
    endpoint_ready = any(endpoint.get('conditions', {}).get('ready') for endpoint in endpoints)
    restored = capture(run, 'pod-after')
    restored_ready = ready_condition(restored)['lastTransitionTime']
    count = max(event['count'] for event in failures)
    first = min(event['firstTimestamp'] for event in failures)
    last = max(event['lastTimestamp'] for event in failures)
    rows = [
        ('注入 Pod UID', f'`{uid}`'),
        ('startup 成功（watch接收，UTC）', observed_time(started)),
        ('故障probe失败次数 / 时间段（UTC）', f'{count} / {first[11:19]}–{last[11:19]}'),
        ('注入Pod restartCount', f'{min(restarts)}→{max(restarts)}'),
        ('注入Pod曾为ready endpoint', str(endpoint_ready).lower()),
        ('恢复配置后的替换Pod Ready（UTC）', restored_ready),
        ('后补HTTP/选模/完整结束', smoke(run)),
    ]
    if kind == 'liveness':
        killing = next(event for event in events
                       if event.get('reason') == 'Killing'
                       and 'failed liveness probe' in event.get('message', ''))
        recovered = next(pod for _, pod in running
                         if container(pod)['restartCount'] > 0 and ready_condition(pod))
        rows.insert(4, ('kubelet重启事件 / 同UID重新Ready（UTC）',
                       f"{killing['lastTimestamp'][11:19]} / "
                       f"{ready_condition(recovered)['lastTransitionTime'][11:19]}"))
        finding = f'{count}次liveness失败后，同UID容器重启并重新Ready。'
        limits = ['仅一次故障重启，不推算长期可靠性。']
    else:
        finding = '故障readiness阻止新Pod入池，观察期间容器未重启。'
        limits = ['故障Pod从未Ready，未测试同一健康Pod因readiness失败被摘除。']
    limits.append('后补5个功能请求晚于观察窗口，缺同期Pod UID归属；不用于恢复时延。')
    evidence = ['raw/probe-inject.json', 'raw/pod-watch/stdout.log',
                'raw/event-watch/stdout.log', 'raw/endpoint-watch/stdout.log',
                'raw/pod-after/stdout.log', 'raw/*-request/{stdout.log,exit-code.txt}']
    return f'M3 {kind.capitalize()} Probe', finding, rows, limits, evidence


def pvc_values(run):
    pod = capture(run, 'pod-after')
    uid = pod['metadata']['uid']
    pods = [obj for _, obj in watch(run, 'pod-watch') if obj['metadata']['uid'] == uid]
    first_ready = next(obj for obj in pods if ready_condition(obj))
    ready = ready_condition(first_ready)['lastTransitionTime']
    created = pod['metadata']['creationTimestamp']
    main = container(pod)
    init = pod['status']['initContainerStatuses'][0]
    init_state = init['state']['terminated']
    return {
        'uid': uid, 'created': created, 'ready': ready,
        'create_ready': (utc(ready) - utc(created)).total_seconds(),
        'main_ready': (utc(ready) - utc(main['state']['running']['startedAt'])).total_seconds(),
        'init_seconds': (utc(init_state['finishedAt']) - utc(init_state['startedAt'])).total_seconds(),
        'restart': f"{init['restartCount']} / {main['restartCount']}",
        'init_exit': init_state['exitCode'],
    }


def pvc_summary(run, metadata):
    cold = metadata['experiment'] == 'model-cache-cold'
    values = pvc_values(run)
    init_name = 'init-log' if cold else 'init-follow-01'
    text = (run / 'raw' / init_name / 'stdout.log').read_text()
    if cold:
        seconds = re.search(r'marked complete after ([\d.]+)s', text).group(1)
        branch = f'复制并校验，日志耗时{seconds}s'
    else:
        if 'Warm model cache: skipping copy and byte comparison.' not in text:
            raise ValueError(f'{run}/raw/{init_name}: missing warm-cache branch')
        branch = '完成标记命中，跳过复制与逐字节比较'
    rows = [
        ('Pod UID', f"`{values['uid']}`"),
        ('Pod创建 / 首次Ready（UTC）', f"{values['created']} / {values['ready']}"),
        ('创建→Ready / main启动→Ready', f"{values['create_ready']:.0f}s / {values['main_ready']:.0f}s"),
        ('init state耗时（秒级记录）',
         '同秒' if values['init_seconds'] == 0 else f"{values['init_seconds']:.0f}s"),
        ('init/main restartCount / init exit', f"{values['restart']} / {values['init_exit']}"),
        ('缓存分支', branch),
        ('non-thinking HTTP/选模/完整结束', smoke(run, 'request-nothink' if cold else 'request')),
    ]
    finding = f"{'Cold' if cold else 'Warm'} PVC启动创建→Ready为{values['create_ready']:.0f}s，init/main均无重启。"
    limits = ['cold仅指目标PVC为空，源资产已在节点；不含下载，page cache未控制。',
              '无init/main cgroup内存曲线；节点内存不能归属为容器/GPU内存。']
    if cold:
        limits.append('初始5请求均触及32-token上限；后补non-thinking成功晚于启动窗口。')
    else:
        paired = run.parent / Path(metadata['paired_cold_run']).name
        other = pvc_values(paired)
        rows.append(('配对cold创建→Ready / 本轮差值',
                     f"{other['create_ready']:.0f}s / {other['create_ready'] - values['create_ready']:.0f}s"))
        limits.append('HTTP400缺对应客户端capture；watch路径曾复用，非零退出码无法唯一归属。')
    evidence = ['raw/pod-watch/stdout.log', 'raw/pod-after/stdout.log',
                f'raw/{init_name}/stdout.log', 'raw/workload-before/stdout.log',
                'raw/*-request*/{stdout.log,exit-code.txt}']
    if not cold:
        evidence.append(f"{paired.name}/raw/pod-{{watch,after}}/stdout.log（同级配对cold run）")
    return f"M3 PVC {'Cold' if cold else 'Warm'} Startup", finding, rows, limits, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path, help='Full run directory extracted from Tier B')
    parser.add_argument('--output', type=Path, help='Write Markdown; otherwise print it')
    args = parser.parse_args()
    try:
        metadata = yaml.safe_load((args.run / 'run.yaml').read_text())
        experiment = metadata['experiment']
        if experiment in ['readiness-failure-recovery', 'liveness-failure-recovery']:
            title, finding, rows, limits, evidence = probe_summary(args.run, metadata)
        elif experiment in ['model-cache-cold', 'model-cache-warm']:
            title, finding, rows, limits, evidence = pvc_summary(args.run, metadata)
        else:
            parser.error(f'Unsupported M3 experiment: {experiment}')
        lines = [f'# {title}', '', f'**Observed Fact**：{finding}', '',
                 '| 项目 | 结果 |', '|---|---|']
        lines.extend(f'| {name} | {value} |' for name, value in rows)
        lines.extend(['', '## 限制', ''])
        lines.extend(f'- {limit}' for limit in limits)
        lines.extend(['', '## 复核', '',
                      '以下路径相对Tier B内同名run；按Pod UID过滤watch，用对象时间计算Ready，watch时间仅表示client接收。'])
        lines.extend(f'- `{path}`' for path in evidence)
        lines.extend(['', '在仓库根目录执行（复核同名run的完整raw）：', '', '```bash',
                      f'python3 scripts/experiments/summarize-m3-lifecycle.py <tier-b-root>/{metadata["run_id"]}',
                      '```', ''])
        result = '\n'.join(lines)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result)
        else:
            print(result, end='')
    except (OSError, ValueError, KeyError, StopIteration, yaml.YAMLError) as error:
        parser.exit(1, f'{args.run}: {type(error).__name__}: {error}\n')


if __name__ == '__main__':
    main()
