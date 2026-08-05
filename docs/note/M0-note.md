# M0 Work Log

记录操作过程中的一些步骤和发现。本文是按时间记录的工作日志，早期“只有一台节点”等描述不代表当前状态；当前结论以 `docs/reviews/m0-review.md` 和 `docs/environment/` 下的基线文档为准。

---
建立仓库大体结构

现在只有一台spark点亮，第二台接入尚需要时间

尝试填写dgx-spark-inventory.md
- Firmware name是什么？ NVIDIA DGX Spark UEFI
    - Firmware version <- `hostnamectl`
- `free -h`的total Mem是121Gi，这是一个比较奇怪的数字，转成GB也不是128，这是Unified Mem吗？
    - 128,000,000,000 / 1024³ ≈ 119.2 GiB，再加上具体硬件容量表示方式和系统保留区域，显示约 121 GiB 并不异常。
- `lsblk`
    - loop0–loop22：Ubuntu Snap 软件包挂载的只读虚拟块设备，可以忽略。
    - `nvme0n1p2`真正挂载的盘

在Network这里挣扎了挺久，主要原因是没学过Network101，连interface的具体概念都不清楚。
- 在目前的spark架构上，存在3张网卡：
    - `enP7s7`：真正意义上的有线网卡，连接到Router / Switch，主要用于管理和LAN通信
    - `wlP9s9`：无线网卡，目前没有启用。
    - `enp1s0f1np1`：200G，ConnectX-7，NCCL数据传输网卡，p0/p1是两个端口，p0目前没有连接，p1连接到spark-b的p1。
    - MTU均为1500

开始落地CUDA smoke test。
- nvidia-smi可以正常显示GPU信息，不过spark是unified mem架构，显存显示这一套不支持。
- `ldconfig -p`检查CUDA依赖
- 做了一个简单的CUDA smoke test，运行正常。

然后开始测试各种镜像。
- 选用的镜像均为NGC Catalog下的官方镜像，为了生态一致性。
- 惊喜的是官方pytorch镜像里已经包含了NCCL, cuDNN和CUDA等库，可以通过smoke test
- 具体镜像列表参见[container-image-inventory.md](../environment/container-image-inventory.md)。总之这块比较顺利

在测试镜像过程中决定再给自己做一套kind lab练手。

**重要：** 在测试的过程中发现vLLM的实例直接拿满了所有显存，导致其他容器无法启动。原因是如果不加入`--gpu-memory-utilization`参数，vLLM会尝试标记所有显存为kv cache预留空间，unified memory架构下直接就拿满RSS上所有RAM了。在限制实例内存上限的同时，一定要记得同时限制vLLM的显存。

vLLM serve Qwen3-0.6B成功

在准备开始network测试时，得知spark-b已经成功接入。开始设置spark-b的相关配置，主要是ssh，然后修改原定计划开始加入对spark-b的iperf3测试。

开始进行NCCL测试。
- NCCL测试主要是为了验证两台spark之间的网络传输是否正常，尤其是NCCL的RDMA传输能力。
- 第一个block: 本地编译的nccl lib没有注入dynamic linker path，导致在spark上运行时找不到libnccl.so.2。路径写入`/etc/ld.so.conf.d/nccl.conf`后`ldconfig`解决
- 第二个block: core的OpenMPI是ompi4,默认使用tcp btl. 本地编译nv推荐的hpc-x ompi5后重新build test解决。
- 第三个block: 远端spark-b未配置相同的nccl和ompi环境。同步环境并在`.bashrc`中加入LD_LIBRARY_PATH后解决。
- 第四个block: spark-b的ssh配置不正确，导致无法通过ssh走通spark-b->spark-a。根因是nccl-test的mpi不仅需要管理通路的信任，还需要数据通路的信任，此前只设置了MGMT的ssh信任。通过在spark-b上设置DATA的ssh信任后解决。
- 未解决问题：因为当前NCCL是build from latest git source, MLX5的支持要求是MLX5-1.25，内核只到1.24，导致无法使用GDR和Spectrum-X插件。后续需要升级内核和MLX5驱动，或者使用MLX5-1.24的NCCL版本对齐支持
- 更新：MLX5-1.25的优化影响基本不大，首先GB10是unified mem架构，GPU和CPU通信已经通过NVlink，无需GDR；Spectrum-X多节点优化在目前仅有两台spark的情况下也不明显。后续可以考虑升级内核和MLX5驱动，但目前不会过多影响整体性能。

进入总结阶段，整理了M0的review文档和各个基线文档。删除了不再需要的测试残留，repo整体脱敏后publish。
