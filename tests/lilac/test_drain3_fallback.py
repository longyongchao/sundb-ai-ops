"""Drain3 兜底解析器测试"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.diagnose.lilac.drain3_fallback import Drain3Fallback


class TestDrain3Fallback:
    """Drain3 测试"""

    def test_parse_produces_template(self):
        fb = Drain3Fallback()
        if not fb.available:
            pytest.skip("drain3 not installed")

        result = fb.parse("Connection from 192.168.1.100 port 5432 accepted")
        assert result is not None
        assert result.source == "drain3"
        assert "<*>" in result.template_str or len(result.tokens) > 0

    def test_repeated_parse_consistent(self):
        fb = Drain3Fallback()
        if not fb.available:
            pytest.skip("drain3 not installed")

        for _ in range(5):
            fb.parse("User alice logged in from 192.168.1.100")
        for _ in range(5):
            fb.parse("User bob logged in from 10.0.0.5")

        r1 = fb.parse("User charlie logged in from 172.16.0.1")
        r2 = fb.parse("User dave logged in from 8.8.8.8")
        if r1 and r2:
            assert r1.template_id == r2.template_id

    def test_disabled_returns_none(self):
        fb = Drain3Fallback.__new__(Drain3Fallback)
        fb._available = False
        fb._miner = None

        result = fb.parse("Any log message here")
        assert result is None
