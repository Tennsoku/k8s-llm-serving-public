# Lab 2 Observations

> 完整 capture 保留在本地 gitignored
> `artifacts/staging/evidence/20260809-lab2/`；本文保留 observed values，不把
> legacy 小文件纳入 M1 final-reference public evidence。

## Fixed runtime

| Evidence | Value/location |
|---|---|
| Model and immutable revision/checksum | `7ae557604adf67be50417f59c2c2f167def9a775` |
| Runtime/container and vLLM/PyTorch versions | `nvcr.io/nvidia/vllm@sha256:1de8e6bfdb4c81c1f31a806cc9b13b5c6352714a7cec87f4d24964bcc91159b2`, `vLLM 0.24.0+092c4842.dev`, `PyTorch 2.13.0a0+9186a08b2c.nv26.07` |
| Exact expanded server command | `vllm serve /models/Qwen2.5-0.5B-Instruct --host 0.0.0.0 --port 8000 --dtype auto --served-model-name qwen2.5-0.5b-instruct --gpu-memory-utilization 0.15` |
| `SERVED_MODEL_NAME` | qwen2.5-0.5b-instruct |
| `GPU_MEMORY_UTILIZATION` | 0.15 |
| `MAX_MODEL_LEN` / `MAX_NUM_SEQS` | unset |
| Initial server-ready time and startup log | local-only capture |
| Restart server-ready time and startup log | local-only capture |
| Idle system/cgroup/CUDA memory evidence | local-only capture |
| Post-shutdown memory/time | local-only capture |
| Initial/restart server exit codes | 120 (Ctrl-C) |
| Shutdown signal, traceback, or leaked-process evidence | none observed |

## API behavior

| Request | HTTP status | Raw evidence | Observed behavior |
|---|---:|---|---|
| `GET /health` before ready | 000 | local-only | endpoint no response |
| `GET /health` ready | 200 | local-only | endpoint healthy |
| `GET /v1/models` | 200 | local-only | model ID: qwen2.5-0.5b-instruct |
| Non-stream chat | 200 | local-only | one-time return with complete content |
| Stream chat | 200 | local-only | multiple returns with content chunks |
| Unknown model | 404 | local-only | expected 404, server healthy after error |
| Malformed JSON | 400 | local-only | expected 400, server healthy after error |
| Post-stop health probe | 000 | local-only | endpoint stopped: no response |

## Interpretation

- Why memory remains allocated while idle: vLLM server keeps the model loaded in GPU memory until shutdown, and KV cache VRAM (for spark -- unified with system RAM) is reserved for future requests. The server does not free memory until the process exits.
- Server readiness versus request TTFT: 
  - The server is considered ready when it can respond to `/health` and `/v1/models` requests, which indicates that the model is loaded and the server is listening.
  - TTFT for a request does not include serving time. Only includes model inference time after ready status.
- Work before the first generated token: 
  - Serving preparation: loading the model, initializing the engine, and preparing the request pipeline
  - Model inference: Prefill (tokenization, forward pass)
- Served API name versus model source/path: 
  - Model name is `qwen2.5-0.5b-instruct`, name used in the API requests.
  - Model source path is `/models/Qwen2.5-0.5B-Instruct`, files on disk.
  - The server maps the served model name to the model source path internally.
- Expected 4xx versus unexpected transport/5xx failure: 
  - Expected 4xx responses (e.g., unknown model, malformed JSON) indicate that the server is running correctly and returning appropriate error codes for invalid requests.
  - Unexpected 5xx, 000 transport failure, or timeout indicates the server is not functioning correctly.
- Startup/restart/shutdown reproducibility: yes, shutdown with Ctrl-C, so the exit code is 120. The server can be restarted with the same command and environment variables.
- Unified-memory telemetry limitation: 
  - On DGX Spark, unsupported framebuffer-memory fields are evidence of the unified-memory telemetry boundary; do not convert `N/A` to zero or call it discrete VRAM.
- Errors or version-specific changes: None observed.
