# Interview walkthrough

## Two minutes

**Point to make.** The dashboard measures how much supplier backlog can be traced to a customer that supplier also financed.

- When a supplier invests in a customer, that customer may spend some of the funding back with the supplier.
- Follow both arrows. An investment goes from seller to customer. A capacity purchase goes from customer back to seller.
- The central reading is $46.7 billion of $2.72 trillion across 38 reviewed relationships, or 1.72%. The assumptions put it between 1.39% and 18.22% against the same denominator.
- Most backlog is anonymous. Only 20.7% of the denominator ties to named customers. The local model adds proposed relationships for a person to inspect.

**Show this.** Open the Headline panel and the [system diagram](../README.md#how-the-system-works).

## Five minutes

Start `make serve` in a second terminal. Keep the [How it works panel](http://localhost:8765/#how) open next to the shell.

| Time | What to show | What to say |
|---|---|---|
| 0:00–0:45 | Headline | The central estimate attributes $46.7B of $2.72T in disclosed supplier backlog to customers with financing traceable to the seller. That is 1.72%. Only 20.7% of backlog has a named customer, so much of the denominator cannot be attributed. |
| 0:45–1:30 | How it works → read the OpenAI release | Microsoft invested in OpenAI. The supply-side question is how much customer spending later goes back to a funder. The model proposes the funding arrow. |
| 1:30–2:30 | `make demo` | This replays a local Qwen recording against the cached release. It proposes Microsoft → OpenAI, equity investment, $1 billion. The source establishes an investment. The reviewer still needs evidence for the precise instrument. |
| 2:30–3:30 | `make explain ID=a_81cddd0804260229a87a` | The quote, source URL and entities pass. The model says “one billion” where the source says “$1 billion”. Find the same failure under both `verify` and `verify.retry`. Reconciliation says NEW and review says pending. |
| 3:30–4:30 | How it works → open the linked Microsoft filing | The reviewed ledger already contains $13B in total funding commitments. NEW means the matching rule found no same transaction. A reviewer must resolve overlap, legal status and amount bounds. Approval exports a YAML, application changes the ledger, and publication rebuilds the metrics and dashboard. |
| 4:30–5:00 | Return to Headline | An eligible new funding row can change the share of customer purchases attributed back to a supplier. A duplicate contributes zero additional dollars. The recorded proposal remains pending and contributes zero. |

[Original source, responses and checks](TRACE_EXAMPLE.md) · [Benchmark counts](../eval/RESULTS.md) · [Review commands](04-deal-agent.md#human-review-and-publication)

## Fifteen minutes

### Data and evidence tiers

**Point to make.** A relationship earns its place through an attributable source and a defined payment direction.

- Start with EDGAR filings, issuer releases and news discovery. A stored snippet supports only the words it contains.
- Follow a reviewed row from source URL to short quote, as-of date and SEC accession where applicable.
- Only T1 filings and T2 issuer statements enter the headline. Third-party reports can guide investigation and a separate sensitivity view.
- A cap, a purchase order and a signed annual obligation carry different implications. The review fields retain the amount basis, conditions and status.

**Show this.** Open the dashboard Ledger panel and one source. Keep the [data guide](02-data-and-ledger.md) open.

### The deal agent stage by stage

**Point to make.** The model interprets prose inside a pipeline whose checks and publication rules are ordinary Python.

- Hash and store the source. Chunk long documents with overlap and remember successful chunks by document identity.
- Count resolved companies and financing cues, then ask the local model for relevance. A second call proposes one or more directed edges.
- Validate strict JSON and check the quote, USD amount, entities and URL. Keep the original failed check even when a retry repairs it.
- Reconcile direction, instrument, source/date and amount against reviewed and pending rows. Route the result to a person.

**Show this.** Run `make explain ID=a_81cddd0804260229a87a` and point to the raw response and both amount checks. [Agent workflow](04-deal-agent.md)

### Why freeze the test split?

**Point to make.** The comparison needs evidence that could not influence the changes made this night.

- Group passages from the same release and linked AMD/OpenAI announcement. Use 15 development passages and reserve ten for the final comparison.
- Lock membership and test annotations by hash. Keep review feedback apart from those sources. Expected labels never enter an inference prompt.
- Count exact directed pair and type with one-to-one matching. A verified quotation can still describe the wrong type. Every proposed edge enters the denominator.
- Treat this as a small excerpt study. The historic rules report already covered all 25 passages. A new filing corpus would provide stronger evidence of generalization.

**Show this.** Open the [frozen split](../eval/gold/splits.json) and the [selection rule](history/NIGHT3.md#selection-rule-recorded-before-scoring).

### What the comparisons teach

**Point to make.** Read the errors behind a difference before treating it as a better extraction method.

- The rules adapter has a dollar floor and guesses direction. On dev it scored one true edge, eleven extra proposals and nine missing edges across fifteen passages.
- “Meta” appeared inside the editorial word “metadata”. “Intel” appeared inside “intelligence”. The independent alias check exposed how the extractor generated extra candidates.
- Read precision and recall together. A filter can increase precision by dropping both correct and incorrect candidates. Check the number of correct directed edges and verifier failures as well.
- Use the scored run ID and its cassette to examine any discrepancy. Timing for real inference and the sub-two-minute replay describe different operations.

**Show this.** Put the [development comparisons](../eval/RESULTS-dev.md) and [error analysis](../eval/ERROR_ANALYSIS.md) beside one another.

### Review and promotion

**Point to make.** An analyst decides whether a later disclosure is a distinct transaction or restates an earlier one.

- Open the worklist. A candidate can be new, an update or a duplicate. The classification is a suggestion based on matched records.
- Read the original source and see why a verifier flagged the item. A human can correct it, reject it or approve a short publication quote and conservative bounds.
- Approval exports a reviewed YAML. Application checks its content and ledger revision, records the audit and requires an explicit target for an update. Only then can publication rebuild the dashboard.

**Show this.** Run `python -m deal_agent inbox`. Open the [review sequence](04-deal-agent.md#human-review-and-publication). In an interview, finish at inspection.

### From one approved deal to the financial result

**Point to make.** A single financing relationship can change the share attributed to several suppliers even if no customer commitment changes.

- On a new Microsoft-to-OpenAI funding edge, Microsoft's share of OpenAI's documented external funding can rise. Other funders' shares can fall because they share that denominator.
- Each supplier's exposure multiplies the eligible customer's share of its backlog by the applicable provenance share. The ecosystem aggregates using disclosed backlog weights.
- On a purchase edge the input changes elsewhere. The buyer's eligible commitment increases that seller's demand numerator. A restatement replaces the selected row.
- Stress uses the revised network to propagate a funding shortfall through purchases under a pass-through assumption. The traced pending example has no measured incremental effect.

**Show this.** Open the [metric definition](03-metrics-and-stress.md) and the dashboard Stress lab. Move its pass-through control and point out the underlying assumption.

### What failed and what changed

**Point to make.** The failures identify places where more modeling cannot supply missing evidence.

- Earlier Amazon labels treated the transaction as equity. A separately attributed filing supplement established a convertible note and changed the adjudication.
- A warrant receipt can establish who holds the warrant while leaving the project's financing direction ambiguous. Its uncertain label remains visible.
- The model can repeat the same unsupported text after a repair. Recording both attempts makes the failure explainable and prevents an unattended ledger change.
- The evidence base still needs full filing passages and more independent deals. Repeated excerpts from one S-1 add information about that filing without supplying another independent company.

**Show this.** Open the [prior adjudication record](history/AGENT_PROGRESS.md), [gold notes](../eval/gold/README.md) and [traced example](TRACE_EXAMPLE.md).

## Design tradeoffs

| Choice | Alternative considered | Reason in the project | Cost | Source |
|---|---|---|---|---|
| Loopback Ollama | Hosted inference | Keep source text local and allow runs without API keys | Model download, RAM and CPU time | [Provider and preflight](../deal_agent/provider.py) |
| Plain Python orchestration | Agent framework | Each stage, retry and side effect is explicit and can be tested independently | The repository owns orchestration and recovery | [Pipeline](../deal_agent/pipeline.py) |
| Deterministic evidence checks | Ask the model to certify its own answer | Recheck copied words, known entities and explicit USD against the cached source | A true quote can still refer to the wrong instrument | [Verifier](../deal_agent/verify.py) |
| One bounded repair | Retry until a check passes | Retain initial failures and prevent a repair from exchanging an unresolved deal for a different one | Some fixable candidates remain pending | [Repair implementation](../deal_agent/pipeline.py) |
| Human promotion gate | Publish verified model output automatically | A person must decide status, legal identity and conservative dollar bounds | Analyst review limits throughput | [Review integration](../DECISIONS.md#agent-review-integration-2026-11-09) |
| Shared application mechanism | A second ledger writer for the agent | Original and agent reviews need the same stale-state and update protections | Approval, application and publication are separate operations | [Dated decision](../DECISIONS.md#agent-review-integration-2026-11-09) |
| Freeze source groups | Repeatedly compare on all excerpts | Protect the final comparison from later tuning and same-source leakage | Only ten passages are available for held-out scoring | [Prospective rule](history/NIGHT3.md#selection-rule-recorded-before-scoring) |
| Record exact responses | Require a live model for every demonstration | Reconstruct the real output, check request identity and replay offline | Recordings take space and change when prompts change | [Record and replay](../deal_agent/provider.py) |
| Original rules baseline | Report a model score in isolation | Measure the incremental value of model extraction on identical inputs | A fixed taxonomy mapping is required | [Rules adapter](../deal_agent/rules.py) |
| Three provenance readings | Report one exact financing fraction | Private funding denominators are incomplete and disclosure is uneven | The range is wide | [Pre-registered provenance](../DECISIONS.md#a5-funding-provenance-matrix-f-and-the-three-bounds) |
