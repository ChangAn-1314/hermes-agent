"""Tests for structured long message split in stream consumer."""
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
async def test_stream_consumer_splits_structured_long_message_into_multiple_messages():
    adapter = MagicMock()
    adapter.MAX_MESSAGE_LENGTH = 4096
    adapter._split_structured_long_messages = True
    adapter._structured_long_message_max_lines = 4
    adapter._delay_jitter = 0.0
    adapter.send = AsyncMock(side_effect=[
        SimpleNamespace(success=True, message_id="msg_1"),
        SimpleNamespace(success=True, message_id="msg_2"),
    ])
    adapter.edit_message = AsyncMock(return_value=SimpleNamespace(success=True))

    consumer = GatewayStreamConsumer(adapter, "chat_123", StreamConsumerConfig(edit_interval=0.01, buffer_threshold=1, cursor=" ▉"))
    consumer.on_delta("## 一\n第一段\n\n## 二\n第二段")
    consumer.finish()

    await consumer.run()

    assert adapter.send.call_count == 2


@pytest.mark.asyncio
async def test_stream_consumer_splits_structured_long_message_after_initial_stream_edit():
    adapter = MagicMock()
    adapter.MAX_MESSAGE_LENGTH = 4096
    adapter._split_structured_long_messages = True
    adapter._structured_long_message_max_lines = 4
    adapter._delay_jitter = 0.0
    adapter.send = AsyncMock(side_effect=[
        SimpleNamespace(success=True, message_id="msg_1"),
        SimpleNamespace(success=True, message_id="msg_2"),
    ])
    adapter.edit_message = AsyncMock(return_value=SimpleNamespace(success=True))

    consumer = GatewayStreamConsumer(adapter, "chat_123", StreamConsumerConfig(edit_interval=10.0, buffer_threshold=999, cursor=" ▉"))
    consumer._message_id = "msg_existing"
    consumer._last_sent_text = "## 一\n第一段 ▉"
    consumer._already_sent = True
    consumer._accumulated = "## 一\n第一段\n\n## 二\n第二段"
    consumer.finish()

    await consumer.run()

    assert adapter.send.call_count == 1
    adapter.edit_message.assert_awaited()
