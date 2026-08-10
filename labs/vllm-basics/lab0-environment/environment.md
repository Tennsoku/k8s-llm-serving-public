# Environment Evidence

Complete this file from the same shell used for every experiment. Do not record access tokens or other secrets.

**Note**: Most info is collected during M0, so here I skipped and filled the fields directly.
Most tests are in vLLM docker container, so all the host environment info is collected from the NVIDIA NGC vLLM image instance.

| Field | Value |
|---|---|
| Date (with timezone) | 2026-08-07 UTC-4 |
| Primary node | spark-a |
| Host operating system | `Ubuntu 24.04.4 LTS` |
| Kernel | `6.17.0-1029-nvidia` |
| CPU | 20 cores: Cortex-X925 + Cortex-A725 |
| System memory | approximately 121 GiB, Unified |
| GPU | NVIDIA GB10 |
| GPU VRAM | Unified |
| NVIDIA driver | `580.173.02` |
| Driver-reported CUDA | `13.3` |
| PyTorch CUDA runtime | `13.3` |
| Python | `3.12.3` |
| PyTorch | `2.13.0a0+9186a08b2c.nv26.07` |
| vLLM | `0.24.0+092c4842.dev` |
| Model | `Qwen/Qwen2.5-0.5B-Instruct` |
| Model revision/commit | `7ae557604adf67be50417f59c2c2f167def9a775` |
| Tokenizer revision/commit | `7ae557604adf67be50417f59c2c2f167def9a775` |
| Install command | `docker pull nvcr.io/nvidia/vllm@sha256:1de8e6bfdb4c81c1f31a806cc9b13b5c6352714a7cec87f4d24964bcc91159b2` |

## Reproducibility notes

- Container: nvcr.io/nvidia/vllm@sha256:1de8e6bfdb4c81c1f31a806cc9b13b5c6352714a7cec87f4d24964bcc91159b2
