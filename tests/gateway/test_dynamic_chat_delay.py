"""Tests for dynamic chat delay helpers."""
from gateway.platforms.helpers import compute_short_chat_delay, compute_long_chunk_delay


def test_short_chat_delay_grows_with_length():
    assert compute_short_chat_delay("嗯") < compute_short_chat_delay("刚才那句不对")


def test_short_chat_delay_is_capped():
    delay = compute_short_chat_delay("这是一条特别特别长但是仍然按照短聊天泡泡逻辑处理的测试消息" * 3)
    assert delay <= 0.9


def test_long_chunk_delay_grows_with_length():
    assert compute_long_chunk_delay("短一点") < compute_long_chunk_delay("这是一条更长很多很多的分段消息，用来验证长段延时会随着内容增长而增加")


def test_long_chunk_delay_is_capped():
    delay = compute_long_chunk_delay("超长消息" * 500)
    assert delay <= 4.0
