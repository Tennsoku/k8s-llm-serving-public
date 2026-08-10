# 一些关于 内存占用的观察和理解碎片

Lab1中，mem采集数据按每个指标分别取峰值后：
| 指标 | B max32 | B max128 | 差异 |
|---|---:|---:|---:|
| 运行前 host used | 74.064 GB | 74.228 GB | 0.164 GB |
| host used 最大采样值 | 96.457 GB | 96.583 GB | 0.127 GB |
| cgroup 最大采样值 | 3.286 GB | 3.321 GB | 0.035 GB |
| CUDA free after load | 3.14 GiB | 3.22 GiB | 接近 |
| vLLM KV-cache pool | 15.31 GiB | 15.16 GiB | 接近 |

## 约 20 GiB 到底是什么？

它主要是每次 vLLM engine 初始化时预留的内存

模型权重：约 0.93 GiB
CUDA Graph pool：约 0.51–0.52 GiB
KV-cache pool：约 15.2 GiB
其余 CUDA/runtime、workspace 和 profiling allocation
CUDA-visible free memory 从约 23 GiB 降到约 3 GiB

## cgroup 只看到约 3.3 GB
DGX Spark 的 CPU 和 iGPU 物理上共享 128 GB LPDDR5x，这是 UMA；但“共享物理内存”不等于“所有分配都使用同一套 Linux cgroup 记账”。
Linux memory.current 主要统计被 charge 到该 cgroup 的匿名内存、page cache、部分 kernel structures 和 socket buffers；内核文档也明确说明这种覆盖并非完全严密。[Linux cgroup v2 memory controller](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html)

从数据可以推断：
- Python、tokenizer、CPU staging buffer、普通匿名内存等被计入 container cgroup；
- CUDA/驱动管理的那部分 unified GPU allocation 没有以同样规模计入 memory.current；
- host free 能看到物理 DRAM available 的下降；
- torch.cuda.mem_get_info() 能看到 CUDA 管理视角的 pool；
- 三者不是同一个 accounting domain

NVIDIA 也明确指出 Spark 的 UMA memory reporting 存在特殊边界，nvidia-smi 不支持传统 framebuffer usage，而 cudaMemGetInfo 也不能反映所有可通过 swap 回收的 DRAM。[DGX Spark known issues](https://docs.nvidia.com/dgx/dgx-spark/known-issues.html)

## KV-cache pool 的Token size

vllm的gpu_worker.py:508和kv_cache_utils.py:2146会产出日志：
```
Available KV cache memory: 15.31 GiB
GPU KV cache size: 1,338,016 tokens
```
可以通过计算
```
15.31 GiB KV cache / 1,338,016 token capacity
≈ 12.0 KiB/token
```
可以跳过model的详细维度计算，直接用这个比例来估算KV-cache pool的token容量。
