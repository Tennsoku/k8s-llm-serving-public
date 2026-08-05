# M0 Container Image Inventory

| Purpose | Registry / image | Tag | Recorded digest | Architecture | M0 status | Notes |
|---|---|---|---|---|---|---|
| PyTorch GPU qualification | `nvcr.io/nvidia/pytorch` | `26.07-py3` | `sha256:7531d90bcbe0e43e1f7363029c7e145ce90eebeb494a7b4695fdba0329d7c3c3` | arm64 | Pass on both nodes | Digest-pinned in the GPU-container smoke and bootstrap replay |
| vLLM functional smoke | `nvcr.io/nvidia/vllm` | `26.07-py3` | `sha256:1de8e6bfdb4c81c1f31a806cc9b13b5c6352714a7cec87f4d24964bcc91159b2` | arm64 | Functional pass / harness partial | Both node inventories record this digest and both captured commands execute it; outer wrappers exit 141 despite HTTP 200 |
| Plain container lifecycle | `hello-world` | `latest` | Not pinned | architecture selected by runtime | Pass in bootstrap replay | Lifecycle-only probe; mutable identity is a trivial, non-blocking M0 issue |

Canonical private identity evidence is under
`artifacts/m0-private/20260805-m0-final/{spark-a,spark-b}/node/images.txt` and the
relevant test `command.txt` files. Its sanitized publication mapping is
`benchmarks/raw-results/m0-platform-qualification/20260805-m0-final/`.
