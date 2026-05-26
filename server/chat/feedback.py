from fastapi import Body
from configs import logger, log_verbose
from server.utils import BaseResponse
from server.db.repository import feedback_message_to_db

def chat_feedback(message_id: str = Body("", max_length=32, description="聊天记录id"),
            score: int = Body(0, max=100, description="用户评分，满分100，越大表示评价越高"),
            reason: str = Body("", description="用户评分理由，比如不符合事实等"),
            record_id: int = Body(None, description="关联的诊断记录ID"),
            evolution_case_id: int = Body(None, description="关联的自进化案例ID"),
            accepted: bool = Body(None, description="诊断建议是否被采纳")
            ):
    try:
        if message_id:
            feedback_message_to_db(message_id, score, reason)
    except Exception as e:
        msg = f"反馈聊天记录出错： {e}"
        logger.error(f'{e.__class__.__name__}: {msg}',
                     exc_info=e if log_verbose else None)
        return BaseResponse(code=500, msg=msg)

    try:
        from server.evolution.collector import capture_user_feedback
        capture_user_feedback(
            message_id=message_id or None,
            score=score,
            reason=reason,
            record_id=record_id,
            evolution_case_id=evolution_case_id,
            accepted=accepted,
            raw_feedback={
                "message_id": message_id,
                "score": score,
                "reason": reason,
                "record_id": record_id,
                "evolution_case_id": evolution_case_id,
                "accepted": accepted,
            },
        )
    except Exception as evolution_error:
        logger.warning(f"自进化反馈采集失败，不影响原反馈流程: {evolution_error}")

    return BaseResponse(code=200, msg=f"已反馈聊天记录 {message_id}")
