"""Tests for Telegram chatty split integration in GatewayStreamConsumer."""
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.stream_consumer import GatewayStreamConsumer, StreamConsumerConfig


def _ensure_telegram_mock():
    if "telegram" in sys.modules and hasattr(sys.modules["telegram"], "__file__"):
        return
    mod = MagicMock()
    mod.ext.ContextTypes.DEFAULT_TYPE = type(None)
    mod.constants.ParseMode.MARKDOWN_V2 = "MarkdownV2"
    mod.constants.ChatType.GROUP = "group"
    mod.constants.ChatType.SUPERGROUP = "supergroup"
    mod.constants.ChatType.CHANNEL = "channel"
    mod.constants.ChatType.PRIVATE = "private"
    for name in ("telegram", "telegram.ext", "telegram.constants", "telegram.request"):
        sys.modules.setdefault(name, mod)


_ensure_telegram_mock()


@pytest.mark.asyncio
async def test_stream_consumer_sends_short_chat_lines_as_separate_messages():
    adapter = MagicMock()
    adapter.MAX_MESSAGE_LENGTH = 4096
    adapter._split_short_chat_messages = True
    adapter.send = AsyncMock(side_effect=[
        SimpleNamespace(success=True, message_id="msg_1"),
        SimpleNamespace(success=True, message_id="msg_2"),
        SimpleNamespace(success=True, message_id="msg_3"),
    ])
    adapter.edit_message = AsyncMock(return_value=SimpleNamespace(success=True))

    consumer = GatewayStreamConsumer(adapter, "chat_123", StreamConsumerConfig(edit_interval=0.01, buffer_threshold=1, cursor=" ▉"))
    consumer.on_delta("嗯\n刚才那句不对\n我重新来")
    consumer.finish()

    await consumer.run()

    assert adapter.send.call_count == 3
    texts = [call.kwargs["content"] for call in adapter.send.call_args_list]
    assert texts == ["嗯", "刚才那句不对", "我重新来"]
    adapter.edit_message.assert_not_called()


@pytest.mark.asyncio
async def test_stream_consumer_keeps_structured_text_as_single_message():
    adapter = MagicMock()
    adapter.MAX_MESSAGE_LENGTH = 4096
    adapter._split_short_chat_messages = True
    adapter.send = AsyncMock(return_value=SimpleNamespace(success=True, message_id="msg_1"))
    adapter.edit_message = AsyncMock(return_value=SimpleNamespace(success=True))

    consumer = GatewayStreamConsumer(adapter, "chat_123", StreamConsumerConfig(edit_interval=0.01, buffer_threshold=1, cursor=" ▉"))
    consumer.on_delta("说明：\n这里是详细内容")
    consumer.finish()

    await consumer.run()

    assert adapter.send.call_count == 1
    sent_text = adapter.send.call_args.kwargs["content"]
    assert "说明" in sent_text
