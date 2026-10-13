import json

from models.local_model import LocalModel


class _Resp:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def _model():
    return LocalModel(model_name="m", mode="ollama", temperature=0, max_tokens=50)


def _capture(monkeypatch, body):
    sent = {}

    def fake_post(url, json=None, **kwargs):
        sent["payload"] = json
        return _Resp(body)

    monkeypatch.setattr("models.local_model.requests.post", fake_post)
    return sent


def test_think_unset_sends_no_think_field(monkeypatch):
    monkeypatch.delenv("JBF_OLLAMA_THINK", raising=False)
    sent = _capture(monkeypatch, {"response": "a", "done": True})
    _model().query("hello")
    assert "think" not in sent["payload"]


def test_think_false_is_sent_and_trace_is_empty(monkeypatch):
    monkeypatch.setenv("JBF_OLLAMA_THINK", "false")
    sent = _capture(monkeypatch, {"response": "a", "done": True})
    out = _model().query("hello")
    assert sent["payload"]["think"] is False
    assert out["thinking"] == ""


def test_think_true_returns_trace_separately(monkeypatch):
    monkeypatch.setenv("JBF_OLLAMA_THINK", "true")
    sent = _capture(monkeypatch, {"response": "answer", "thinking": "reasoning", "done": True})
    out = _model().query("hello")
    assert sent["payload"]["think"] is True
    assert out["text"] == "answer"
    assert out["thinking"] == "reasoning"


def test_garbage_value_is_ignored(monkeypatch):
    monkeypatch.setenv("JBF_OLLAMA_THINK", "maybe")
    sent = _capture(monkeypatch, {"response": "a", "done": True})
    _model().query("hello")
    assert "think" not in sent["payload"]
    json.dumps(sent["payload"])  # still serialisable


def test_model_without_thinking_mode_is_retried_without_the_field(monkeypatch):
    monkeypatch.setenv("JBF_OLLAMA_THINK", "false")
    calls = []

    class Bad(_Resp):
        status_code = 400
        text = '{"error":"\\"m\\" does not support thinking"}'

        def raise_for_status(self):
            raise AssertionError("must not be called on the rejected request")

    def fake_post(url, json=None, **kwargs):
        calls.append(dict(json))
        return Bad({}) if "think" in json else _Resp({"response": "ok", "done": True})

    monkeypatch.setattr("models.local_model.requests.post", fake_post)
    out = _model().query("hello")
    assert out["text"] == "ok"
    assert "think" in calls[0] and "think" not in calls[1]
