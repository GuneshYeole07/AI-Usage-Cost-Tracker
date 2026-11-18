from pathlib import Path

from app.parser import hash_path, parse_claude_code

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def _parse():
    with open(FIXTURE, encoding="utf-8") as fh:
        return parse_claude_code(fh, user="gunesh")


def test_one_session_with_deduplicated_turns():
    sessions, report = _parse()
    assert len(sessions) == 1
    s = sessions[0]
    # msg_01 is written on two lines but is ONE model call; <synthetic> is skipped.
    assert len(s.turns) == 3
    assert report.bad_lines == 1
    assert s.user == "gunesh"
    assert s.project == "shop-api"  # from a Windows-style cwd


def test_usage_counted_once():
    s = _parse()[0][0]
    t1, t2, t3 = s.turns
    assert (t1.cache_creation_tokens, t1.output_tokens) == (13000, 150)
    assert t1.context_tokens == 13012
    assert t2.context_tokens == 8 + 2400 + 13000
    assert t3.cache_read_tokens == 15400


def test_tool_calls_errors_and_reads():
    s = _parse()[0][0]
    t1, t2, t3 = s.turns
    assert t1.tool_names == ["Read"] and t1.tool_errors == 0
    assert t1.file_reads == [{"file": hash_path("C:\\Users\\dev\\projects\\shop-api\\checkout.py"), "tokens": 2000}]
    assert t2.tool_names == ["Bash"] and t2.tool_errors == 1
    assert t3.tool_calls == 0


def test_no_prompt_text_is_kept():
    s = _parse()[0][0]
    blob = repr([(t.model, t.tool_names, t.file_reads) for t in s.turns]) + s.project + s.user + s.id
    assert "SECRET" not in blob
    assert "checkout.py" not in blob  # file paths are hashed


def test_garbage_input_does_not_crash():
    sessions, report = parse_claude_code(["", "not json", "[1,2]", '{"type":"assistant"}', '{"sessionId":"x","type":"user"}'], "u")
    assert sessions == []
    assert report.bad_lines == 2
