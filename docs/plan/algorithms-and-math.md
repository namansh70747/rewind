# Rewind — Algorithms & Math Reference

> Technical reference for the `flightrecorder` package. This document specifies the core algorithms and their mathematics for record-replay, deterministic time-travel, auto-bisect, content-addressed storage, and ML-based failure clustering.
>
> **The core law of Rewind:** *playback* (bit-exact reproduction from the boundary log) versus *re-execution* (a fork that re-runs computation). Everything below serves one of those two modes.

Part of the 6-month plan package. See sibling docs: [README](./README.md) · [tech-stack-and-oss-map](./tech-stack-and-oss-map.md) · [risks-and-spikes](./risks-and-spikes.md) · [competitive-landscape](./competitive-landscape.md) · [roadmap-6-months](./roadmap-6-months.md) · [milestones-and-exit-criteria](./milestones-and-exit-criteria.md) · [team-and-cadence](./team-and-cadence.md).

---

## Contents

1. [Record-replay determinism model](#1-record-replay-determinism-model)
2. [Boundary matching](#2-boundary-matching)
3. [Sequence alignment for auto-bisect](#3-sequence-alignment-for-auto-bisect)
4. [Content-addressed storage & dedup](#4-content-addressed-storage--dedup)
5. [Time-travel via replay-to-N with snapshots](#5-time-travel-via-replay-to-n-with-snapshots)
6. [ML math](#6-ml-math)
- [Quick reference: library map](#quick-reference-library-map)
- [Canonical references (papers)](#canonical-references-papers)

---

## 1. Record-replay determinism model

The foundational model comes from **rr** (O'Callahan et al., USENIX ATC 2017). rr treats a process as a **deterministic function of its inputs**, where "inputs" means *everything read across the boundary with the outside world*. The strategy: record only the **nondeterministic boundary events**, then inject the recorded values back on replay. rr itself records syscall results, signal timing (pinned to a retired-conditional-branch hardware counter), and thread scheduling (serialized onto one logical core).

For an **AI agent**, the boundary is the set of external reads:

- **LLM completions** — the dominant source of nondeterminism
- Tool / API responses, HTTP, DB, RAG retrievals
- Clock (`time.time()`), RNG, `uuid4()`
- Environment / config, filesystem

We model the run as a **boundary log** $B = \langle b_1, \dots, b_N \rangle$, where each event is

$$b_i = (\text{key}_i,\ \text{request}_i,\ \text{response}_i).$$

### Replay invariant (faithfulness)

> If at every boundary the agent issues the **same request in the same order** and Rewind returns the **recorded response**, then all deterministic computation *between* boundaries reproduces bit-for-bit, and the whole run is reproduced.

Formally, replay is **faithful iff** the replayed request stream is **prefix-equal, order-equal, and content-equal** to $B$.

### Faithfulness breakers

Anything that leaks nondeterminism *not* captured at the boundary causes **silent divergence**:

- Uncaptured entropy: RNG, time, `uuid`, hardware counters, `set`/`dict` ordering under `PYTHONHASHSEED`, `os.urandom`
- True concurrency / data races
- In-process floating-point nondeterminism (rare — the LLM is treated as a boundary, not in-process math)
- Hidden global state; wall-clock branching
- `asyncio` completion races
- **Any missed external read** → silent divergence

### Verification: the boundary hash-chain

We verify faithfulness with a **hash-chain** — a degenerate Merkle chain, in the same spirit as git commits or a Certificate Transparency log:

$$h_0 = H(\text{run\_metadata} \parallel \text{seed})$$
$$h_i = H\big(h_{i-1} \parallel \text{canon}(\text{request}_i) \parallel \text{canon}(\text{response}_i)\big)$$

where `canon` is a **canonical serialization**: sorted JSON keys, fixed float formatting, normalized unicode, stable tool-argument encoding. The final $h_N$ is the **run fingerprint**.

- **Integrity:** any edit to event $i$ changes $h_i$ and all $h_j$ for $j \ge i$ — detectable in $O(1)$.
- **Replay check:** recompute $h'_i$ live during replay; the **first** $i$ where $h'_i \neq h_i$ is the **exact divergence boundary**. This is a free, precise regression signal.
- A **chained** (not flat) hash gives *where* divergence happened, not merely *that* it happened, and it is streamable.

> **Cross-link / flag:** this hash-chain doubles as the **cheapest auto-bisect**. When passing and failing traces are **step-aligned**, binary-search for the first differing $h_i$ in $O(\log N)$ replays. Reserve the full $O(nm)$ sequence alignment of [§3](#3-sequence-alignment-for-auto-bisect) for the insert/delete case where traces are *not* step-aligned.

**Implement with:** `blake3` for $H$ (<https://pypi.org/project/blake3/>, <https://github.com/BLAKE3-team/BLAKE3>) + `orjson`/custom canonicalizer. Model the interception layer on rr (<https://github.com/rr-debugger/rr>). Primary reference: rr, USENIX ATC 2017 (<https://www.usenix.org/system/files/conference/atc17/atc17-o_callahan.pdf>, <https://arxiv.org/pdf/1705.05937>, <https://rr-project.org>).

**Complexity:** $O(N)$ time, $O(1)$ state.

---

## 2. Boundary matching

To replay, each live boundary call must be matched to its recorded counterpart. We use an **ordinal key** plus a **content-hash validation**.

### The key

$$\text{key} = (\text{thread\_id},\ \text{boundary\_type},\ \text{call\_site\_id},\ \text{occurrence\_index})$$

- **`call_site_id`** = a *stable* hash of `(file, qualified-function, lexical call position)`, or an explicit decorator label. **Not** a raw line number (which drifts with edits).
- **`occurrence_index`** = a monotonic counter per `(thread, call_site)`, reset at run start.

### Validation

1. Find the candidate recorded event by **key**.
2. Confirm `canon(request_live)` hashes equal to the **recorded request hash**.

Then:

- **key match + hash match** → serve the recorded response.
- **key match but hash differs** → the inputs changed → a deterministic divergence occurred **upstream** → **raise a divergence** (this is the bisect signal).

### Loops and retries

`occurrence_index` handles loops and retries cleanly: when the same `call_site` is hit repeatedly, the counter distinguishes iterations $0, 1, 2, \dots$, so the 3rd retry maps to the 3rd recorded response — **including recorded failures**. (rr uses retired-branch counts as its ordinal; a per-call-site counter suffices when the boundary is the replay unit.)

### Concurrency / async — two options

1. **Serialize onto one logical timeline** (the rr approach): only one task runs between boundaries; record the global order; replay re-imposes it. This kills interleaving nondeterminism and is the **best default** — agent frameworks are mostly single-threaded event loops.
2. **Record happens-before order** (Lamport / vector clocks): stamp each boundary with a logical clock. For `asyncio`, record the order awaitables **actually resolve** (the completion order of `gather` / `as_completed`) and replay *that*. Resolution order — not scheduling order — is what downstream code observes. A per-task `occurrence_index` keeps keys unique.

Reference: Aumayr et al., "Efficient and Deterministic Record & Replay for Actor Languages" (<https://arxiv.org/pdf/1805.06267>).

**Implement with:** custom interception — monkeypatch / context-manager shims around the LLM SDK, `httpx`/`requests`, `time`, `random` — plus a `contextvars` per-task counter.

**Complexity:** $O(1)$ amortized per match (hash-map lookup); $O(N)$ total.

---

## 3. Sequence alignment for auto-bisect

Given a **passing** trace $A = \langle a_1, \dots, a_n \rangle$ and a **failing** trace $B = \langle b_1, \dots, b_m \rangle$ of agent **decisions** (each decision = an LLM decision + a tool-call), we align them and report the **first diverging decision**. Because inserted/deleted steps matter, we need **edit-distance / alignment**, not a positional diff.

### Needleman–Wunsch (global alignment)

$$F(i,j) = \max \begin{cases} F(i-1, j-1) + s(a_i, b_j) \\ F(i-1, j) + g \\ F(i, j-1) + g \end{cases}$$

with initialization $F(i,0) = i \cdot g$, $F(0,j) = j \cdot g$, $F(0,0) = 0$. Traceback runs from $F(n,m)$; the **first cell on the optimal path** that takes a substitution with $s < 0$ or a gap is the **first diverging decision**.
(<https://en.wikipedia.org/wiki/Needleman%E2%80%93Wunsch_algorithm>)

### Smith–Waterman (local alignment)

Same recurrence with a **floor of 0**:

$$H(i,j) = \max \begin{cases} 0 \\ H(i-1, j-1) + s \\ H(i-1, j) + g \\ H(i, j-1) + g \end{cases}$$

with $H(i,0) = H(0,j) = 0$. Traceback runs from the **global max cell** and stops at the first $0$.
(<https://en.wikipedia.org/wiki/Smith%E2%80%93Waterman_algorithm>)

### Affine gaps (Gotoh)

A gap of length $\ell$ costs

$$\gamma(\ell) = -d - (\ell - 1)e$$

with **open** penalty $d$ and **extend** penalty $e$, where $e < d$. Implemented with two auxiliary matrices $E, F$ alongside $H$; still $O(nm)$.

### Dynamic time warping (DTW)

$$D(i,j) = c(i,j) + \min\{D(i-1, j),\ D(i, j-1),\ D(i-1, j-1)\}$$

with $D(0,0) = 0$ and $D(i,0) = D(0,j) = +\infty$. A **Sakoe–Chiba band** of width $w$ constrains warping → $O(wL)$.
(<https://en.wikipedia.org/wiki/Dynamic_time_warping>)

### Cost design — where "agent-ness" lives

The substitution cost must be **semantic**, not string-equality.

**Embeddings.** With cosine similarity

$$\cos(u, v) = \frac{u \cdot v}{\lVert u \rVert\, \lVert v \rVert} \in [-1, 1], \qquad d_{\cos} = 1 - \cos,$$

map to a score

$$s(a_i, b_j) = \cos(u, v) - \tau, \qquad \tau \approx 0.8.$$

(<https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html>)

**Structured tool-call diff.**

$$s = w_{\text{tool}} \cdot \mathbb{1}[\text{tool}_i = \text{tool}_j] + w_{\text{args}} \cdot \text{sim}_{\text{args}} + w_{\text{sem}} \cdot \cos(u, v)$$

where $\text{sim}_{\text{args}}$ is a normalized structured JSON diff: exact key match; value similarity via normalized Levenshtein / token-set for strings, and numeric closeness for numbers. A **different tool** yields a large negative score; the **same tool with slightly different args** yields a small penalty.

**First-divergence report.** Walk the optimal path from the start; the **first gap or below-threshold mismatch** is the bisect answer.

> **Cheaper path when traces are aligned by construction:** binary-search the boundary hash-chain of [§1](#1-record-replay-determinism-model) — $O(\log N)$ replays to the first differing $h_i$. Use full alignment here only for insert/delete cases.

**Implement with:** Biopython `Bio.Align.PairwiseAligner` (`mode='global'|'local'`, affine gaps, custom substitution; `pairwise2` deprecated since 1.80 — <https://biopython.org/docs/dev/Tutorial/chapter_pairwise.html>); RapidFuzz for $\text{sim}_{\text{args}}$ (<https://rapidfuzz.github.io/RapidFuzz/>); `dtaidistance` for banded DTW on embeddings (<https://dtaidistance.readthedocs.io>); `sentence-transformers` (<https://sbert.net>).

**Complexity:** NW / SW / DTW $O(nm)$ time, $O(nm)$ space (or $O(\min(n,m))$ score-only via Hirschberg); banded DTW $O(wL)$; embedding is a one-time $O(n+m)$.

---

## 4. Content-addressed storage & dedup

Every payload is stored under its own hash:

$$\text{addr} = H(\text{bytes}).$$

Identical payloads are stored **once** (e.g. a system prompt repeated across 10k steps is stored a single time). Objects are **immutable** and **self-verifying** — re-hash on read to detect corruption.

### BLAKE3 vs SHA-256

Both are cryptographically strong. **Pick BLAKE3:**

- 4–10× faster
- Internal Merkle tree → parallel / streamable (tens of GB/s multicore, vs SHA-256's sequential Merkle–Damgård)
- Free verified streaming

Use SHA-256 **only if FIPS compliance is required**. (<https://github.com/BLAKE3-team/BLAKE3>, <https://guptadeepak.com/blake2-and-blake3-high-performance-hashing-alternatives/>)

### Collision probability (birthday bound)

$$P(\text{collision}) \approx \frac{n^2}{2^{b+1}}, \qquad P \approx 0.5 \text{ at } n \approx 2^{b/2}.$$

For $b = 256$ bits → $2^{128}$ resistance. At $n = 10^{12}$ objects, $P \approx 10^{-53}$ — negligible. Therefore **same hash $\Rightarrow$ same content** in practice. (<https://www.johndcook.com/blog/2017/01/10/probability-of-secure-hash-collisions/>)

### Garbage collection

**Ref-counted:** each object's refcount = number of pointers to it. Deleting a run decrements; sweep objects at count $0$.

- Immediate refcount: $O(1)$ per change (content DAGs are usually cycle-free)
- Periodic mark-and-sweep: $O(V + E)$

### Optional: CDC + Merkle for large near-duplicate blobs

For big, slightly-changed blobs, use **content-defined chunking (FastCDC**, USENIX ATC 2016). FastCDC uses a **Gear rolling hash**

$$\text{fp} = (\text{fp} \ll 1) + G(b)$$

where $G$ is a 256-entry table of random 64-bit values, plus **cut-point skipping** and **normalization** — roughly 10× faster than Rabin. Store the blob as a **Merkle tree of chunk hashes**; unchanged chunks are shared across versions. (<https://www.usenix.org/system/files/conference/atc16/atc16-paper-xia.pdf>)

**Implement with:** `blake3` (<https://pypi.org/project/blake3/>); `fastcdc` (<https://github.com/nlfiedler/fastcdc-py>); a key→bytes store (SQLite / LMDB / filesystem sharded by hash prefix).

**Complexity:** put/get $O(L)$; dedup lookup $O(1)$; GC $O(1)$ per edit or $O(V+E)$ per sweep; CDC $O(L)$.

---

## 5. Time-travel via replay-to-N with snapshots

To reconstruct state at step $t$: **restore the nearest snapshot $\le t$**, then **deterministically replay forward** via the boundary log.

Snapshot every $k$ steps ($N/k$ snapshots total). The expected distance back to the nearest earlier snapshot is $k/2$, so the expected replay work is

$$W_{\text{replay}} \approx \frac{k}{2} \text{ boundaries}, \qquad S \approx \frac{N}{k} \text{ snapshots}.$$

### Optimal snapshot interval

With replay cost $c_r$ per boundary and snapshot cost $c_s$ each:

$$C(k) = c_r \cdot \frac{k}{2} + c_s \cdot \frac{N}{k}.$$

Setting $\dfrac{dC}{dk} = \dfrac{c_r}{2} - \dfrac{c_s N}{k^2} = 0$ gives

$$k^\ast = \sqrt{\frac{2\, c_s\, N}{c_r}} = \Theta(\sqrt{N}),$$

so $S = \Theta(\sqrt{N})$ and $W_{\text{replay}} = \Theta(\sqrt{N})$.

This is the **classic $\sqrt{N}$ space-time balance** — the same result as $O(\sqrt{N})$ gradient checkpointing and Bennett pebbling. If $c_s \ll c_r$, shrink $k$; if state is huge ($c_s \gg c_r$), enlarge $k$.

### Refinements

- **Incremental / copy-on-write snapshots:** store the delta since the previous snapshot; pairs with CAS + CDC ([§4](#4-content-addressed-storage--dedup)); drops $c_s$.
- **Two-tier:** sparse full snapshots + boundary log as the *always* source of truth. Snapshots are **pure accelerators, never authoritative**.

### State serialization options

| Option | Captures | Portable? |
|---|---|---|
| `pickle` / `cloudpickle` | arbitrary graphs incl. closures | no |
| `dill` | lambdas, live state | no |
| Schema'd (`pydantic` / `msgpack` / `protobuf`) | declared fields | yes, diff-friendly |
| Process-level (CRIU, or `fork()`-COW like rr) | whole process | no |

**Recommendation:** schema'd serialization of the **logical state** (messages, memory, scratchpad, tool cursors) into CAS — deduped and CDC-chunked — with the boundary log as the deterministic bridge.

**Implement with:** `cloudpickle` / `dill` (<https://github.com/cloudpipe/cloudpickle>) or `msgpack`; store deltas in the [§4](#4-content-addressed-storage--dedup) CAS.

**Complexity:** reach any step in $O(k) = O(\sqrt{N})$ boundaries; storage $O(N/k) = O(\sqrt{N})$; snapshot write $O(\lvert \text{state delta} \rvert)$.

> **Flag:** $k^\ast = \Theta(\sqrt{N})$ assumes uniform access and comparable snapshot/replay costs. Agent state snapshots are **large**, so expect $c_s \gg c_r$, which pushes $k$ **up** — pair with COW/CDC incremental snapshots to pull $c_s$ back down.

---

## 6. ML math

Used for **clustering and root-causing failures** across many runs.

### (a) Embedding similarity

$$\cos(u, v) = \frac{u \cdot v}{\lVert u \rVert\, \lVert v \rVert}, \qquad d = 1 - \cos.$$

Normalize vectors to unit length so that **cosine = dot product**.
**Implement with:** `sentence-transformers` (<https://sbert.net>).

### (b) HDBSCAN

(Campello, Moulavi, Sander — 2013 / TKDD 2015; <https://hdbscan.readthedocs.io>, <https://pberba.github.io/stats/2020/01/17/hdbscan/>)

- **Core distance:** $\text{core}_k(x)$ = distance to the $k$-th nearest neighbor.
- **Mutual reachability distance:**

$$d_{\text{mreach}}(a, b) = \max\{\text{core}_k(a),\ \text{core}_k(b),\ d(a, b)\}.$$

- Build the **MST** under $d_{\text{mreach}}$, then form a hierarchy by removing edges in order of decreasing weight (single-linkage on mutual reachability).
- **Condense** with `min_cluster_size`: the small side falls out as noise; when both sides are large it is a genuine split.
- Let $\lambda = 1/\text{distance}$. Cluster **stability**:

$$\text{Stability}(C) = \sum_{p \in C} \big(\lambda_{\text{death}}(p) - \lambda_{\text{birth}}(C)\big).$$

- **Flat extraction** maximizes total stability: keep a node if its stability exceeds the sum of its children's, else descend. This auto-selects the number of clusters and labels low-density points as noise.

**Complexity:** ~$O(n \log n)$ typical (space-tree MST); worst case $O(n^2)$ in high dimension.

### (c) UMAP

(McInnes / Healy / Melville; <https://arxiv.org/pdf/1802.03426>)

Build a weighted kNN graph → **fuzzy simplicial set** using locally-adaptive exponential kernels, with a per-point $\sigma_i$ chosen so the effective neighbor count is $\log_2 k$, then a symmetrized fuzzy union. The low-dimensional embedding minimizes the cross-entropy

$$C = \sum_{ij} \left[ p_{ij} \log \frac{p_{ij}}{q_{ij}} + (1 - p_{ij}) \log \frac{1 - p_{ij}}{1 - q_{ij}} \right], \qquad q_{ij} = \big(1 + a \lVert y_i - y_j \rVert^{2b}\big)^{-1},$$

optimized by SGD with negative sampling. Use for visualization, or as a **pre-reduction step before HDBSCAN**.
**Complexity:** ~$O(n^{1.14})$. **Implement with:** `umap-learn`.

### (d) Weak supervision / Snorkel

(Ratner et al., NeurIPS 2016 data programming, <https://arxiv.org/abs/1605.07723>; Snorkel VLDB 2018, <https://arxiv.org/pdf/1711.10160>)

**Labeling functions** (LFs) each vote a class or abstain. A **generative label model** learns each LF's latent accuracy and correlations from their agreements — **no ground truth** — yielding a probabilistic label $P(y \mid \Lambda)$.

Independent model:

$$p_\theta(\Lambda, y) \propto \exp\left( \sum_j \theta_j\, \lambda_j\, y \right),$$

fit by maximizing the marginal likelihood

$$\max_\theta \sum_i \log \sum_y p_\theta(\Lambda_i, y) \quad \text{(EM / SGD)}.$$

The full model adds correlation factors. The resulting **soft labels** train a noise-aware downstream classifier.

**Implement with:** Snorkel `LabelModel` (<https://snorkel.org>) — but note it is **near-unmaintained**; hand-written LFs are perfectly fine.
**Complexity:** LF apply $O(n \cdot L)$; fit $O(\text{iters} \cdot n \cdot L)$.

### (e) LoRA

(Hu et al., <https://arxiv.org/abs/2106.09685>)

Freeze $W_0 \in \mathbb{R}^{d \times k}$ and learn a low-rank update:

$$W' = W_0 + \Delta W = W_0 + \frac{\alpha}{r} B A, \qquad B \in \mathbb{R}^{d \times r},\ A \in \mathbb{R}^{r \times k},\ r \ll \min(d, k).$$

The forward pass is

$$h = W_0 x + \frac{\alpha}{r} B A x.$$

Initialize $A$ Gaussian and $B = 0$ (so $\Delta W = 0$ at start); $\alpha/r$ is a fixed scaling (rule of thumb $\alpha = 2r$). Trainable params $r(d + k) \ll d \cdot k$ (up to ~10,000× fewer), and $\Delta W$ is **mergeable** into $W_0$ at inference (zero added latency).

### (f) QLoRA

(Dettmers et al., <https://arxiv.org/abs/2305.14314>)

- **4-bit NF4** quantization (quantile quantization, information-theoretically optimal for zero-centered normal weights) — storage only; dequantize to bf16 per matmul.
- **Double quantization:** quantize the scales themselves (~0.37 bits/param).
- **Paged optimizers:** unified memory to absorb gradient-checkpoint spikes.
- **Net result:** fine-tune a frozen 4-bit base with bf16 LoRA adapters at ~16-bit quality — 65B on a single 48GB GPU.

**Implement with (e + f):** HF PEFT (<https://github.com/huggingface/peft>) + bitsandbytes (<https://github.com/bitsandbytes-foundation/bitsandbytes>).
**Complexity:** dominated by the frozen base forward/backward; extra LoRA cost is $O(r(d + k))$ params.

---

## Quick reference: library map

| § | Topic | Implement with | URL |
|---|---|---|---|
| 1 | Hash-chain / fingerprint | `blake3`, `orjson`/custom canonicalizer; model on rr | <https://pypi.org/project/blake3/> · <https://github.com/rr-debugger/rr> |
| 2 | Boundary matching | custom interception (monkeypatch/shims) + `contextvars` | — |
| 3 | Sequence alignment | Biopython `PairwiseAligner`, RapidFuzz, `dtaidistance`, `sentence-transformers` | <https://biopython.org/docs/dev/Tutorial/chapter_pairwise.html> · <https://rapidfuzz.github.io/RapidFuzz/> · <https://dtaidistance.readthedocs.io> · <https://sbert.net> |
| 4 | CAS & dedup | `blake3`, `fastcdc`, SQLite/LMDB/sharded FS | <https://pypi.org/project/blake3/> · <https://github.com/nlfiedler/fastcdc-py> |
| 5 | Time-travel snapshots | `cloudpickle`/`dill` or `msgpack`; deltas in §4 CAS | <https://github.com/cloudpipe/cloudpickle> |
| 6a | Embedding similarity | `sentence-transformers` | <https://sbert.net> |
| 6b | HDBSCAN | `hdbscan` | <https://hdbscan.readthedocs.io> |
| 6c | UMAP | `umap-learn` | <https://arxiv.org/pdf/1802.03426> |
| 6d | Weak supervision | Snorkel `LabelModel` (near-unmaintained) | <https://snorkel.org> |
| 6e/f | LoRA / QLoRA | HF PEFT + bitsandbytes | <https://github.com/huggingface/peft> · <https://github.com/bitsandbytes-foundation/bitsandbytes> |

---

## Canonical references (papers)

- **rr** — O'Callahan et al., USENIX ATC 2017. <https://www.usenix.org/system/files/conference/atc17/atc17-o_callahan.pdf> · <https://arxiv.org/pdf/1705.05937>
- **Record & Replay for Actor Languages** — Aumayr et al. <https://arxiv.org/pdf/1805.06267>
- **Needleman–Wunsch** — <https://en.wikipedia.org/wiki/Needleman%E2%80%93Wunsch_algorithm>
- **Smith–Waterman** — <https://en.wikipedia.org/wiki/Smith%E2%80%93Waterman_algorithm>
- **Dynamic time warping** — <https://en.wikipedia.org/wiki/Dynamic_time_warping>
- **BLAKE3** — <https://github.com/BLAKE3-team/BLAKE3>
- **FastCDC** — USENIX ATC 2016. <https://www.usenix.org/system/files/conference/atc16/atc16-paper-xia.pdf>
- **HDBSCAN** — Campello, Moulavi, Sander (2013 / TKDD 2015). <https://hdbscan.readthedocs.io>
- **UMAP** — McInnes, Healy, Melville. <https://arxiv.org/pdf/1802.03426>
- **Data Programming** — Ratner et al., NeurIPS 2016. <https://arxiv.org/abs/1605.07723>
- **Snorkel** — VLDB 2018. <https://arxiv.org/pdf/1711.10160>
- **LoRA** — Hu et al. <https://arxiv.org/abs/2106.09685>
- **QLoRA** — Dettmers et al. <https://arxiv.org/abs/2305.14314>
