# ADR 0016 — Active hosted provider scope

The maintainer replaces direct OpenAI and Anthropic integrations and live gates
with Groq, Gemini, NVIDIA and xAI. Historical recordings keep their provider IDs.
The built-in verifier retains their request shapes for offline compatibility.
The integrations extra no longer installs the two retired SDKs. The HTTPX2
transport remains part of the MCP 2 path.

Groq and Gemini cover streaming/tool workflows, NVIDIA covers inference and
the optional cloud embedding route, and Grok covers model/tool capture and the
blinded evaluation baseline. Exact model and feature qualification requires
live account evidence. The original requirement wording is preserved for
traceability in the [acceptance ledger](../release-evidence/acceptance-ledger.json).

The provider substitution leaves the original fleet, required user journeys and
privacy, reliability and performance gates in place. Synthetic fixtures are
controlled test evidence. Provider catalogue status only indicates reachability.
