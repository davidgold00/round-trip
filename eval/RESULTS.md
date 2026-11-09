# Deal extraction evaluation

Status: **incomplete**. Model: `qwen2.5:7b-instruct`.
Run: `f0d8f846cda7400cba70342903213a59`. Generated: 2026-11-09T06:22:34.402047+00:00.

Gold corpus: 12 positive and 5 negative documents; 7 uncertain labels. 0 structural label failures.

The corpus contains short, attributed excerpts, not full filings. It is a small smoke benchmark; scores do not establish full-document or out-of-time accuracy. Uncertain labels remain identified in manifest.json.

| Metric | Result |
|---|---:|
| triage_precision | Not measured |
| triage_recall | Not measured |
| edge_precision | Not measured |
| edge_recall | Not measured |
| amount_accuracy | Not measured |
| numeric_amount_accuracy | Not measured |
| verification_pass_rate | Not measured |

Edge matching is directed entity pair + deal_type, one-to-one per document. All predictions are scored, including failed verification; failures are never filtered to improve precision. Amount accuracy scores matched pairs, including correct nulls; numeric accuracy excludes null gold amounts. Numeric tolerance: max($1, 0.1%). Final verification rate includes repaired candidates.

Excluded uncertain labels: False. A failed model call makes the run incomplete; metrics are withheld rather than treating an unavailable model as zero recall.

## Execution errors

- microsoft_openai_2019: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
- microsoft_openai_2023: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
- nvidia_openai_2025: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
- amazon_anthropic_2023: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
- amazon_anthropic_2024: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
- coreweave_openai_2025: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
- amd_openai_chips_2025: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
- oracle_openai_2025: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
- coreweave_meta_2026: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
- nvidia_coreweave_2025: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
- amd_openai_warrant_2025: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
- negative_frontier_forum: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
- negative_regulation: Local Ollama unavailable. Run `ollama serve`, then pull the configured model (qwen2.5:7b-instruct). No remote fallback is used. HTTPConnectionPool(host='127.0.0.1', port=11434): Max retries exceeded with url: /api/generate (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=11434): Failed to establish a new connection: [Errno 111] Connection refused"))
