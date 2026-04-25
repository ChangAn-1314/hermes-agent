"""Tests for dynamic delay behavior in GatewayStreamConsumer."""
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_short_chat_split_uses_sleep_between_units():
    adapter = MagicMock()
    adapter.MAX_MESSAGE_LENGTH = 4096
    adapter._split_short_chat_messages = True
    adapter._delay_jitter = 0.0
    adapter.send = AsyncMock(side_effect=[
        SimpleNamespace(success=True, message_id="msg_1"),
        SimpleNamespace(success=True, message_id="msg_2"),
        SimpleNamespace(success=True, message_id="msg_3"),
    ])
    adapter.edit_message = AsyncMock(return_value=SimpleNamespace(success=True))

    consumer = GatewayStreamConsumer(adapter, "chat_123", StreamConsumerConfig(edit_interval=0.01, buffer_threshold=1, cursor=" ▉"))
    consumer.on_delta("嗯\n刚才那句不对\n我重新来")
    consumer.finish()

    with patch("gateway.stream_consumer.asyncio.sleep", new=AsyncMock()) as sleep_mock:
        await consumer.run()

    assert sleep_mock.await_count >= 2


@pytest.mark.asyncio
async def test_long_chunk_fallback_uses_sleep_between_chunks():
    adapter = MagicMock()
    adapter.MAX_MESSAGE_LENGTH = 30
    adapter._long_chunk_delay_base = 0.9
    adapter._long_chunk_delay_per_char = 0.008
    adapter._long_chunk_delay_max = 4.0
    adapter._delay_jitter = 0.0
    adapter.send = AsyncMock(return_value=SimpleNamespace(success=True, message_id="msg_1"))

    consumer = GatewayStreamConsumer(adapter, "chat_123", StreamConsumerConfig())
    consumer._fallback_prefix = ""
    consumer._last_sent_text = ""
    long_text = "这是第一段。" * 20

    with patch("gateway.stream_consumer.asyncio.sleep", new=AsyncMock()) as sleep_mock, \
         patch.object(consumer, "_split_text_chunks", return_value=["第一段很长的内容", "第二段继续发送"]):
        await consumer._send_fallback_final(long_text)

    assert sleep_mock.await_count >= 1
