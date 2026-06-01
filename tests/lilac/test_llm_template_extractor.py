"""LLM 模板提取器单元测试"""

import os
import sys
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server.diagnose.lilac.llm_template_extractor import (
    LLMTemplateExtractor,
    build_prompt,
)


class TestPromptBuilding:
    """Prompt 构造测试"""

    def test_prompt_format(self):
        demos = [
            {"raw_log": "User alice logged in", "template": "User <*> logged in"},
            {"raw_log": "File data.txt deleted", "template": "File <*> deleted"},
        ]
        prompt = build_prompt(demos, "Connection from 10.0.0.1 failed")

        assert "Examples:" in prompt
        assert "User alice logged in" in prompt
        assert "User <*> logged in" in prompt
        assert "Connection from 10.0.0.1 failed" in prompt
        assert prompt.strip().endswith("Output:")

    def test_prompt_with_empty_demos(self):
        prompt = build_prompt([], "Test log message")
        assert "Examples:" in prompt
        assert "Test log message" in prompt


class TestResponseParsing:
    """LLM 响应解析测试"""

    def test_valid_json_response(self):
        extractor = LLMTemplateExtractor()
        result = extractor._parse_response(
            '{"template": "Connection from <*> failed", "variables": ["10.0.0.1"]}',
            "Connection from 10.0.0.1 failed",
        )
        assert result == "Connection from <*> failed"

    def test_json_with_markdown_wrapper(self):
        extractor = LLMTemplateExtractor()
        result = extractor._parse_response(
            '```json\n{"template": "Error in <*>", "variables": ["auth"]}\n```',
            "Error in auth",
        )
        assert result == "Error in <*>"

    def test_malformed_but_extractable(self):
        extractor = LLMTemplateExtractor()
        result = extractor._parse_response(
            'The template is: {"template": "User <*> login from <*>"}',
            "User admin login from 192.168.1.1",
        )
        assert result == "User <*> login from <*>"

    def test_empty_response(self):
        extractor = LLMTemplateExtractor()
        result = extractor._parse_response("", "some log")
        assert result is None

    def test_invalid_template_rejected(self):
        extractor = LLMTemplateExtractor()
        result = extractor._parse_response(
            '{"template": "Completely wrong template text"}',
            "User alice logged in from 192.168.1.5",
        )
        assert result is None


class TestExtractWithMockLLM:
    """Mock LLM 端到端测试"""

    @patch("server.utils.get_ChatOpenAI")
    def test_successful_extraction(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.predict.return_value = '{"template": "Connection from <*> port <*> accepted", "variables": ["10.0.0.1", "5432"]}'
        mock_get_llm.return_value = mock_llm

        extractor = LLMTemplateExtractor()
        demos = [{"raw_log": "User bob login", "template": "User <*> login"}]
        result = extractor.extract("Connection from 10.0.0.1 port 5432 accepted", demos)

        assert result is not None
        assert result.template_str == "Connection from <*> port <*> accepted"
        assert result.source == "llm"

    @patch("server.utils.get_ChatOpenAI", side_effect=Exception("LLM unavailable"))
    def test_extraction_returns_none_on_failure(self, mock_get_llm):
        extractor = LLMTemplateExtractor()
        result = extractor.extract("test log", [])
        assert result is None
