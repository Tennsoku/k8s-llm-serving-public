# Lab 2: OpenAI-Compatible Serving

## Outcome

Operate a persistent vLLM endpoint, exercise streaming and non-streaming chat completions, and preserve its success and failure behavior.

## Steps

1. Start the service and save its log:

   ```bash
   ./lab2-online-serving/commands/start-server.sh 2>&1 | tee lab2-server.log
   ```

2. Wait for application startup; query `curl http://127.0.0.1:8000/health` and record elapsed startup time.
3. In a second shell run `./lab2-online-serving/commands/curl-examples.sh`.
4. Send malformed JSON manually and record its status/body. The script already validates an unknown-model failure.
5. Capture idle VRAM, interrupt the server with Ctrl-C, and measure whether/when memory returns.
6. Restart from the same command and complete [observations.md](observations.md).

Set `MODEL`, `MODEL_REVISION`, `SERVED_MODEL_NAME`, `HOST`, `PORT`, or `DTYPE` as environment variables. If the served name differs, use the same `MODEL` value for the curl script. CLI flags are version-sensitive; preserve `vllm serve --help` when adaptation is required.

## Expected result and errors

`/v1/models` exposes the served name. The non-streaming response is one JSON document; streaming is server-sent events ending in a completion marker. Curl fails on unexpected HTTP errors, while the intentional invalid-model case must return 4xx. The server script validates its binary and port before model loading.

## Submission and review criteria

- Submit startup command/log, successful API bodies, streaming excerpt, failure status/bodies, shutdown evidence, and completed notes.
- **Pass:** documented start/restart/stop all work; model list and both completion modes succeed; at least invalid-model and malformed-body failures are explained; idle and post-stop memory are measured.
- **Revise:** only HTTP 200 bodies are retained, API model name is assumed rather than verified, or startup latency is labeled TTFT.
- **Human review:** Assign model execution, auth, rate limiting, routing, and tenant isolation to vLLM or an external platform component, with reasons.
