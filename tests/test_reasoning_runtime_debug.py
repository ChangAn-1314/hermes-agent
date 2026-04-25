import logging

import run_agent
from run_agent import AIAgent
from hermes_constants import parse_reasoning_effort


def test_build_api_kwargs_custom_chat_completions_includes_reasoning_effort_high():
    agent = AIAgent(
        model='gpt-5.4',
        provider='custom',
        api_mode='chat_completions',
        base_url='https://xcode.best/v1',
        api_key='dummy',
        reasoning_config=parse_reasoning_effort('high'),
        enabled_toolsets=[],
        quiet_mode=True,
    )

    kwargs = agent._build_api_kwargs([{'role': 'user', 'content': 'hi'}])

    assert kwargs['reasoning_effort'] == 'high'


def test_build_api_kwargs_logs_runtime_debug_snapshot_for_custom_reasoning(caplog):
    agent = AIAgent(
        model='gpt-5.4',
        provider='custom',
        api_mode='chat_completions',
        base_url='https://xcode.best/v1',
        api_key='dummy',
        reasoning_config=parse_reasoning_effort('high'),
        enabled_toolsets=[],
        quiet_mode=True,
    )

    with caplog.at_level(logging.DEBUG, logger=run_agent.logger.name):
        agent._build_api_kwargs([{'role': 'user', 'content': 'hi'}])

    assert any('Runtime debug snapshot' in rec.message for rec in caplog.records)
