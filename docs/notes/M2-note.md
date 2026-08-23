# M2 Work Log

记录操作过程中的一些步骤和发现。本文是按时间记录的工作日志。

--- 

在正式动手前需要扩张一下 M1 来的 benchmark runner scope，showcase 页面在复用 run analysis / comparison viewer 的同时也需要加入新的 contract。
但是 showcase 页面好像越堆越多了。需要拆分成 milestone-specific 的 scope，以防后面几个 milestone 的 scope 也都堆在一起，导致 js 越来越长。
benchmark runner 长度也有点过于雷霆了，之前就已经列为技术债，是不是应该动手救一下。
先分两个小时试试看吧。

稍微整理了一下。但是感觉 runner 已经很难再精简了，主要是 lifecycle/telemetry 可能需要拆分一下。后面再做。

一个关于 16b 浮点精度的笔记：
FP16 
- 1 sign + 5 exponent + 10 mantissa bits
- 高精度但动态范围小 → 适合推理。

BF16
- 1 sign + 8 exponent + 7 mantissa bits
- 精度较低但动态范围大 → 适合训练

在进行过程中网络环境发生了小幅变化，导入了 Nvidia Cluster Assistant 的配置，CX7 的两端在同一子网下。
在测试中发现之前从来没有动过 MTU 的配置，linux 默认的 MTU 是1500，但是 CX7 的 RoCE 接口的 MTU 上限是4096。
如果不修改 MTU 的话，NCCL 的带宽会下降到90G左右。
而且 M0 开始其实就出现了因为 package size 不够，TCP 传输存在 retrans 和 rx_out_of_buffer 的情况。
修改 MTU 之后可以达到110G左右。

把 MTU 的设置固定在9000了。

Compatibility check 中发现 Spec Decoding 的 draft 模型和 target 模型在当前 vLLM 版本下强制要求 vocab size 一致，否则会 validation failed。Qwen2.5-7B 的 vocab size 和 Qwen2.5-0.5B 的不一致。
最新版本 v0.27.0 的 vLLM 已经更新了 `--enable-heterogeneous-vocab` 参, 不过不打算因为这个事情去更换已经固定的 vLLM image digest。
研究了一下 Qwen3-0.6B 和 Qwen3-8B 是一组好的实验组。SD 就用这个跑吧。
