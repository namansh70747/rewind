# Month 5 substitute evaluation proposal

The implementation is merged, but real-fleet evaluation and independent review
are pending. [ADR-0015](adr/0015-course-provider-substitution.md) proposes a smaller
course exercise; approval has not been recorded.

The runner exercises neighbors, three synthetic symptom families, fresh-failure
matching and a replay policy gate. Its offline keyword baseline is not a
prompted LLM. Ties and losses are retained; no baseline predictions are degraded.
Human evaluation is reported as not performed.

```bash
python -m pip install -e '.[dev,ml]'
python examples/month5_close_gates.py
python -m pytest tests/test_month5.py tests/test_month5_course_close.py
```

An explicitly requested `--live` baseline sends the blinded synthetic features
to Gemini or NVIDIA and may incur charges. It requires configured credentials
and fails if credentials or valid model output are missing. It never falls back
to the heuristic while claiming a live comparison.

See [generated synthetic report](validation/month5/course-close.json). It does
not attest original production, course approval, or public release completion.
