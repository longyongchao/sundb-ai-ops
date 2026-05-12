"""LILAC LLM 模板提取器：ICL Prompt 构造 + LLM 调用"""

import logging
import re
from typing import Dict, List, Optional

from server.diagnose.lilac.models import LogTemplate

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert at parsing log messages. Your task is to identify \
the static template and dynamic parameters in a log message.

Rules:
1. Replace dynamic parameters with <*>
2. Keep all punctuation, brackets, and structural tokens unchanged
3. Numeric values, IDs, paths, IPs, names, timestamps are typically parameters
4. Verbs, prepositions, descriptive words, and error codes patterns are typically template
5. Output ONLY a JSON object: {"template": "...", "variables": [...]}
6. Do NOT add any explanation"""


def build_prompt(
    demonstrations: List[Dict[str, str]], query_log: str
) -> str:
    """构造 ICL few-shot prompt"""
    lines = [SYSTEM_PROMPT, "", "Examples:", ""]

    for demo in demonstrations:
        lines.append(f"Input: {demo['raw_log']}")
        lines.append(f'Output: {{"template": "{demo["template"]}", "variables": []}}')
        lines.append("")

    lines.append(f"Input: {query_log}")
    lines.append("Output:")

    return "\n".join(lines)


class LLMTemplateExtractor:
    """通过 LLM 提取日志模板"""

    def __init__(
        self,
        temperature: float = 0.0,
        timeout: float = 10.0,
    ):
        self._temperature = temperature
        self._timeout = timeout

    def extract(
        self,
        masked_log: str,
        demonstrations: List[Dict[str, str]],
    ) -> Optional[LogTemplate]:
        """调用 LLM 提取模板，失败返回 None"""
        try:
            from server.utils import get_ChatOpenAI

            prompt = build_prompt(demonstrations, masked_log)
            llm = get_ChatOpenAI(temperature=self._temperature)
            response = llm.predict(prompt)

            template_str = self._parse_response(response, masked_log)
            if template_str is None:
                return None

            return LogTemplate.from_template_str(template_str, source="llm")

        except Exception as e:
            logger.warning(f"LLM template extraction failed: {e}")
            return None

    def _parse_response(self, raw_output: str, original_log: str) -> Optional[str]:
        """解析 LLM 输出，提取模板字符串"""
        text = raw_output.strip()

        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        try:
            from server.utils import robust_json_parse
            parsed = robust_json_parse(text)
            if isinstance(parsed, dict) and "template" in parsed:
                template_str = parsed["template"].strip()
                if self._validate_template(template_str, original_log):
                    return template_str
        except Exception:
            pass

        m = re.search(r'"template"\s*:\s*"([^"]+)"', text)
        if m:
            template_str = m.group(1).strip()
            if self._validate_template(template_str, original_log):
                return template_str

        return None

    @staticmethod
    def _validate_template(template_str: str, original_log: str) -> bool:
        """验证模板合法性：模板的静态部分必须出现在原始日志中"""
        if not template_str:
            return False
        static_parts = [p.strip() for p in template_str.split("<*>") if p.strip()]
        if not static_parts:
            return len(template_str.split()) > 0
        return all(part in original_log for part in static_parts)
