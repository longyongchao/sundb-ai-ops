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

| Category | Examples | Template |
|----------|----------|----------|
| Timestamps | `2026-05-13 21:07:40,857`, `Wed May 13 21:07:42 2026`, `1715612862.123`, `15:49:05.591941` | <*> |
| Numeric values | `128`, `3.1415`, `1.04e-3`, `0x7f3a`, `95.2%` | <*> |
| IP:port / CIDR | `192.168.1.1:5432`, `10.0.0.0/24`, `[::1]:443` | <*> |
| Identifiers | UUIDs, session/request/transaction IDs, hex hashes, tokens | <*> |
| Hostnames / domains | `db-replica-03.internal`, `node2.cluster.local` | <*> |
| File paths | `/var/log/app.log`, `C:\\Users\\admin\\file.txt` | <*> |
| Usernames / emails | `alice`, `admin@example.com` | <*> |
| Process/thread IDs | PID `12345`, TID `0x7f3a`, `Thread-4` | <*> |
| Durations / sizes | `350ms`, `1.2GB`, `45s`, `128KB` | <*> |
| URLs | `http://api.internal/v1/health` | <*> |
| Version strings (when they embed build numbers) | `v3.2.1-build.4521` | <*> |
| SQL/query fragments | Embedded queries or table-specific clauses | <*> |
| Container/pod names | `api-server-6d8f7-xk2p9` | <*> |

## What to KEEP (static structure)

- Log level keywords: INFO, ERROR, WARN, DEBUG, FATAL, TRACE
- Action/event words: started, stopped, failed, connected, timeout, retry, completed
- Module/class/function names that identify the log statement
- Source file names (replace line numbers): `[utils.py:<*>]`
- Error type names: NullPointerException, TimeoutError, IOError
- Structural punctuation: brackets, colons, equals signs, commas as separators
- Fixed enum values when they name the event: `status=RUNNING` → keep if RUNNING is the event being logged; replace if it varies per instance

## Critical rules

1. **Atomicity**: A single semantic value = ONE <*>. Never split at internal dots, colons, or hyphens.
   - `1.0418123006820679` → <*> (NOT `1.<*>`)
   - `2026-05-13` → <*> (NOT `<*>-05-13`)
   - `192.168.1.1:5432` → <*> (NOT `<*>:<*>`)
2. **Greedy on timestamps**: If a log starts with any timestamp pattern (ISO, ctime, epoch, custom), replace the ENTIRE timestamp including milliseconds as one <*>.
3. **Adjacency without separator**: `2026[1,8]` = two values glued together → `<*>[<*>]`. Use surrounding syntax (brackets, delimiters) to determine boundaries.
4. **Repeated parameters**: Each occurrence gets its own <*>. `from 10.0.0.1 to 10.0.0.2` → `from <*> to <*>`
5. **When uncertain**: If a token could be static or dynamic, check — does it look like it would change across different executions of the same code path? If yes → <*>.

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
            from server.utils import get_ChatOpenAI, MY_MODEL_NAME

            prompt = build_prompt(demonstrations, masked_log)
            llm = get_ChatOpenAI(
                model_name=MY_MODEL_NAME,
                temperature=self._temperature,
                streaming=False,
            )
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
