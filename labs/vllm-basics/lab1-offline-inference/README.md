# Lab 1: Offline Inference

## Outcome

Load one model directly through the vLLM Python API, distinguish initialization from generation time, and demonstrate a multi-prompt call.

## Steps

1. Activate the Lab 0 environment and capture `nvidia-smi` before loading.
2. Run the default four-prompt case:

   ```bash
   python lab1-offline-inference/offline_inference.py --max-tokens 32
   ```

3. Repeat with `--max-tokens 128`. Then use repeated `--prompt` options to run a controlled two-prompt case.
4. Repeat an identical case and compare outputs. Temperature is zero and the seed is fixed; explain any remaining nondeterminism.
5. Capture GPU memory during generation in a second terminal (`nvidia-smi --loop=1`) and complete [observations.md](observations.md).

Use `--model` and `--revision` when deviating from the default. The Python API is version-sensitive; record the vLLM version if an argument changes.

## Expected result and errors

The program reports model initialization separately, prints every prompt/output and output-token count, and reports batch generation time. It exits clearly for a missing package, model-load error, or generation error. A Hugging Face download or gated-model error is an environment issue, not benchmark evidence.

## Submission and review criteria

- Submit command lines, uncropped output, GPU observations, and completed notes.
- **Pass:** at least two prompts share one `generate` call; 32- and 128-token limits are compared; load time and request time are separated; memory evidence is timestamped; deterministic behavior is demonstrated or explained.
- **Revise:** only one prompt is used, initialization is included in generation latency, output is claimed deterministic from one run, or memory values lack measurement timing.
- **Human review:** Explain `LLM`, `SamplingParams`, cold-start overhead, and which sampling settings affect quality versus resource use.
