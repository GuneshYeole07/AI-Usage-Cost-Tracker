"""Model pricing in USD per million tokens.

These are APPROXIMATE list prices used for estimates only. Update them to your
provider's current rates; every cost figure in the app flows from this table.
Cache multipliers follow Anthropic's published scheme (write = 1.25x input, read = 0.1x input).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_write_mult: float = 1.25
    cache_read_mult: float = 0.10


# Matched by substring against the model name (first match wins, so order matters).
PRICES: list[tuple[str, Price]] = [
    # Claude Fable 5.2: $8 / $40, cache reads $0.20 (= 0.025x input, not the usual 0.1x).
    ("fable", Price(input=8.0, output=40.0, cache_read_mult=0.025)),
    ("opus", Price(input=5.0, output=25.0)),
    ("sonnet", Price(input=3.0, output=15.0)),
    ("haiku", Price(input=1.0, output=5.0)),
    ("gpt-4o-mini", Price(input=0.15, output=0.60)),
    ("gpt-4o", Price(input=2.5, output=10.0)),
    ("gpt-5", Price(input=1.25, output=10.0)),
    ("gemini", Price(input=1.25, output=10.0)),
]
DEFAULT_PRICE = Price(input=3.0, output=15.0)

# Cheaper model a small task could have used instead (top-tier models only, to stay conservative).
DOWNGRADE = {"opus": "sonnet", "gpt-4o": "gpt-4o-mini", "gpt-5": "gpt-4o-mini"}


def price_for(model: str) -> Price:
    m = (model or "").lower()
    for key, price in PRICES:
        if key in m:
            return price
    return DEFAULT_PRICE


def family(model: str) -> str:
    m = (model or "").lower()
    for key, _ in PRICES:
        if key in m:
            return key
    return "other"


def turn_input_cost(model: str, input_tokens: int, cache_creation: int, cache_read: int) -> float:
    p = price_for(model)
    return (
        input_tokens * p.input
        + cache_creation * p.input * p.cache_write_mult
        + cache_read * p.input * p.cache_read_mult
    ) / 1_000_000


def turn_cost(model: str, input_tokens: int, output_tokens: int, cache_creation: int, cache_read: int) -> float:
    p = price_for(model)
    return turn_input_cost(model, input_tokens, cache_creation, cache_read) + output_tokens * p.output / 1_000_000
