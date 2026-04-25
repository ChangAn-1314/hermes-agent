from gateway.run import _resolve_runtime_agent_kwargs
from hermes_cli import runtime_provider as rp
from run_agent import AIAgent


TEST_CONFIG = {
    "model": {
        "provider": "custom",
        "default": "gpt-5.4",
        "base_url": "https://api.ikuncode.cc/v1",
    },
    "custom_providers": [
        {
            "name": "XcodeGPT",
            "base_url": "https://xcode.best/v1",
            "api_key": "sk-xcode",
            "model": "gpt-5.4",
            "api_mode": "chat_completions",
        },
        {
            "name": "IkunCodeClaude",
            "base_url": "https://api.ikuncode.cc/v1",
            "api_key": "sk-claude",
            "model": "claude-sonnet-4-6",
        },
        {
            "name": "IkunCodeGPT",
            "base_url": "https://api.ikuncode.cc/v1",
            "api_key": "sk-gpt",
            "model": "gpt-5.4",
            "api_mode": "chat_completions",
        },
    ],
}


class TestCustomProviderRouting:
    def test_named_custom_provider_keeps_distinct_source_and_key(self, monkeypatch):
        monkeypatch.setattr(rp, "load_config", lambda: TEST_CONFIG)
        monkeypatch.setattr(rp, "get_compatible_custom_providers", lambda config: config["custom_providers"])

        runtime = rp.resolve_runtime_provider(requested="custom:ikuncodegpt")

        assert runtime["provider"] == "custom"
        assert runtime["api_mode"] == "chat_completions"
        assert runtime["base_url"] == "https://api.ikuncode.cc/v1"
        assert runtime["api_key"] == "sk-gpt"
        assert runtime.get("source") == "custom_provider:IkunCodeGPT"
        assert runtime.get("model") == "gpt-5.4"

    def test_gateway_runtime_prefers_configured_custom_provider_name(self, monkeypatch):
        monkeypatch.setattr(rp, "load_config", lambda: TEST_CONFIG)
        monkeypatch.setattr(rp, "get_compatible_custom_providers", lambda config: config["custom_providers"])
        monkeypatch.delenv("HERMES_INFERENCE_PROVIDER", raising=False)

        runtime = _resolve_runtime_agent_kwargs()

        assert runtime["provider"] == "custom"
        assert runtime["api_mode"] == "chat_completions"
        assert runtime["base_url"] == "https://api.ikuncode.cc/v1"
        assert runtime["api_key"] == "sk-gpt"
        assert runtime.get("source") == "custom_provider:IkunCodeGPT"

    def test_custom_chat_completions_forwards_reasoning_effort(self):
        agent = AIAgent(
            model="gpt-5.4",
            provider="custom",
            api_mode="chat_completions",
            base_url="https://xcode.best/v1",
            api_key="sk-test",
            reasoning_config={"enabled": True, "effort": "high"},
        )
        agent.tools = []

        api_kwargs = agent._build_api_kwargs([
            {"role": "user", "content": "hello"}
        ])

        assert api_kwargs["reasoning_effort"] == "high"
