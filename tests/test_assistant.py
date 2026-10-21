"""Tests for the tool loop. A fake Claude client plays back scripted answers, no API key."""

import json
from types import SimpleNamespace

import pytest
from sample_data import RAW

from o2c import db
from o2c.assistant import MAX_ROUNDS, TOOLS, Assistant
from o2c.sync import run_sync


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(name, tool_input, id_="toolu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=id_)


def response(*blocks, stop="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop)


class FakeClaude:
    """Returns the scripted responses in order and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        # copy the list: the assistant keeps appending to the same one
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    folder = tmp_path_factory.mktemp("fixtures")
    for name, rows in RAW.items():
        (folder / f"{name}.json").write_text(json.dumps(rows))
    engine = db.get_engine(f"sqlite:///{folder / 'test.db'}")
    run_sync(None, engine, fixture_dir=folder)
    yield engine
    engine.dispose()


def make(engine, *responses):
    fake = FakeClaude(*responses)
    kb = lambda q: [{"source": "07.md", "heading": "x", "text": f"note for {q}", "score": 0.9}]  # noqa: E731
    return Assistant(engine, client=fake, model="test-model", knowledge_search=kb), fake


def test_plain_answer_without_tools(engine):
    assistant, fake = make(engine, response(text("Hallo!")))
    reply = assistant.chat("Hi")
    assert reply.answer == "Hallo!"
    assert reply.tool_calls == []
    assert fake.requests[0]["tools"] == TOOLS


def test_tool_call_runs_query_and_sends_result_back(engine):
    assistant, fake = make(
        engine,
        response(tool_use("get_delivered_not_billed", {}), stop="tool_use"),
        response(text("Lieferung 80000001 zu Auftrag 3 ist nicht fakturiert.")),
    )
    reply = assistant.chat("Was ist geliefert, aber nicht fakturiert?")

    assert "80000001" in reply.answer
    assert reply.tool_calls[0].name == "get_delivered_not_billed"
    # second request carries the tool result with the real delivery number
    result_msg = fake.requests[1]["messages"][-1]["content"][0]
    assert result_msg["type"] == "tool_result" and result_msg["tool_use_id"] == "toolu_1"
    assert "80000001" in result_msg["content"]
    assert result_msg["is_error"] is False


def test_two_tools_in_one_turn(engine):
    assistant, _ = make(
        engine,
        response(
            tool_use("find_customers", {"name": "DE 1"}, "t1"),
            tool_use("search_process_knowledge", {"query": "Warenausgang"}, "t2"),
            stop="tool_use",
        ),
        response(text("ok")),
    )
    reply = assistant.chat("Kunde DE 1?")
    assert [c.name for c in reply.tool_calls] == ["find_customers", "search_process_knowledge"]
    assert reply.tool_calls[0].output[0]["customer_id"] == "17100001"


def test_unknown_tool_is_reported_as_error(engine):
    assistant, fake = make(
        engine,
        response(tool_use("delete_order", {"order_id": "1"}), stop="tool_use"),
        response(text("Das kann ich nicht.")),
    )
    reply = assistant.chat("Lösche Auftrag 1")
    assert reply.tool_calls[0].is_error
    assert fake.requests[1]["messages"][-1]["content"][0]["is_error"] is True


def test_wrong_parameters_become_error_not_crash(engine):
    assistant, _ = make(
        engine,
        response(tool_use("get_order_details", {"order": "1"}), stop="tool_use"),
        response(text("Fehler korrigiert.")),
    )
    reply = assistant.chat("Auftrag 1?")
    assert reply.tool_calls[0].is_error
    assert "TypeError" in reply.tool_calls[0].output


def test_loop_stops_after_max_rounds(engine):
    endless = [response(tool_use("top_customers", {"n": 1}), stop="tool_use")] * MAX_ROUNDS
    assistant, _ = make(engine, *endless)
    reply = assistant.chat("?")
    assert len(reply.tool_calls) == MAX_ROUNDS
    assert "nicht in wenigen Schritten" in reply.answer


def test_history_is_sent_before_question(engine):
    assistant, fake = make(engine, response(text("ok")))
    history = [{"role": "user", "content": "A"}, {"role": "assistant", "content": "B"}]
    assistant.chat("C", history)
    assert [m["content"] for m in fake.requests[0]["messages"]] == ["A", "B", "C"]
