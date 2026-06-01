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


def token_similarity_fuzzy(
    log_tokens: List[str],
    template_tokens: List[str],
    penalty: float = 0.95,
) -> float:
    """模糊相似度：允许 ±1 token 差异

    当长度差 1 时，在较长序列中尝试每个 skip 位置，
    对齐后计算匹配度，乘以 penalty 惩罚因子。
    精确匹配时直接委托 token_similarity()。
    """
    n_log = len(log_tokens)
    n_tpl = len(template_tokens)

    if n_log == n_tpl:
        return token_similarity(log_tokens, template_tokens)

    if abs(n_log - n_tpl) != 1:
        return 0.0

    if not log_tokens or not template_tokens:
        return 0.0

    if n_log > n_tpl:
        longer, shorter = log_tokens, template_tokens
        log_is_longer = True
    else:
        longer, shorter = template_tokens, log_tokens
        log_is_longer = False

    n_longer = len(longer)
    n_shorter = len(shorter)
    best_score = 0.0

    for skip in range(n_longer):
        matches = 0
        j = 0
        for i in range(n_longer):
            if i == skip:
                continue
            if log_is_longer:
                if _token_matches(longer[i], shorter[j]):
                    matches += 1
            else:
                if _token_matches(shorter[j], longer[i]):
                    matches += 1
            j += 1

        score = matches / n_shorter
        if score > best_score:
            best_score = score

    return best_score * penalty
