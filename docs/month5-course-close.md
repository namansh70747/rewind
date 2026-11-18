# Month 5 course close

Software for weeks 19–22 already lived in `main`. This page closes the leftover
**evidence** items without paid OpenAI/Anthropic keys (ADR-0015).

| Leftover | Close |
|---|---|
| Neighbors / human review | Three synthetic families; neighbors stay in-family (`course-close.json`) |
| Embeddings extra | Documented in [killer demo](killer-demo.md); optional BGE/LanceDB |
| Failure map | `fr fleet-map` on the substitute corpus |
| Prompted-LLM baseline | Live Gemini or NVIDIA via `live_prompted_predictions` when a key is set; otherwise frozen **keyword-stub-v1** |
| `fr eval` CI | Already in `.github/workflows/ci.yml`; Month 5 workflow also runs pytest |
| 672-tool fleet | Substituted with 24–30 local synthetic runs + existing NVIDIA/Gemini pairs |

Reproduce:

```bash
python -m pip install -e '.[dev,ml]'
# Optional: set GEMINI_API_KEY or NVIDIA_API_KEY first for a live prompted baseline.
python examples/month5_close_gates.py
python -m pytest tests/test_month5.py tests/test_month5_course_close.py
```

Committed evidence: [validation/month5/course-close.json](validation/month5/course-close.json).
