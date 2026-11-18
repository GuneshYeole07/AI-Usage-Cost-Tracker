from app.rules import analyze_session
from tests.helpers import make_session


def rules_of(s):
    return {f.rule: f for f in analyze_session(s)}


def test_efficient_session_has_no_findings():
    s = make_session([12_000 + 2_500 * i for i in range(20)])  # ends at ~60k
    assert analyze_session(s) == []


def test_long_chat_is_flagged_with_conservative_waste():
    contexts = [12_000 + 4_000 * i for i in range(60)]  # first above 100k at index 23, ends ~248k
    f = rules_of(make_session(contexts))["long_context"]
    assert f.tokens_wasted > 0
    # Never claims more than "everything above a fresh baseline".
    assert f.tokens_wasted <= sum(c - 20_000 for c in contexts if c > 100_000)
    # And clearly less than that naive number, because a fresh chat regrows too.
    assert f.tokens_wasted < 0.9 * sum(c - 20_000 for c in contexts if c > 100_000)
    # Context first passes 100k at index 23; the reset happens after that turn,
    # so the crossing turn itself is not counted and waste starts on the next one.
    assert f.turns[0] == 24
    assert 23 not in f.turns
    assert f.cost_wasted > 0


def test_long_chat_evidence_counts_only_later_messages():
    contexts = [12_000 + 4_000 * i for i in range(60)]  # crosses at index 23 (turn 24)
    f = rules_of(make_session(contexts))["long_context"]
    assert "at turn 24 " in f.evidence
    later = len(contexts) - 24  # turns after the crossing one
    assert len(f.turns) == later
    assert f"made {later} later messages lighter" in f.evidence


def test_real_compaction_stops_the_waste_count():
    grow = [20_000 + 5_000 * i for i in range(20)]  # up to 115k
    after_compact = [30_000 + 2_000 * i for i in range(15)]  # user compacted, stays small
    f = rules_of(make_session(grow + after_compact)).get("long_context")
    flagged = set(f.turns) if f else set()
    assert not flagged & set(range(20, 35))


def test_agent_loop():
    errors = [0, 0, 1, 1, 1, 1, 1, 1, 0, 0]
    f = rules_of(make_session([15_000 + 1_000 * i for i in range(10)], errors=errors))["agent_loop"]
    assert f.turns == [2, 3, 4, 5, 6, 7]
    # first 2 retries are allowed; 4 turns counted as waste
    assert f.tokens_wasted == sum((15_000 + 1_000 * i) + 300 for i in (4, 5, 6, 7))


def test_three_errors_is_not_a_loop():
    errors = [0, 1, 1, 1, 0, 0]
    assert "agent_loop" not in rules_of(make_session([15_000] * 6, errors=errors))


def test_repeated_reads():
    read = [{"file": "abc", "tokens": 4_000}]
    reads = [read, read, read, read, read, []]
    f = rules_of(make_session([15_000 + 4_000 * i for i in range(6)], reads=reads))["repeated_reads"]
    assert f.tokens_wasted == 3 * 4_000  # 5 reads, 2 allowed


def test_tool_overhead():
    f = rules_of(make_session([80_000 + 1_000 * i for i in range(10)]))["tool_overhead"]
    assert f.tokens_wasted == (80_000 - 50_000) * 10
    # a normal Claude Code start (~50k) is not flagged
    assert "tool_overhead" not in rules_of(make_session([50_000 + 1_000 * i for i in range(10)]))


def test_long_chat_baseline_is_never_below_session_start():
    contexts = [60_000 + 4_000 * i for i in range(40)]
    f = rules_of(make_session(contexts))["long_context"]
    # waste can never exceed "context above this session's own starting size"
    assert f.tokens_wasted <= sum(c - 60_000 for c in contexts if c > 100_000)


def test_big_model_small_task():
    s = make_session([13_000, 14_000, 15_000], model="claude-opus-4-5", outputs=[100, 120, 90])
    f = rules_of(s)["model_choice"]
    assert f.cost_wasted > 0 and f.tokens_wasted == 0
    assert "model_choice" not in rules_of(make_session([13_000, 14_000, 15_000], outputs=[100, 120, 90]))


def test_cache_miss():
    s = make_session([20_000 + 1_000 * i for i in range(12)], cached=False)
    assert "cache_miss" in rules_of(s)
    assert "cache_miss" not in rules_of(make_session([20_000 + 1_000 * i for i in range(12)]))


def test_no_double_counting_between_rules():
    contexts = [80_000 + 5_000 * i for i in range(40)]  # heavy startup AND long chat
    s = make_session(contexts)
    total = sum(t.total_tokens for t in s.turns)
    assert sum(f.tokens_wasted for f in analyze_session(s)) < total
