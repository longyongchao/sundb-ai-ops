"""Benchmark 工具函数"""

import re
from typing import List, Tuple


def generate_logformat_regex(log_format: str) -> Tuple[List[str], re.Pattern]:
    """将 Loghub log_format 模板转为命名捕获组正则。

    log_format 中的文字部分本身就是正则语法（如 \\[ 表示匹配 [），
    只有 <Field> 占位符被替换为捕获组。
    """
    headers = []
    splitters = re.split(r"(<[^<>]+>)", log_format)
    regex_parts = []

    for item in splitters:
        if item.startswith("<") and item.endswith(">"):
            header = item.strip("<>")
            headers.append(header)
            if header == "Content":
                regex_parts.append(f"(?P<{header}>.*)")
            else:
                regex_parts.append(f"(?P<{header}>.*?)")
        else:
            regex_parts.append(item)

    regex_str = "^" + "".join(regex_parts) + "$"
    return headers, re.compile(regex_str)
