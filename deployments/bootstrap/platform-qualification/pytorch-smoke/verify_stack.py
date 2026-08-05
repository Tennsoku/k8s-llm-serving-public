from __future__ import annotations

import json
import platform
import sys

import torch


def main() -> int:
    result: dict[str, object] = {
        "python_version": sys.version,
        "architecture": platform.machine(),
        "torch_version": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_count": torch.cuda.device_count(),
        "cudnn_available": torch.backends.cudnn.is_available(),
        "cudnn_version": torch.backends.cudnn.version(),
        "nccl_available": torch.distributed.is_nccl_available(),
    }

    if not torch.cuda.is_available():
        print(json.dumps(result, indent=2))
        return 1

    device = torch.device("cuda:0")
    result["device_name"] = torch.cuda.get_device_name(device)
    result["device_capability"] = torch.cuda.get_device_capability(device)

    left = torch.randn((2048, 2048), device=device)
    right = torch.randn((2048, 2048), device=device)
    output = left @ right

    torch.cuda.synchronize()

    result["output_shape"] = list(output.shape)
    result["output_finite"] = bool(torch.isfinite(output).all().item())

    print(json.dumps(result, indent=2))
    return 0 if result["output_finite"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
