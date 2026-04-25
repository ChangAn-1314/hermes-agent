"""Shared helper classes for gateway platform adapters.

Extracts common patterns that were duplicated across 5-7 adapters:
message deduplication, text batch aggregation, markdown stripping,
and thread participation tracking.
"""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional
import random

if TYPE_CHECKING:
    from gateway.platforms.base import BasePlatformAdapter, MessageEvent

logger = logging.getLogger(__name__)


# ─── Message Deduplication ────────────────────────────────────────────────────


class MessageDeduplicator:
    """TTL-based message deduplication cache.

    Replaces the identical ``_seen_messages`` / ``_is_duplicate()`` pattern
    previously duplicated in discord, slack, dingtalk, wecom, weixin,
    mattermost, and feishu adapters.

    Usage::

        self._dedup = MessageDeduplicator()

        # In message handler:
        if self._dedup.is_duplicate(msg_id):
            return
    """

    def __init__(self, max_size: int = 2000, ttl_seconds: float = 300):
        self._seen: Dict[str, float] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds

    def is_duplicate(self, msg_id: str) -> bool:
        """Return True if *msg_id* was already seen within the TTL window."""
        if not msg_id:
            return False
        now = time.time()
        if msg_id in self._seen:
            if now - self._seen[msg_id] < self._ttl:
                return True
            # Entry has expired — remove it and treat as new
            del self._seen[msg_id]
        self._seen[msg_id] = now
        if len(self._seen) > self._max_size:
            cutoff = now - self._ttl
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
        return False

    def clear(self):
        """Clear all tracked messages."""
        self._seen.clear()


# ─── Text Batch Aggregation ──────────────────────────────────────────────────


class TextBatchAggregator:
    """Aggregates rapid-fire text events into single messages.

    Replaces the ``_enqueue_text_event`` / ``_flush_text_batch`` pattern
    previously duplicated in telegram, discord, matrix, wecom, and feishu.

    Usage::

        self._text_batcher = TextBatchAggregator(
            handler=self._message_handler,
            batch_delay=0.6,
            split_threshold=1900,
        )

        # In message dispatch:
        if msg_type == MessageType.TEXT and self._text_batcher.is_enabled():
            self._text_batcher.enqueue(event, session_key)
            return
    """

    def __init__(
        self,
        handler,
        *,
        batch_delay: float = 0.6,
        split_delay: float = 2.0,
        split_threshold: int = 4000,
    ):
        self._handler = handler
        self._batch_delay = batch_delay
        self._split_delay = split_delay
        self._split_threshold = split_threshold
        self._pending: Dict[str, "MessageEvent"] = {}
        self._pending_tasks: Dict[str, asyncio.Task] = {}

    def is_enabled(self) -> bool:
        """Return True if batching is active (delay > 0)."""
        return self._batch_delay > 0

    def enqueue(self, event: "MessageEvent", key: str) -> None:
        """Add *event* to the pending batch for *key*."""
        chunk_len = len(event.text or "")
        existing = self._pending.get(key)
        if not existing:
            event._last_chunk_len = chunk_len  # type: ignore[attr-defined]
            self._pending[key] = event
        else:
            existing.text = f"{existing.text}\n{event.text}"
            existing._last_chunk_len = chunk_len  # type: ignore[attr-defined]

        # Cancel prior flush timer, start a new one
        prior = self._pending_tasks.get(key)
        if prior and not prior.done():
            prior.cancel()
        self._pending_tasks[key] = asyncio.create_task(self._flush(key))

    async def _flush(self, key: str) -> None:
        """Wait then dispatch the batched event for *key*."""
        current_task = self._pending_tasks.get(key)
        pending = self._pending.get(key)
        last_len = getattr(pending, "_last_chunk_len", 0) if pending else 0

        # Use longer delay when the last chunk looks like a split message
        delay = self._split_delay if last_len >= self._split_threshold else self._batch_delay
        await asyncio.sleep(delay)

        event = self._pending.pop(key, None)
        if event:
            try:
                await self._handler(event)
            except Exception:
                logger.exception("[TextBatchAggregator] Error dispatching batched event for %s", key)

        if self._pending_tasks.get(key) is current_task:
            self._pending_tasks.pop(key, None)

    def cancel_all(self) -> None:
        """Cancel all pending flush tasks."""
        for task in self._pending_tasks.values():
            if not task.done():
                task.cancel()
        self._pending_tasks.clear()
        self._pending.clear()


# ─── Markdown Stripping ──────────────────────────────────────────────────────

# Pre-compiled regexes for performance
_RE_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_RE_ITALIC_STAR = re.compile(r"\*(.+?)\*", re.DOTALL)
_RE_BOLD_UNDER = re.compile(r"__(.+?)__", re.DOTALL)
_RE_ITALIC_UNDER = re.compile(r"_(.+?)_", re.DOTALL)
_RE_CODE_BLOCK = re.compile(r"```[a-zA-Z0-9_+-]*\n?")
_RE_INLINE_CODE = re.compile(r"`(.+?)`")
_RE_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_RE_LINK = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
_RE_MULTI_NEWLINE = re.compile(r"\n{3,}")


def strip_markdown(text: str) -> str:
    """Strip markdown formatting for plain-text platforms (SMS, iMessage, etc.).

    Replaces the identical ``_strip_markdown()`` functions previously
    duplicated in sms.py, bluebubbles.py, and feishu.py.
    """
    text = _RE_BOLD.sub(r"\1", text)
    text = _RE_ITALIC_STAR.sub(r"\1", text)
    text = _RE_BOLD_UNDER.sub(r"\1", text)
    text = _RE_ITALIC_UNDER.sub(r"\1", text)
    text = _RE_CODE_BLOCK.sub("", text)
    text = _RE_INLINE_CODE.sub(r"\1", text)
    text = _RE_HEADING.sub("", text)
    text = _RE_LINK.sub(r"\1", text)
    text = _RE_MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


# ─── Thread Participation Tracking ───────────────────────────────────────────


class ThreadParticipationTracker:
    """Persistent tracking of threads the bot has participated in.

    Replaces the identical ``_load/_save_participated_threads`` +
    ``_mark_thread_participated`` pattern previously duplicated in
    discord.py and matrix.py.

    Usage::

        self._threads = ThreadParticipationTracker("discord")

        # Check membership:
        if thread_id in self._threads:
            ...

        # Mark participation:
        self._threads.mark(thread_id)
    """

    _MAX_TRACKED = 500

    def __init__(self, platform_name: str, max_tracked: int = 500):
        self._platform = platform_name
        self._max_tracked = max_tracked
        self._threads: set = self._load()

    def _state_path(self) -> Path:
        from hermes_constants import get_hermes_home
        return get_hermes_home() / f"{self._platform}_threads.json"

    def _load(self) -> set:
        path = self._state_path()
        if path.exists():
            try:
                return set(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                pass
        return set()

    def _save(self) -> None:
        path = self._state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        thread_list = list(self._threads)
        if len(thread_list) > self._max_tracked:
            thread_list = thread_list[-self._max_tracked:]
            self._threads = set(thread_list)
        path.write_text(json.dumps(thread_list), encoding="utf-8")

    def mark(self, thread_id: str) -> None:
        """Mark *thread_id* as participated and persist."""
        if thread_id not in self._threads:
            self._threads.add(thread_id)
            self._save()

    def __contains__(self, thread_id: str) -> bool:
        return thread_id in self._threads

    def clear(self) -> None:
        self._threads.clear()


# ─── Phone Number Redaction ──────────────────────────────────────────────────


def redact_phone(phone: str) -> str:
    """Redact a phone number for logging, preserving country code and last 4.

    Replaces the identical ``_redact_phone()`` functions in signal.py,
    sms.py, and bluebubbles.py.
    """
    if not phone:
        return "<none>"
    if len(phone) <= 8:
        return phone[:2] + "****" + phone[-2:] if len(phone) > 4 else "****"
    return phone[:4] + "****" + phone[-4:]


# ─── Short Chat Bubble Splitting ─────────────────────────────────────────────

_TABLE_RULE_RE = re.compile(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$")


def _looks_like_chatty_line(text: str, *, max_len: int = 48) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped) > max_len:
        return False
    if text.startswith((" ", "\t")):
        return False
    if stripped.startswith((">", "-", "*", "【", "#", "```", "|")):
        return False
    if re.match(r"^\d+\.\s", stripped):
        return False
    return True


def _looks_like_heading_line(text: str, *, max_len: int = 24) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return len(stripped) <= max_len and stripped.endswith((":", "："))


def should_split_short_chat_block(text: str) -> bool:
    if not text or "```" in text:
        return False
    lines = [line for line in text.splitlines() if line.strip()]
    if not 2 <= len(lines) <= 6:
        return False
    if _looks_like_heading_line(lines[0]):
        return False
    if any(_TABLE_RULE_RE.match(line.strip()) for line in lines):
        return False
    return all(_looks_like_chatty_line(line) for line in lines)


def split_short_chat_block(text: str) -> List[str]:
    if not should_split_short_chat_block(text):
        return [text]
    return [line.strip() for line in text.splitlines() if line.strip()]


def compute_short_chat_delay(text: str, *, base: float = 0.18, per_char: float = 0.025, max_delay: float = 0.9, jitter: float = 0.0) -> float:
    visible_len = len((text or '').strip())
    delay = base + visible_len * per_char
    if jitter > 0:
        delay += random.uniform(-jitter, jitter)
    return max(base, min(delay, max_delay))


def compute_long_chunk_delay(text: str, *, base: float = 0.9, per_char: float = 0.008, max_delay: float = 4.0, jitter: float = 0.0) -> float:
    visible_len = len((text or '').strip())
    delay = base + visible_len * per_char
    if jitter > 0:
        delay += random.uniform(-jitter, jitter)
    return max(base, min(delay, max_delay))


def split_structured_long_message(text: str, *, max_lines: int = 6) -> List[str]:
    if not text or '\n' not in text:
        return [text]

    heading_re = re.compile(r'^(?:#{1,6}\s+.+|(?:第[一二三四五六七八九十百0-9]+[章节部分篇])|(?:[一二三四五六七八九十]+[、.．])|(?:\d+[、.．])|(?:[A-Za-z][、.．:：]))')
    known_heading_lines = {"结论", "总结", "说明", "补充说明", "注意", "备注", "原因", "现状", "状态", "下一步", "我做了什么", "这次新增了什么", "我刚做的事", "我核到的真实情况"}

    def is_heading_line(line: str) -> bool:
        first = (line or '').strip()
        if not first:
            return False
        if heading_re.match(first):
            return True
        if first in known_heading_lines:
            return True
        return False

    def is_heading_block(block: str) -> bool:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            return False
        return is_heading_line(lines[0])

    normalized = text.replace('\r\n', '\n')
    raw_blocks = [block.strip() for block in re.split(r'\n\s*\n', normalized) if block.strip()]

    def coalesce_blocks(blocks: List[str], *, preserve_blank_separated_blocks: bool = False) -> List[str]:
        sections: List[str] = []
        current: List[str] = []
        current_lines = 0

        for block in blocks:
            block_lines = block.count('\n') + 1
            heading_block = is_heading_block(block)
            should_flush = False
            if current:
                should_flush = heading_block or current_lines + block_lines > max_lines
                if preserve_blank_separated_blocks and not heading_block:
                    should_flush = True
            if should_flush:
                sections.append('\n\n'.join(current).strip())
                current = [block]
                current_lines = block_lines
            else:
                current.append(block)
                current_lines += block_lines

        if current:
            sections.append('\n\n'.join(current).strip())
        return sections

    if len(raw_blocks) > 1:
        sections = coalesce_blocks(raw_blocks, preserve_blank_separated_blocks=True)
        return sections if len(sections) > 1 else [text]

    logical_blocks: List[str] = []
    current_lines: List[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            if current_lines:
                logical_blocks.append('\n'.join(current_lines).strip())
                current_lines = []
            continue
        if current_lines and is_heading_line(line):
            logical_blocks.append('\n'.join(current_lines).strip())
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        logical_blocks.append('\n'.join(current_lines).strip())

    if len(logical_blocks) <= 1:
        return [text]

    sections = coalesce_blocks(logical_blocks)
    return sections if len(sections) > 1 else [text]
