import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from gateway.run import GatewayRunner


def _make_event(text="hello"):
    source = SessionSource(
        platform=Platform.TELEGRAM,
        user_id="u1",
        user_name="tester",
        chat_id="c1",
        chat_name="chat",
        chat_type="dm",
        thread_id=None,
    )
    return MessageEvent(text=text, source=source, message_id="m1")


def _make_runner(history=None, agent_result=None):
    runner = object.__new__(GatewayRunner)
    runner.config = MagicMock()
    runner.adapters = {Platform.TELEGRAM: MagicMock()}
    runner.adapters[Platform.TELEGRAM].stop_typing = AsyncMock()
    runner.hooks = SimpleNamespace(emit=AsyncMock())
    runner.session_store = MagicMock()
    runner.session_store.get_or_create_session.return_value = SimpleNamespace(
        session_id="sess-1",
        session_key="platform:chat:user",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-02T00:00:00",
        was_auto_reset=False,
        auto_reset_reason=None,
        reset_had_activity=False,
        last_prompt_tokens=0,
    )
    runner.session_store.load_transcript.return_value = history or [
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "old reply"},
    ]
    runner.session_store.append_to_transcript = MagicMock()
    runner.session_store.update_session = MagicMock()
    runner.session_store.has_any_sessions = MagicMock(return_value=True)
    runner._set_session_env = MagicMock(return_value={})
    runner._clear_session_env = MagicMock()
    runner._prepare_inbound_message_text = AsyncMock(return_value="hello")
    runner._run_agent = AsyncMock(return_value=agent_result or {})
    runner._should_send_voice_reply = MagicMock(return_value=False)
    runner._send_voice_reply = AsyncMock()
    runner._deliver_media_from_response = AsyncMock()
    runner._clear_restart_failure_count = MagicMock()
    runner._show_reasoning = False
    runner._session_db = None
    return runner


@pytest.mark.asyncio
async def test_handle_message_with_agent_does_not_skip_final_text_when_only_already_sent():
    """Commentary/partial stream should not suppress the final normal reply.

    Regression for the case where the stream consumer emitted some interim text,
    setting already_sent=True, but never marked final_response_sent. The gateway
    must still return the final assistant reply so the normal send path delivers it.
    """
    runner = _make_runner(agent_result={
        "final_response": "final answer",
        "messages": [{"role": "assistant", "content": "final answer"}],
        "already_sent": True,
        "final_response_sent": False,
        "failed": False,
        "history_offset": 2,
        "api_calls": 1,
        "tools": [],
        "last_prompt_tokens": 0,
    })
    event = _make_event()

    with patch("gateway.run.build_session_context", return_value={}), patch(
        "gateway.run.build_session_context_prompt", return_value=""
    ):
        result = await runner._handle_message_with_agent(event, event.source, "quick-key")

    assert result == "final answer"
    runner._deliver_media_from_response.assert_not_called()


@pytest.mark.asyncio
async def test_handle_message_with_agent_skips_normal_send_only_when_final_response_was_streamed():
    """When the final reply really was streamed, the normal send path should skip."""
    runner = _make_runner(agent_result={
        "final_response": "final answer\nMEDIA:/tmp/file.txt",
        "messages": [{"role": "assistant", "content": "final answer"}],
        "already_sent": True,
        "final_response_sent": True,
        "failed": False,
        "history_offset": 2,
        "api_calls": 1,
        "tools": [],
        "last_prompt_tokens": 0,
    })
    event = _make_event()

    with patch("gateway.run.build_session_context", return_value={}), patch(
        "gateway.run.build_session_context_prompt", return_value=""
    ):
        result = await runner._handle_message_with_agent(event, event.source, "quick-key")

    assert result is None
    runner._deliver_media_from_response.assert_awaited_once()
