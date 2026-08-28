# M2 Review

<section id="m2-overview" class="review-fragment" data-analysis-status="draft">
<h2>M2.0 — Compatibility inventory</h2>
<p><strong>结论（Interpretation）：</strong>在 pinned runtime 上，APC、FP8 KV cache、online FP8 weight 与 Qwen3 draft speculative configuration 均有成功的 canonical candidate；Qwen2.5 draft speculative configuration 在 startup 阶段失败。这里的 supported 只表示对应配置在本环境可启动并完成所列请求，不证明性能、质量或跨版本兼容性。</p>
<table>
<thead><tr><th>Feature</th><th>分类</th><th>公开证据</th></tr></thead>
<tbody>
<tr><td>APC</td><td><code>supported</code></td><td><a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-apc-candidate-7b-canonical/run.yaml">run</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-apc-candidate-7b-canonical/derived/summary.json">summary</a></td></tr>
<tr><td>FP8 KV cache</td><td><code>supported</code></td><td><a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-kv-candidate-canonical/run.yaml">run</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-kv-candidate-canonical/raw/server/server.log">log</a></td></tr>
<tr><td>Online FP8 weight</td><td><code>supported</code></td><td><a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-weight-candidate-canonical/run.yaml">run</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-weight-candidate-canonical/raw/server/server.log">log</a></td></tr>
<tr><td>Draft speculative</td><td>Qwen2.5 <code>startup_failed</code>；Qwen3 <code>supported</code></td><td><a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-compat-draft-speculative-qwen2.5/raw/server/server.log">failure</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260825-m2-spec-decoding-candidate-canonical/run.yaml">success</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260825-m2-spec-decoding-candidate-canonical/derived/summary.json">summary</a></td></tr>
</tbody>
</table>
<p><strong>Observed Fact：</strong>四个 supported candidate 的公开 summary 均记录 success 与 raw validation passed；Qwen2.5 failure evidence 记录 0 measured request 与 startup failure。APC、量化、512-token speculative 的 A/B 和 4k/8k/16k long-context run set 是 active showcase 范围。</p>
<p><strong>范围：</strong>未公开的 64-token speculative exploratory point 与 32k startup check 只保留为 Tier B、non-active 限制，不进入 selector，也不作为以下结论的主要公开证据。</p>
</section>

<section id="m2-prefix-cache" class="review-fragment" data-analysis-status="draft">
<h2>M2.1 — Prefix-cache canonical comparison</h2>
<p><strong>结论（Interpretation）：</strong>在固定 prefix-heavy workload 的 C1/C16 canonical A/B 中，run-shared candidate 的 token hit、prefill、TTFT 与 waiting 读数共同支持“prefix reuse 减少 measured prefill 工作”的解释。C16 确认了 bounded concurrency 下的机制收益，但不是 capacity、<code>C_eff</code> 或全局最优点。</p>
<p><strong>证据：</strong><a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-apc-baseline-7b-canonical/derived/summary.json">control summary</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-apc-candidate-7b-canonical/derived/summary.json">candidate summary</a> · <a href="../../showcase/m2/compare.html?study=m2.1-prefix-cache-canonical&amp;c=16">C16 comparison</a></p>
<table>
<thead><tr><th>C</th><th>Hit ratio control→candidate</th><th>Uncached prefill tok/req</th><th>TTFT p95</th><th>Prefill mean</th><th>Max waiting</th></tr></thead>
<tbody><tr><td>1</td><td>0% → 98.746%</td><td>1037 → 13</td><td>0.267 → 0.145 s</td><td>0.185 → 0.067 s</td><td>0 → 0</td></tr><tr><td>16</td><td>0% → 98.746%</td><td>1037 → 13</td><td>3.175 → 0.244 s</td><td>0.862 → 0.144 s</td><td>9 → 0</td></tr></tbody>
</table>
<p><strong>Observed Fact：</strong>两侧均在 fresh runtime 上完成 C1/C16 × 3 repetitions；各 6/6 cases 完整、96/96 requests 成功且 raw validation passed。对应请求的 input tokens 全部匹配，public summaries 保留 query/hit counter delta 与 derived hit ratio。</p>
<p><strong>Observed Fact：</strong>C1 的 E2E p95 median 为 4.291→4.961 秒，没有观测到端到端收益。96 对请求中有 17 对 output token 数不同，因此 throughput、TPOT 与 E2E 的归因弱于 counter、prefill 和 TTFT。</p>
<h3>范围与执行缺口</h3>
<ul><li>Priming-inclusive 成本尚未物化，公开投影也未保留 warm-up evidence，因此当前不发布成本结论。</li><li>性能 run 不保存输出文本；结果不能用于输出质量结论，也不能外推到其他 prompt 或实际 hit-rate 分布。</li></ul>
</section>

<section id="m2-quantization" class="review-fragment" data-analysis-status="draft">
<h2>M2.2 — Quantization canonical comparisons</h2>
<p><strong>结论（Interpretation）：</strong>在 pinned runtime 与 C1 workload 下，FP8 KV 将 runtime 报告的 KV capacity 提高约 92.7%，但冻结质量集出现负向 flip，不能视为透明替代；online FP8 weight 的 decode 指标改善，4-case 质量集未观测到 flip。后者实际为 FP8 weight、<code>activation=None</code>、BF16 compute 与 KV auto，不是已验证的 W8A8；两组结果均不外推为全局性能或质量结论。</p>
<p><strong>KV 证据：</strong><a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-kv-baseline-canonical/derived/summary.json">baseline summary</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-kv-candidate-canonical/derived/summary.json">candidate summary</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-kv-baseline-canonical/derived/output-evaluation-summary.json">baseline output</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-kv-candidate-canonical/derived/output-evaluation-summary.json">candidate output</a> · <a href="../../showcase/m2/compare.html?study=m2.2-kv-quant-canonical&amp;c=1">comparison</a></p>
<p><strong>Weight 证据：</strong><a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-weight-baseline-canonical/derived/summary.json">baseline summary</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-weight-candidate-canonical/derived/summary.json">candidate summary</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-weight-baseline-canonical/derived/output-evaluation-summary.json">baseline output</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-weight-candidate-canonical/derived/output-evaluation-summary.json">candidate output</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260823-m2-quant-output-weight-candidate-canonical/raw/server/server.log">candidate runtime</a> · <a href="../../showcase/m2/compare.html?study=m2.2-weight-quant-canonical&amp;c=1">comparison</a></p>
<table>
<thead><tr><th>Axis</th><th>Strict quality baseline→candidate</th><th>C1 median / runtime capacity baseline→candidate</th></tr></thead>
<tbody><tr><td>BF16 weight + FP8 KV</td><td>3/4 → 2/4</td><td>KV capacity 254,384 → 490,224 tokens；TTFT p95 265.42 → 273.59 ms；TPOT p95 74.77 → 76.57 ms</td></tr><tr><td>Online FP8 weight</td><td>3/4 → 3/4</td><td>Output TPS 13.096 → 27.477；TPOT p95 76.38 → 36.38 ms；KV capacity 248,288 → 369,584 tokens</td></tr></tbody>
</table>
<p><strong>Observed Fact：</strong>四条 canonical run 均使用 fresh runtime，完成 C1 × 3 repetitions；每条 24/24 measured requests 成功、raw validation passed、lifecycle graceful。四份公开 output-evaluation summary 均记录 4/4 cases、0 request error，且 item id 与 scorer 对齐；FP8 KV 的 <code>long-01</code> 为 <code>true→false</code>，<code>format-01</code> 在四侧的 strict <code>json_exact</code> 都为 false。</p>
<p><strong>公开证据边界：</strong>Tier A 仅保留 output-evaluation summary，没有原始 evaluation response 或 frozen case file；因此公开页面可以复核 score/flip，不能从公开 projection 重算质量 summary 或独立复核输出文本细节。没有预声明质量阈值，这里只报告变化，不判定“可接受”。</p>
<h3>范围与执行缺口</h3>
<ul><li>性能证据只有 C1 canonical，未执行额外 bounded exploratory 点；不据此声称并发收益、capacity 点或全局最优。</li><li>KV pair 的 measured output tokens 为 1,200 → 1,483，E2E 与 request/output throughput 不能作干净 A/B 归因；TTFT、TPOT 只作为该有界请求集的观测。</li><li>质量结论仅覆盖固定 4 cases；约 1K 的 retrieval case 不代表 8K long-context accuracy。</li></ul>
</section>

<section id="m2-speculative" class="review-fragment" data-analysis-status="draft">
<h2>M2.3 — Speculative decoding canonical comparison</h2>
<p><strong>结论（Interpretation）：</strong>在 pinned runtime 中，Qwen3-0.6B draft + Qwen3-8B target 不是通用 latency 优化：512-token canonical 降低 TPOT/E2E、提高 output TPS，同时增加 TTFT。结果支持一个以目标函数划分的适用边界——tested completion/decode-sensitive workload 受益，TTFT-primary 交互请求为负收益；tested canonical range 未出现整体 E2E/TPS negative point。</p>
<p><strong>证据：</strong><a href="../../benchmarks/raw-results/m2-serving-optimization/20260825-m2-spec-decoding-baseline-canonical/derived/summary.json">baseline summary</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260825-m2-spec-decoding-candidate-canonical/derived/summary.json">candidate summary</a> · <a href="../../showcase/m2/compare.html?study=m2.3-spec-decoding-canonical&amp;c=16">C16 comparison</a></p>
<table>
<thead><tr><th>Workload</th><th>Acceptance rate</th><th>Accepted tok/draft</th><th>TTFT p95</th><th>TPOT p95</th><th>Output TPS</th><th>E2E p95</th></tr></thead>
<tbody><tr><td>512-out / C1</td><td>52.2613%</td><td>1.567839</td><td>0.086020 → 0.110539 s</td><td>0.071743 → 0.036225 s</td><td>13.939 → 27.585</td><td>36.744 → 18.623 s</td></tr><tr><td>512-out / C16</td><td>53.1303%</td><td>1.593909</td><td>0.221981 → 0.272461 s</td><td>0.071378 → 0.044080 s</td><td>223.344 → 344.003</td><td>36.677 → 22.754 s</td></tr></tbody>
</table>
<p><strong>Observed Fact：</strong>两侧均完成 C1/C16 × 3 repetitions；各 96/96 requests 成功且 raw validation passed。所有 measured requests 均为 33 input / 512 output tokens、<code>finish_reason=length</code>。Candidate 在每个 concurrency 内三次 counter delta 相同，acceptance 派生值已进入 summary。</p>
<h3>范围与执行缺口</h3>
<ul><li>性能 workload 不保存输出正文，不能从 active public evidence 得出输出等价性结论。</li><li>64-token exploratory point 与独立 4-case output evaluation 为 Tier B、non-active 证据，不进入 selector；它们不替代 512-token canonical primary。</li><li>Candidate 会同时改变 scheduler/model-runner 路径；这里只归因到整套 speculative configuration，不隔离内部机制。</li></ul>
</section>

<section id="m2-long-context" class="review-fragment" data-analysis-status="draft">
<h2>M2.4 — Long-context boundary check</h2>
<p><strong>结论（Interpretation）：</strong>在 pinned 7B BF16 runtime、C1、<code>max_model_len=32768</code> 下，actual input 3,812–14,912 tokens 的三个 exploratory 点均成功。TTFT、prefill time 与 KV usage 随输入长度平滑、近似同比增长；TPOT 只在 76.09–78.84 ms 窄区间内漂移。tested range 内未观察到清晰的 latency knee、KV/统一内存压力信号或请求失败；首个 pressure/failure boundary 仍为 Unknown。</p>
<p><strong>证据：</strong><a href="../../benchmarks/raw-results/m2-serving-optimization/20260824-m2-long-context-4k/derived/summary.json">4k summary</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260824-m2-long-context-8k/derived/summary.json">8k summary</a> · <a href="../../benchmarks/raw-results/m2-serving-optimization/20260824-m2-long-context-16k/derived/summary.json">16k summary</a></p>
<table>
<thead><tr><th>Actual input</th><th>TTFT p95</th><th>Prefill mean</th><th>TPOT p95</th><th>E2E p95</th><th>Max KV usage</th></tr></thead>
<tbody><tr><td>3,812</td><td>0.856 s</td><td>0.772 s</td><td>76.09 ms</td><td>5.189 s</td><td>1.562%</td></tr><tr><td>7,512</td><td>1.628 s</td><td>1.539 s</td><td>76.97 ms</td><td>5.862 s</td><td>2.995%</td></tr><tr><td>14,912</td><td>3.496 s</td><td>3.399 s</td><td>78.84 ms</td><td>7.834 s</td><td>6.046%</td></tr></tbody>
</table>
<p><strong>Observed Fact：</strong>三个 request point 各完成 4/4 measured requests，0 failure/timeout，raw validation passed。max waiting、preemption、cgroup pressure/OOM、host swap/reclaim 均为 0；NVML process、cgroup 与 host memory 没有随长度单调升高。</p>
<h3>范围与 Unknown</h3>
<ul><li>最高验证的是 14,912 input-token 请求成功；<code>max_model_len=32768</code> 配置与 Tier B startup check 不代表 32k 请求能力。每点只有一次、4 个顺序请求，不声明 tail latency、capacity 或严格线性。</li><li>4k 的 output 为 57 tokens，8k/16k 为 55，因此 E2E 只作配套观测；结论以 actual input、TTFT、prefill 与 KV usage 为主。</li><li>GPU framebuffer telemetry 为 unsupported，只能报告现有代理指标未显示压力。三条 server log 在 measured 请求完成后的 SIGTERM shutdown 阶段均有 cleanup traceback 和 <code>EngineDeadError</code>；wrapper 仍记录 exit 0、无 OOM/restart 与 lifecycle success。</li></ul>
</section>
