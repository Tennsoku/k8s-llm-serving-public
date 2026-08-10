# vLLM Runtime

## Scope

该目录保存后续 Serving 使用的最小 vLLM runtime 配置和启动入口。

Lab exploratory implementations 保留在 `labs/vllm-basics/`。

## Runtime Execution Model

Model initialization
→ request input
→ tokenization
→ scheduling
→ prefill
→ KV cache
→ decode
→ sampling
→ output

## Prefill

将输入prompt tokenize后建立initial KV cache state。
随input length增长，KV cache的内存大小也会显著增加。
prefill阶段的时间是TTFT的最主要factor之一。

## Decode

在prefill结束产生第一个output token后，根据之前的KV cache state和当前token的embedding，计算下一个token的logits。
在持续decode阶段持续更新KV cache。根据输入的output length决定时间和内存占用。但是max_tokens只是上限，实机output仍会在
遇到EOS token时提前结束。

## KV Cache

保存历史 attention K/V state，随 active sequence 和 sequence length 增长。
inference capacity 的关键资源，内存的主要消费者。

## PagedAttention

将KV cache分为多个page，按需要加载到GPU memory，设计思路近似physical memory的paging机制。
与之相似，也会有bulk allocation和fragmentation问题。

## Scheduling

在多prompt、多client、多engine的情况下，vLLM runtime需要合理调度prefill和decode阶段的execution，
最大化GPU utilization和吞吐量。prefill是memory intensive，decode是compute intensive。
不同的prompt shape和max_tokens会影响prefill和decode的时间和内存占用。
Scheduling策略也会影响TTFT。

## Lab 1 Observations

链接：
../../labs/vllm-basics/lab1-offline-inference/observations.md

## Current Boundaries

当前尚未覆盖：
- HTTP serving
- concurrent clients
- TTFT benchmark
- runtime metrics
- capacity benchmark
- Kubernetes