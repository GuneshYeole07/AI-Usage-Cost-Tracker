from app.pricing import DEFAULT_PRICE, family, price_for, turn_cost


def test_fable_has_its_own_price():
    p = price_for("claude-fable-5-2")
    assert p != DEFAULT_PRICE
    assert (p.input, p.output) == (8.0, 40.0)
    assert family("claude-fable-5-2") == "fable"


def test_fable_turn_cost():
    # 1M of each: input $8 + output $40 + cache write $10 + cache read $0.20
    cost = turn_cost("claude-fable-5-2", 1_000_000, 1_000_000, 1_000_000, 1_000_000)
    assert abs(cost - 58.20) < 1e-9
