"""Offline HTTP example: fr record-script examples/http_agent.py.

A MockTransport supplies a simulated provider response at recording time.
On replay, Rewind serves the cassette before that transport is invoked.
"""

import httpx

with httpx.Client(
    transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"answer": 42}))
) as client:
    print(client.get("https://simulated-provider.invalid/answer").json()["answer"])
