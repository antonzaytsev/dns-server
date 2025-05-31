"""Basic import tests to verify all dependencies are installed correctly."""

import pytest


def test_core_dns_imports():
    """Test that core DNS and networking libraries can be imported."""
    import asyncio  # noqa: F401

    import aiofiles  # noqa: F401
    import aiohttp  # noqa: F401
    import dns.message
    import dns.query
    import uvloop  # noqa: F401
    import websockets  # noqa: F401
    import yaml  # noqa: F401

    # Basic functionality test for dnspython
    assert hasattr(dns.message, "Message")
    assert hasattr(dns.query, "udp")


def test_monitoring_imports():
    """Test that monitoring and logging libraries can be imported."""
    import prometheus_client
    import structlog

    # Basic functionality test
    assert hasattr(prometheus_client, "Counter")
    assert hasattr(structlog, "get_logger")


def test_dev_tool_imports():
    """Test that development tools can be imported."""
    import click

    # Basic functionality test
    assert hasattr(click, "command")


@pytest.mark.asyncio
async def test_asyncio_functionality():
    """Test basic asyncio functionality."""

    async def sample_coroutine():
        return "test"

    result = await sample_coroutine()
    assert result == "test"
