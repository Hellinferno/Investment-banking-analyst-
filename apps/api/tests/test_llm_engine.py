from types import SimpleNamespace

from engine import llm


def test_gemini_model_is_configurable_and_uses_supported_config(monkeypatch):
    captured = {}

    class Models:
        @staticmethod
        def generate_content(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="ok")

    monkeypatch.setattr(llm, "gemini_client", SimpleNamespace(models=Models()))
    monkeypatch.setattr(llm, "GEMINI_MODEL", "gemini-test-model")

    assert llm._call_gemini("system", "user") == "ok"
    assert captured["model"] == "gemini-test-model"
    assert captured["contents"] == "user"
    assert captured["config"].system_instruction == "system"
    assert captured["config"].temperature is None
