"""An API-key-free failure investigation using explicitly simulated external services.

A travel agent uses a stale price quote. Intervening on that quote changes the
actual execution path from over-budget to a successful simulated reservation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .boundary import Cassette, Session
from .fork import Mock, fork_run

if TYPE_CHECKING:
    import httpx

    from .replay import Run

SCENARIO = "travel-budget-v1"
BUDGET = 500


def _reservation(request: Any) -> dict[str, Any]:
    price = request["price"]
    return {
        "status": "confirmed" if price <= BUDGET else "over_budget",
        "total": price,
        "budget": BUDGET,
        "simulated": True,
    }


def demo_mocks() -> dict[tuple[str, str], Mock]:
    return {
        ("tool", "reserve_trip"): _reservation,
        ("state", "agent_state"): lambda request: request,
        ("llm", "explain_result"): lambda request: {
            "text": "Trip reserved within budget."
            if request["status"] == "confirmed"
            else "Reservation rejected: the quote exceeds the budget."
        },
    }


def make_demo_run(quote: int = 720) -> Run:
    def run(session: Session, inner: httpx.BaseTransport | None) -> str:
        task = {"destination": "Jaipur", "budget": BUDGET, "currency": "INR"}
        session.mediate("input", "travel_request", None, lambda: task)
        session.mediate("clock", "time", None, lambda: 1780000000.0)
        session.mediate(
            "llm",
            "plan_trip",
            task,
            lambda: {"tool": "price_lookup", "reason": "Check the fare before booking."},
        )
        fare = session.mediate(
            "tool",
            "price_lookup",
            {"destination": "Jaipur"},
            lambda: {"price": quote, "currency": "INR", "source": "simulated-cache"},
        )
        state = {**task, "quoted_price": fare["price"], "within_budget": fare["price"] <= BUDGET}
        session.mediate("state", "agent_state", state, lambda: state)
        request = {"destination": "Jaipur", "price": fare["price"]}
        result = session.mediate("tool", "reserve_trip", request, lambda: _reservation(request))
        explanation = session.mediate(
            "llm", "explain_result", result, lambda: demo_mocks()[("llm", "explain_result")](result)
        )
        return json.dumps({**result, "explanation": explanation["text"]}, sort_keys=True)

    return run


def record_demo(quote: int = 720) -> Cassette:
    session = Session("record")
    output = make_demo_run(quote)(session, None)
    return Cassette(
        session.boundaries,
        session.chain,
        output,
        "demo",
        SCENARIO,
        {"scenario": SCENARIO, "simulated": True},
    )


def recover_demo(parent: Cassette, price: int = 420) -> Cassette:
    if parent.provider != "demo" or parent.model != SCENARIO:
        raise ValueError("the CLI recovery scenario supports travel-budget-v1 demo runs only")
    if price < 0:
        raise ValueError("price cannot be negative")
    return fork_run(
        parent,
        make_demo_run(),
        at=3,
        value={"price": price, "currency": "INR", "source": "simulated-cache"},
        mocks=demo_mocks(),
    )
