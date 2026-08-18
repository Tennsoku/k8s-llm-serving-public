# M1 Work Log

记录操作过程中的一些步骤和发现。本文是按时间记录的工作日志。

--- 

M1开始前想要规范一下证据的收集和整理流程，主要是为了保证后续的review和publication过程顺利。
一开始从M0的标准出发，但是发现越做越繁琐，甚至到了cryptographic的程度，这是完全没有必要的。M0之所以做得麻烦了点是因为考虑到涉及到一些敏感信息的收集和整理，必须要保证安全性和可追溯性。
及时叫停了进一步深入钻牛角尖，现在的目标是保证收集的证据可以被review和publication使用，并检查常见敏感信息。后续milestone会继续沿用简化流程。

Lab0和Lab1跑完了。虽然觉得Lab1为了offline固定环境把整个results都mount进一个container有点蠢，但是后面把这个container分离成serving plane后应该就不需要这么干了。现在跑完出来还要chown整个目录，多少感觉不是container化的做法。

offline阶段的一些理解扩展：
- max_tokens主要影响的是output tokens，提高会增加decode段的时间和内存占用。decode是compute intensive的，所以elapsed time显著增加，但是memory好像也加了不少。
- KV$的初次建立在prefill阶段，Decode时在读取当前token的KV$后会在生成新的token的时候追加新的KV$。mem的增加也是这个原因。

Online没什么好说的，主要是把serving plane独立出来，建立了三个基础host脚本。

## Metrics 

进入Canonical capture以后逐渐感觉事情变得复杂起来了。runtime/client/system三个环境的数据都要采集，目前的设计的流程是这样的：
```text
start server
    ↓
wait ready
    ↓
capture run metadata
    ↓
capture run exposition
    ↓
warm-up
    ↓
Concurreny levels: 1 2 4 8 16 32 × 3 repetitions
    ↓
stop metric sampler
    ↓
capture after exposition
    ↓
stop server
    ↓
derive summary
```

一开始想着runtime和system的采集都在serving plane上进行了，但是被教育会和vLLM竞争资源，污染benchmark，并且在host上的cgroup和proc指标更准确。想想后续monitoring和profiling也是独立的plane进行，确实是我考虑没到位了。

可能是Spark比较强悍，C16根本摸不到knee，拉个C32跑一下试试看

麻了，拉到128也看不到knee。先往后推吧。

M1.3之前的scope最大问题是一直使用同一个prompt, Prefix Cache Hit高达99.31%。prefill几乎没有压力，KV cache也很难扩展。 E2E在C24的时候接近初版SLO的边界了(500ms)，不过曲线一直很平滑，一直到C128为止还是没有达到Saturation，没有出现明显的knee。后续的scope会使用不同的prompt，增加prefill和KV cache的压力。（Spark果然还是太强了

M1.4-1.6在benchmark管线搭完以后跑得倒是挺快的，但是结论写得有点力竭。。。

写到一半review整个repo的时候发现已经有各种漂移和超限了，以目前的进度来看roadmap的预估也非常不靠谱。需要大刀阔斧改一下现在的scope和roadmap。
而且要好好写一版AGENTS的约束和规范了。模糊的语句描述的约束毫无力度，随便超随便漂，必须有一个hard gate。

AI有一句说的对，规范写了不用CI作为hard gate，那就还是白写。必须要有tests和CI来保证执行力。

总算close了。最后审计的时候还和AI拉扯了很久，各退一步取中点吧。我多写点caveat，你少卡我点脖子，不要不想说车轱辘话也要卡我一下。
