# M3 Work Log

记录操作过程中的一些步骤和发现。本文是按时间记录的工作日志。

--- 

一开始的设想是做一个独立的 control plane 节点，就想着把 WSL 当作这个入口。实操过程中发现使用这个并不纯净的环境带来了不少麻烦，而且作为一个个人节点的 Availablity 也有待考量：WSL 和 spark 并不在同一私网下，需要设置 tailnet，同时作为单点 access 节点仅有我可以接触，一旦 down 了会失去对整个 cluster 的控制。HA 暂时没急着做，新的独立的单控制节点也还在讨论中，目前还是回到 1 cp + work -> 1 work 的拓扑最稳定。

回滚之前的设计。

在 setup k8s 的过程中出了一个比较严重的 incident。。。忘了 containerd 和 runc 是 k8s 和 docker 的共有 dependency 了， 在上 Ubuntu 发行版 containerd 的时候没仔细看 apt summary，把 docker-ce 和 containerd.io 一起带走了。docker 环境整个炸完，还好发现及时可以简单回滚。切记切记，这在看到 apt summary 的时候就应该停下来的。之前也了解过 k8s 底层这一块，怎么就没过脑子呢

把设计的minimal基本都落地了。不过学到了 k8s 的记账和现有的 docker 并不共通，之后跑 workload 的时候需要格外小心，UMA 的特殊性导致如果 GPU vRAM 拿太多甚至会使得整个 node 的 memory 被占满，导致系统级 OOM 影响到 docker 和整个 node 的稳定性。之后的 workload 需要在拉起前优先确认 docker 的情况。

修改了 dgxtop 专门分一个 tab 出来看 container

Plugin 接入了 GPU 和 RoCE，不过现在 GPU 和 RoCE 的最小分块就是 1，只能靠 time slice 来做多任务调度。后续可以考虑做一个 scheduler 来做 GPU 和 RoCE 的分配？再说吧
