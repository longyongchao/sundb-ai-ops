"""LILAC LLM 模板提取器：ICL Prompt 构造 + LLM 调用"""

import logging
import re
from typing import Dict, List, Optional

from server.diagnose.lilac.models import LogTemplate

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a log template extractor. Given a raw log message, produce its structural template by replacing every runtime-variable token with the placeholder <*>.

## Goal
Identify the STATIC SKELETON of the log — the part that is identical across all instances of the same log statement in source code — and replace everything else with <*>.

## What to replace (each becomes exactly ONE <*>)

| Category | Examples |
|----------|----------|
| Timestamps | `2026-05-13 21:07:40,857`, `1715612862.123` |
| Numeric values | `128`, `3.1415`, `0x7f3a`, `95.2%` |
| IP:port / CIDR | `192.168.1.1:5432`, `10.0.0.0/24` |
| Identifiers | UUIDs, session/request/transaction IDs, hex hashes |
| Log-domain IDs | `blk_38865049064139660`, `application_1445144423722_0020` |
| Hostnames / domains | `db-replica-03.internal` |
| File paths | `/var/log/app.log` |
| Process/thread IDs | PID `12345`, TID `0x7f3a` |
| Durations / sizes | `350ms`, `1.2GB`, `45s` |
| HTTP request metrics | `status: 200`, `len: 1893`, `time: 0.247` |

## What to KEEP (static structure)

- Log level keywords: INFO, ERROR, WARN, DEBUG, FATAL, TRACE
- Action/event words: started, stopped, failed, connected, timeout
- Module/class/function names
- Error type names: NullPointerException, TimeoutError
- Structural punctuation: brackets, colons, equals signs

## Critical rules

1. **Atomicity**: A single semantic value = ONE <*>. Never split at internal dots or colons.
2. **Greedy on timestamps**: Replace the ENTIRE timestamp as one <*>.
3. **Repeated parameters**: Each occurrence gets its own <*>.
4. **When uncertain**: If a token changes across different executions → <*>.

## Examples

Input: `PacketResponder 1 for block blk_38865049064139660 terminating`
Output: {"template": "PacketResponder <*> for block <*> terminating", "variables": ["1", "blk_38865049064139660"]}

Input: `10.11.10.1 "GET /v2/tenant/servers/detail HTTP/1.1" status: 200 len: 1893 time: 0.2477829`
Output: {"template": "<*> \\"GET <*>\\" status: <*> len: <*> time: <*>", "variables": ["10.11.10.1", "/v2/tenant/servers/detail HTTP/1.1", "200", "1893", "0.2477829"]}

## Output format

Return ONLY a JSON object, no explanation:
{"template": "<the template string>", "variables": ["var1", "var2", ...]}"""


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
