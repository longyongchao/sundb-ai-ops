"""LILAC Token 级相似度计算"""

from typing import List

PLACEHOLDER = "<*>"


def _token_matches(log_token: str, template_token: str) -> bool:
    """判断单个日志 token 是否匹配模板 token

    支持三种情况：
    1. 模板 token 整体是 <*> → 匹配任何日志 token
    2. 模板 token 内嵌 <*>（如 [SESSION:<*>][DDL）→ 静态部分必须对齐
    3. 无 <*> → 严格相等
    """
    if template_token == PLACEHOLDER:
        return True
    if PLACEHOLDER not in template_token:
        return log_token == template_token

    parts = template_token.split(PLACEHOLDER)
    pos = 0
    for i, part in enumerate(parts):
        if not part:
            continue
        idx = log_token.find(part, pos)
        if idx < 0:
            return False
        if i == 0 and idx != 0:
            return False
        pos = idx + len(part)
    if parts[-1] and not log_token.endswith(parts[-1]):
        return False
    return True


def token_similarity(log_tokens: List[str], template_tokens: List[str]) -> float:
    """计算日志 tokens 与模板 tokens 的位置匹配相似度

    规则：
    - 长度不同返回 0
    - 模板中的 <*> 或包含 <*> 的 token 按通配符匹配
    - 其余位置需严格相等
    - 返回匹配比例 [0.0, 1.0]
    """
    if len(log_tokens) != len(template_tokens):
        return 0.0
    if not log_tokens:
        return 0.0

    matches = 0
    for lt, tt in zip(log_tokens, template_tokens):
        if _token_matches(lt, tt):
            matches += 1

    return matches / len(log_tokens)
