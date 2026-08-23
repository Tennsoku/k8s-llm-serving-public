# Inference相关

TTFT - Time to First Token, 模型从接收到请求到生成第一个 token 的时间，通常用于衡量模型的响应速度。

TPOT - Time per Output Token，模型生成每个 token 所需的时间，通常用于衡量模型的吞吐能力。

ITL - Inter-Token Latency，相邻输出 token 之间的延迟, 在大多数情况下，ITL = TPOT。

# Distributed Training / Inference 相关

## DDP

- Distributed Data Parallel，分布式数据并行训练
- 每个进程维护一个**完整模型**副本。
- 每个进程处理不同的数据分片，独立完成前向与反向传播；反向传播过程中，各参数对应的梯度通常通过 All-Reduce 聚合，使所有模型副本保持一致。
- 优点：提升吞吐量，缺点：多个模型副本开销大，如果模型很大一张GPU放不下就没有意义

## FSDP

- Fully Sharded Data Parallel，完全分片数据并行训练
- 将模型的参数、梯度和优化器状态分片到不同的 GPU 上，从而减少每个 GPU 的内存占用。
- 在执行某个FSDP管理单元或某一组层之前，通过**All-Gather**临时重建该单元所需的完整**参数**；计算完成后释放非本地参数分片。反向阶段则再次收集所需参数，并通过Reduce-Scatter聚合和重新分片**梯度**。（先Reduce，再Scatter）
- 优点：节省显存，缺点：通信开销大

## TP

- Tensor Parallel，张量并行训练
- 将模型的单个层的参数分割到多个 GPU 上进行计算，最后通过All-Reduce或者All-Gather通信操作来聚合结果
- Row Parallel或者Column Parallel会不同，Row - All-Reduce/Reduce-Scatter，Column - All-Gather或者局部拼接，甚至不拼直接传
- 优点：有效切分巨大模型，缺点：对网络要求高，更高频，对延迟极度敏感，所以往往严格要求同一节点、同一NVLink/NVSwitch高速互联域内的 GPU 进行通信，跨机通信会严重影响性能。

## PP

- Pipeline Parallel，流水线并行训练。
- 将模型按层划分为多个 Pipeline Stage，并将不同 Stage 部署到不同设备或设备组上执行。每个 Stage 通常包含若干连续的模型层。
- 对某个 Micro-Batch 而言，后续 Stage 必须等待前一 Stage 生成其输入 Activation；与此同时，前一 Stage 可以继续处理后续 Micro-Batch，从而形成流水线并行。
- 这一机制与 CPU instruction pipeline 在分阶段执行、流水线填充和 Stall 方面较为相似，但 PP 流水线中流动的是不同 Micro-Batch 的模型计算，而不是不同 CPU 指令。
- 需要合理划分各 Pipeline Stage，使每个 Stage 的计算时间、参数量和显存压力尽可能接近。稳态吞吐通常受最慢 Stage 限制，Stage 不平衡会导致其他 Stage 等待。
- 关键词：Pipeline Bubble，流水线气泡。流水线在启动时需要逐步填充，在结束时需要逐步排空，因此天然存在无法完全消除的空闲区域。Stage 不平衡、Micro-Batch 数量不足和调度依赖会进一步扩大 Bubble。
- 相邻 Stage 之间通常通过点对点 Send/Recv 通信：前向传播时传递 Activation，反向传播时传递 Activation Gradient。若 PP 与 DP 或 TP 组合，系统中还会额外出现 All-Reduce、All-Gather、Reduce-Scatter 等 Collective 通信。
- 优点：能够沿模型深度切分参数和计算，适合深度较大、层数较多且可划分为均衡 Stage 的模型。
- 缺点：存在 Pipeline Bubble、Stage Balance、Micro-Batch 调度、Activation 显存和跨 Stage 通信等额外复杂度。

## MoE

- Mixture of Experts，专家混合模型
- 是架构不是训练方式，通常和TP、PP结合使用
- 在传统Transformer的部分Dense FFN层中，用多个并行Expert FFN替代单个FFN；Router针对每个Token选择Top-k个Expert，因此不同Token会激活不同的参数子集。
- 需要一个路由器（Router）来决定每个输入应该由哪些专家处理，依然需要Load Balancing来避免某些专家过载，而其他专家空闲。
- 优点：总参量增长不会显著增加计算量，缺点：路由器和Load Balancing的设计复杂，通信开销大。

## EP
- Expert Parallel，专家并行训练
- 将不同Expert参数部署在不同GPU或进程上，使各设备负责一部分Experts；Token根据Router结果被发送到持有目标Expert的设备执行计算。
- MoE的实现方式
- 需要通过All-to-All通信来同步，和All-Gather和All-Reduce不同，All-to-All通信是指每个GPU都需要与其他所有GPU进行通信，是Multi-to-Multi通信，不是Multi-to-One。随着Expert Parallel规模扩大，通信参与方、网络竞争和小消息调度复杂度都会增加，但通信数据量并非必然指数增长。
- 基于MoE的额外优点：将大量Expert参数和Expert计算分散到多个GPU，使大规模MoE层能够突破单卡容量限制。缺点：同MoE

## ZeRO
- Zero Redundancy Optimizer，零冗余优化器
- 将模型的参数、梯度和优化器状态分片到不同的 GPU 上，从而减少每个 GPU 的内存占用。
- 通过分片和通信操作来实现参数的更新和同步。
  - ZeRO-1：优化器状态分片，通信变化较小
  - ZeRO-2：梯度通过Reduce-Scatter分片
  - ZeRO-3：参数需要按需All-Gather，梯度Reduce-Scatter
- FSDP Full Shard与ZeRO-3最接近。ZeRO通过Stage 1/2/3提供逐级分片策略；FSDP则是PyTorch原生的参数分片方案，其FULL_SHARD模式与ZeRO-3概念上接近。两者实现机制和生态能力有所不同。
- 优点：节省显存，缺点：通信开销大

| 方法            | 分片内容                                  |
| --------------- | ----------------------------------------- |
| ZeRO Stage 1    | Optimizer States                          |
| ZeRO Stage 2    | Optimizer States + Gradients              |
| ZeRO Stage 3    | Optimizer States + Gradients + Parameters |
| FSDP FULL_SHARD | Parameters + Gradients + Optimizer States |

## AFD
- Activation - FFN Disaggregation
- 将Transformer中FFN层的计算拆分为两个阶段。Activation阶段负责生成FFN的输入激活，而FFN阶段则执行实际的前馈神经网络计算。
- 实际是Decode层的再拆分，甚至可以和P/D Disaggregation结合使用，形成更细粒度的流水线。
  ```
  Prefill
  Decode:
    Attention | FFN

  Decode
    │
    ├── Attention → memory/KV-heavy
    │
    └── FFN/MoE   → compute/expert-heavy
  ```
- 适合和MoE结合使用，因为FFN最后还是需要在Attention层上聚合进行下一个layer的计算，独立使用需要搭建一整套额外的通信层，而MoE天然需要使用这个通信层。
- Attention pool 和 Expert pool 最优的 GPU 数量、batch size、并行策略甚至硬件类型都可能完全不同。这也是 AFD 真正想榨出来的性能来源。（同理P/D）

## 增补：通信方式
- All-Reduce:    多方聚合，所有方得到相同结果
- All-Gather:    多方收集，所有方得到完整数据
- Reduce-Scatter: 聚合后分片
- All-to-All:    每一方向每一方发送不同分片
