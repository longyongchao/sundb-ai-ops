"""LILAC Token 级相似度计算"""

from typing import List

PLACEHOLDER = "<*>"


def token_similarity(log_tokens: List[str], template_tokens: List[str]) -> float:
    """计算日志 tokens 与模板 tokens 的位置匹配相似度

    规则：
    - 长度不同返回 0
    - 模板中的 <*> 匹配任何 token
    - 其余位置需严格相等
    - 返回匹配比例 [0.0, 1.0]
    """
    if len(log_tokens) != len(template_tokens):
        return 0.0
    if not log_tokens:
        return 0.0

    matches = 0
    for lt, tt in zip(log_tokens, template_tokens):
        if tt == PLACEHOLDER or lt == tt:
            matches += 1

    return matches / len(log_tokens)
