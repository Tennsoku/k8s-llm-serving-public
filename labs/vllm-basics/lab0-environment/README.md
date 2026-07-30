# Lab 0: Environment Validation

## Outcome

Produce a reproducible record proving that the selected Python environment can import vLLM and access an NVIDIA GPU through PyTorch.

## Steps

1. From this module directory, create the environment:

   ```bash
   VLLM_SPEC='vllm' ./lab0-environment/commands/install-vllm.sh
   source .venv-vllm/bin/activate
   ```

   Pin `VLLM_SPEC` (for example, `vllm==<tested-version>`) for a durable submission. Installation requires network access and can be platform-specific.

2. Run `./lab0-environment/commands/verify-environment.sh`.
3. Copy the evidence into [environment.md](environment.md), record the exact model revision, and save `python -m pip freeze` with the submission.
4. Record free VRAM immediately before any model is loaded.

## Expected result and errors

The verifier prints OS, CPU, memory, Python, PyTorch, vLLM, CUDA, and GPU data. A CPU-only machine may run the script, but it does not pass this GPU lab. Missing commands are reported rather than hidden. Installation failure should be retained verbatim with OS, Python, driver, and package-index context.

## Submission

- Completed `environment.md`
- Verifier output and dependency lock/freeze
- Short answers to the five review questions in the parent design

## Review criteria

- **Pass:** GPU is visible to `nvidia-smi` and PyTorch, `torch.cuda.is_available()` is true, vLLM imports, all versions and model revision are recorded, and another learner can repeat the install.
- **Revise:** “Latest” replaces exact versions, driver CUDA is confused with PyTorch runtime CUDA, model revision is absent, or raw evidence is missing.
- **Human review:** Explain two environment variables or system characteristics that could bias later benchmark comparisons.
