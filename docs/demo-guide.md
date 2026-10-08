# Faculty demo and viva guide

## Before class

Install from the repository using the README. Run `fr demo`, `fr eval`, and
`python -m pytest`. Open `.rewind/demo.html` before presenting. All external
services in the bundled scenario are simulated: internet and API keys are unnecessary.

## Five-minute demonstration

| Time | Action | Explain |
|---|---|---|
| 0:00 | Open the investigation desk | “An agent's external responses can change. I preserve those inputs so a supported run can be reproduced.” |
| 0:30 | Select Failed, scrub to quote #3 | The cache gives 720; the task budget is 500. |
| 1:00 | Step to #4, then #6 | Explicit agent state says outside budget; the simulated reservation fails. |
| 1:30 | Compare Failed and Passing; jump | First response difference is #3, even though the input request is identical. |
| 2:00 | Show `fr verify FAIL_ID --n 50` | The original failure repeats with the same sanitized boundaries and output. |
| 2:30 | Run `fr fork FAIL_ID --price 420` | Reuse the exact prefix, change a response, then recompute through safe mocks. |
| 3:00 | Select Recovered, inspect #4 and #6 | State and final output actually change. The original recording remains intact. |
| 3:30 | Expand provenance | The fork records its parent fingerprint, intervention index and safety policy. |
| 4:00 | Show `fr eval` and tests | Separate measured synthetic evidence from future production work. |
| 4:30 | State the limitations | Boundary evidence is not a memory snapshot; socket guard is not an OS sandbox; no trained ML classifier yet. |

Use the IDs printed by your latest demo. `fr bisect PASS_ID FAIL_ID` returns exit
code 1 intentionally when it finds a difference, so it can serve as a CI comparison gate.

## The engineering contribution

The demonstrable contribution is an integrated **evidence → intervention → outcome**
workflow: sanitized boundary interception, tamper-evident storage, reproducible
execution, localized divergence and fail-closed counterfactual execution with lineage.
It is useful because viewing a log alone does not test a different decision.
Do not claim universal novelty, production compatibility, or a trained ML model.

## Questions you should be able to answer

**What is a boundary?** A point where the agent consumes a value from outside its
ordinary deterministic logic, such as an HTTP response, tool result or clock read.

**Why does replay work?** Given the same code, deterministic internal logic and the
same complete sequence of captured external values, the same decisions should follow.
An unmatched request or unconsumed event causes an explicit divergence.

**What is stored?** An ordered boundary index and compressed content-addressed
request/response blobs in SQLite, plus final output and optional fork metadata.

**How does the hash chain work?** Each link hashes the previous link and canonical
JSON for the current input and response. Changing an event breaks validation. A
fully rewritten chain is not protected: there is no external signature.

**Is bisect really binary search?** This version scans step-aligned event pairs,
O(n), returning the first content mismatch. Binary search/sequence alignment are
future optimizations; the name refers to the investigation workflow.

**Is the fork just an edited recording?** No. Prefix events replay into the agent;
the selected response is replaced and the remaining agent logic runs again. Every
new boundary must have an explicit mock. The rebuilt result is separately recorded.

**What is time travel here?** Scrubbing boundary-observable evidence and explicit
state snapshots. It cannot resume an arbitrary Python stack at a historical instruction.

**What about privacy?** HTTP values are redacted before storage and before the
recorded agent sees them. Detection is intentionally limited; explicit Session
values and exports still need review.

**What is ML here?** There is no trained classifier in this release. `fr similar`
uses event-count features and cosine similarity, an interpretable retrieval baseline.
Fleet embeddings/clustering and LoRA remain research extensions.

**What did you test?** Supported sync/async HTTP capture, SSE, repeated offline replay,
mutation isolation, altered traces, source drift, fail-closed fork continuation,
storage rollback, HTML injection, CLI workflows and browser interactions.

## Short Hinglish recall

- **Record:** agent ko bahar se jo value mili, usse store karo.
- **Replay:** same values wapas do; same supported run reproduce karo.
- **Compare:** pehla input ya response difference dhundo.
- **Fork:** ek response badlo, baaki logic dobara chalao, tools ko mock rakho.
- **Evidence:** test ke results dikhao; planned features ko completed mat bolo.

## Three worked examples

- `python examples/session_agent.py`: a temperature decision and safe counterfactual.
- `fr record-script examples/http_agent.py`: controlled HTTP capture with verified stdout.
- `python examples/langgraph_agent.py`: local graph state replay, 50 times; install
  `pip install -e '.[integrations]'` first. This example needs no provider key.

The demo command exports three portable JSON bundles beside its HTML. They form a
reproducible synthetic sample gallery; no public hosting or real corpus is implied.
