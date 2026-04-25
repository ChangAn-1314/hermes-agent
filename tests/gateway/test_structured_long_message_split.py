"""Tests for structured long message splitting helpers."""
from gateway.platforms.helpers import split_structured_long_message


def test_split_structured_long_message_splits_sections():
    text = "## 一\n第一段\n\n## 二\n第二段\n\n## 三\n第三段"
    chunks = split_structured_long_message(text, max_lines=4)
    assert len(chunks) >= 2


def test_split_structured_long_message_splits_named_chinese_sections():
    text = "这次新增了什么\n\n1 helpers.py 新增结构化长消息切分函数\n文件：\n- a.py\n\n2 stream_consumer.py 接入结构化长消息分段\n文件：\n- b.py"
    chunks = split_structured_long_message(text, max_lines=6)
    assert len(chunks) >= 2
    assert chunks[0].startswith("这次新增了什么")


def test_split_structured_long_message_splits_line_headings_without_blank_lines():
    text = "这次新增了什么\n1. helpers.py 新增结构化长消息切分函数\n文件：\n- a.py\n2. stream_consumer.py 接入结构化长消息分段\n文件：\n- b.py\n结论\n现在应该更容易拆成多段"
    chunks = split_structured_long_message(text, max_lines=6)
    assert len(chunks) >= 2
    assert chunks[0].startswith("这次新增了什么")
    assert any("2. stream_consumer.py" in chunk for chunk in chunks)


def test_split_structured_long_message_splits_on_blank_lines_without_headings():
    text = "第一段先说明背景\n继续补充一行\n\n第二段切到实现细节\n继续补充一行\n\n第三段收尾总结"
    chunks = split_structured_long_message(text, max_lines=10)
    assert chunks == [
        "第一段先说明背景\n继续补充一行",
        "第二段切到实现细节\n继续补充一行",
        "第三段收尾总结",
    ]


def test_split_structured_long_message_does_not_split_simple_label_value_block():
    text = "说明：\n这里是详细内容"
    assert split_structured_long_message(text, max_lines=6) == [text]


def test_split_structured_long_message_does_not_split_short_plain_prose_lines():
    text = "已经同步\n明天继续\n辛苦了"
    assert split_structured_long_message(text, max_lines=6) == [text]


def test_split_structured_long_message_keeps_short_text_single():
    text = "简单一句说明"
    assert split_structured_long_message(text, max_lines=4) == [text]
