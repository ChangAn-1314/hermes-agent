"""Tests for Telegram short chat message splitting.

Covers the opt-in behavior that makes short chat-like multiline replies send
as separate Telegram bubbles, while keeping long/structured output unchanged.
"""
import logging
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import PlatformConfig


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

from gateway.platforms.helpers import split_short_chat_block, should_split_short_chat_block  # noqa: E402
from gateway.platforms.telegram import TelegramAdapter  # noqa: E402


@pytest.fixture()
def adapter_factory():
    def create(split_short_chat_messages: bool = False):
        config = PlatformConfig(
            enabled=True,
            token="test-token",
            extra={"split_short_chat_messages": split_short_chat_messages},
        )
        return TelegramAdapter(config)
    return create


class TestTelegramChattyHelpers:
    def test_should_split_short_chat_block_true_for_short_chat(self):
        text = "嗯\n刚才那句不对\n我重新来"
        assert should_split_short_chat_block(text) is True

    def test_should_not_split_heading_block(self):
        text = "说明：\n这里是详细内容"
        assert should_split_short_chat_block(text) is False

    def test_should_not_split_markdown_list(self):
        text = "- 第一项\n- 第二项\n- 第三项"
        assert should_split_short_chat_block(text) is False

    def test_split_short_chat_block_returns_lines(self):
        text = "嗯\n刚才那句不对\n我重新来"
        assert split_short_chat_block(text) == ["嗯", "刚才那句不对", "我重新来"]

    def test_split_short_chat_block_preserves_unsplittable_text(self):
        text = "说明：\n这里是详细内容"
        assert split_short_chat_block(text) == [text]


class TestTelegramAdapterShortChatSplit:
    @pytest.mark.asyncio
    async def test_send_does_not_split_when_feature_disabled(self, adapter_factory):
        adapter = adapter_factory(split_short_chat_messages=False)
        adapter._bot = MagicMock()
        adapter._bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))

        await adapter.send("12345", "嗯\n刚才那句不对\n我重新来")

        assert adapter._bot.send_message.await_count == 1

    @pytest.mark.asyncio
    async def test_send_splits_short_chat_when_feature_enabled(self, adapter_factory):
        adapter = adapter_factory(split_short_chat_messages=True)
        adapter._bot = MagicMock()
        adapter._bot.send_message = AsyncMock(side_effect=[
            MagicMock(message_id=1),
            MagicMock(message_id=2),
            MagicMock(message_id=3),
        ])

        await adapter.send("12345", "嗯\n刚才那句不对\n我重新来")

        calls = adapter._bot.send_message.await_args_list
        assert len(calls) == 3
        assert calls[0].kwargs["text"] == "嗯"
        assert calls[1].kwargs["text"] == "刚才那句不对"
        assert calls[2].kwargs["text"] == "我重新来"

    @pytest.mark.asyncio
    async def test_send_does_not_split_structured_text_even_when_enabled(self, adapter_factory):
        adapter = adapter_factory(split_short_chat_messages=True)
        adapter._bot = MagicMock()
        adapter._bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))

        content = "说明：\n这里是详细内容"
        await adapter.send("12345", content)

        assert adapter._bot.send_message.await_count == 1
        sent_text = adapter._bot.send_message.await_args.kwargs["text"]
        assert "说明" in sent_text

    @pytest.mark.asyncio
    async def test_send_debug_log_stays_at_debug_level(self, adapter_factory, caplog):
        adapter = adapter_factory(split_short_chat_messages=True)
        adapter._bot = MagicMock()
        adapter._bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))

        with caplog.at_level(logging.WARNING):
            await adapter.send("12345", "嗯\n刚才那句不对\n我重新来")

        assert "telegram.send split_short=" not in caplog.text

    @pytest.mark.asyncio
    async def test_send_debug_log_does_not_include_raw_message_content(self, adapter_factory, caplog):
        adapter = adapter_factory(split_short_chat_messages=True)
        adapter._bot = MagicMock()
        adapter._bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))

        content = "嗯\n刚才那句不对\n我重新来"
        with caplog.at_level(logging.DEBUG):
            await adapter.send("12345", content)

        assert "telegram.send split_short=" in caplog.text
        assert content not in caplog.text
        assert "content_len=" in caplog.text
        assert "base_units_count=" in caplog.text
