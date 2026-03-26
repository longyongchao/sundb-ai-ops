"""
诊断进度管理模块 - 支持任务隔离、超时机制和优雅取消

任务类型：
- TYPE_A (manual): 用户手动诊断（前端触发），优先级高
- TYPE_B (auto): 自动巡检任务（后台触发），优先级低

设计原则：
1. A/B 类任务独立运行，互不阻塞
2. 同类任务之间互斥，避免资源争抢
3. 超时自动释放，避免死锁
4. 支持优雅取消，不强制杀死进程
5. 统一管理异步任务，支持安全取消
"""

import threading
import time
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Set

_lock = threading.Lock()

# 任务类型常量
TASK_TYPE_MANUAL = "manual"    # A 类：用户手动诊断
TASK_TYPE_AUTO = "auto"        # B 类：自动巡检任务

# 超时配置（秒）
TASK_TIMEOUT_SECONDS = 600     # 10 分钟超时

# ============ 全局异步任务管理 ============
# 存储 asyncio.Task 对象，用于取消正在运行的诊断任务
_running_async_tasks: Dict[str, asyncio.Task] = {}
_tasks_lock = threading.Lock()

def register_async_task(task_id: str, task: asyncio.Task) -> None:
    """
    注册异步任务到全局字典
    
    @param task_id: 任务ID（通常是 diagnosis_id）
    @param task: asyncio.Task 对象
    """
    with _tasks_lock:
        _running_async_tasks[task_id] = task
        print(f"[TASK_MANAGER] 注册异步任务: {task_id}")

def unregister_async_task(task_id: str) -> None:
    """
    从全局字典移除异步任务
    
    @param task_id: 任务ID
    """
    with _tasks_lock:
        if task_id in _running_async_tasks:
            del _running_async_tasks[task_id]
            print(f"[TASK_MANAGER] 移除异步任务: {task_id}")

def get_running_task(task_id: str) -> Optional[asyncio.Task]:
    """
    获取正在运行的任务
    
    @param task_id: 任务ID
    @return: asyncio.Task 对象或 None
    """
    with _tasks_lock:
        return _running_async_tasks.get(task_id)

def get_all_running_tasks() -> Dict[str, asyncio.Task]:
    """
    获取所有正在运行的任务
    
    @return: 任务字典的副本
    """
    with _tasks_lock:
        return _running_async_tasks.copy()

def cancel_all_async_tasks() -> Dict[str, bool]:
    """
    取消所有正在运行的异步任务
    
    同时设置取消标志，实现双轨状态联动
    
    @return: 取消结果字典 {task_id: success}
    """
    results = {}
    with _tasks_lock:
        task_ids = list(_running_async_tasks.keys())
        
        for task_id in task_ids:
            task = _running_async_tasks.get(task_id)
            if task and not task.done():
                try:
                    task.cancel()
                    results[task_id] = True
                    print(f"[TASK_MANAGER] 已取消任务: {task_id}")
                except Exception as e:
                    results[task_id] = False
                    print(f"[TASK_MANAGER] 取消任务失败 {task_id}: {e}")
            else:
                results[task_id] = True  # 任务已完成，视为取消成功
        
        # 清空任务字典
        _running_async_tasks.clear()
        print(f"[TASK_MANAGER] 已清空所有任务，共 {len(task_ids)} 个")
    
    # ========== 新增：同步设置取消标志 ==========
    # 设置所有任务类型的取消标志
    for task_type in [TASK_TYPE_MANUAL, TASK_TYPE_AUTO]:
        if _task_states[task_type].get("is_running", False):
            _task_states[task_type]["cancel_requested"] = True
            print(f"[TASK_MANAGER] 已设置 {task_type} 类型任务的取消标志")
    
    return results

def cancel_tasks_by_type(task_type: str) -> Dict[str, bool]:
    """
    取消指定类型的所有异步任务
    
    同时设置取消标志，实现双轨状态联动
    
    @param task_type: 任务类型 (manual/auto)
    @return: 取消结果字典
    """
    results = {}
    with _tasks_lock:
        tasks_to_cancel = [
            (task_id, task) 
            for task_id, task in _running_async_tasks.items() 
            if task_id.startswith(f"diag_{task_type}_")
        ]
        
        for task_id, task in tasks_to_cancel:
            if task and not task.done():
                try:
                    task.cancel()
                    results[task_id] = True
                    print(f"[TASK_MANAGER] 已取消 {task_type} 类型任务: {task_id}")
                except Exception as e:
                    results[task_id] = False
                    print(f"[TASK_MANAGER] 取消任务失败 {task_id}: {e}")
            
            # 从字典中移除
            if task_id in _running_async_tasks:
                del _running_async_tasks[task_id]
    
    # ========== 新增：同步设置取消标志 ==========
    if _task_states.get(task_type, {}).get("is_running", False):
        _task_states[task_type]["cancel_requested"] = True
        print(f"[TASK_MANAGER] 已设置 {task_type} 类型任务的取消标志")
    
    return results

# 独立的任务状态存储
_task_states = {
    TASK_TYPE_MANUAL: {
        "is_running": False,
        "is_completed": False,
        "current_step": 0,
        "total_steps": 10,
        "steps": [],
        "start_time": None,
        "start_timestamp": None,
        "end_time": None,
        "status": "idle",
        "diagnosis_id": None,
        "source": "manual",
        "cancel_requested": False,  # 优雅取消标志
        "cancel_reason": None
    },
    TASK_TYPE_AUTO: {
        "is_running": False,
        "is_completed": False,
        "current_step": 0,
        "total_steps": 10,
        "steps": [],
        "start_time": None,
        "start_timestamp": None,
        "end_time": None,
        "status": "idle",
        "diagnosis_id": None,
        "source": "auto",
        "cancel_requested": False,
        "cancel_reason": None
    }
}


def _check_and_reset_timeout(task_type: str) -> bool:
    """
    检查任务是否超时，如果超时则自动重置
    
    Returns:
        bool: True 表示任务已超时并被重置，False 表示未超时
    """
    state = _task_states.get(task_type)
    if not state:
        return False
    
    if state.get("is_running") and state.get("start_timestamp"):
        elapsed = time.time() - state["start_timestamp"]
        if elapsed > TASK_TIMEOUT_SECONDS:
            print(f"[TIMEOUT] {task_type} 类型诊断任务超时 ({elapsed:.1f}s > {TASK_TIMEOUT_SECONDS}s)，自动重置")
            _reset_task_state(task_type)
            return True
    return False


def _reset_task_state(task_type: str):
    """重置指定类型的任务状态"""
    global _task_states
    _task_states[task_type] = {
        "is_running": False,
        "is_completed": False,
        "current_step": 0,
        "total_steps": 10,
        "steps": [],
        "start_time": None,
        "start_timestamp": None,
        "end_time": None,
        "status": "idle",
        "diagnosis_id": None,
        "source": task_type,
        "cancel_requested": False,
        "cancel_reason": None
    }


def get_task_type_from_source(source: str) -> str:
    """根据来源判断任务类型"""
    if source in ["auto", "patrol", "scheduler", "anomaly_detector"]:
        return TASK_TYPE_AUTO
    return TASK_TYPE_MANUAL


def is_task_running(task_type: str) -> bool:
    """
    检查指定类型的任务是否正在运行
    
    Args:
        task_type: TASK_TYPE_MANUAL 或 TASK_TYPE_AUTO
        
    Returns:
        bool: True 表示正在运行
    """
    with _lock:
        _check_and_reset_timeout(task_type)
        state = _task_states.get(task_type, {})
        return state.get("is_running", False)


def can_start_task(task_type: str) -> Dict[str, Any]:
    """
    检查是否可以启动新任务
    
    Returns:
        Dict: {
            "can_start": bool,
            "reason": str,
            "blocking_type": Optional[str],
            "can_override": bool  # 是否可以覆盖（自动任务可被手动任务覆盖）
        }
    """
    with _lock:
        _check_and_reset_timeout(task_type)
        
        state = _task_states.get(task_type, {})
        
        if state.get("is_running"):
            return {
                "can_start": False,
                "reason": f"同类任务正在运行中",
                "blocking_type": task_type,
                "diagnosis_id": state.get("diagnosis_id"),
                "can_override": False,
                "elapsed_seconds": time.time() - state["start_timestamp"] if state.get("start_timestamp") else 0
            }
        
        return {
            "can_start": True,
            "reason": "可以启动新任务",
            "blocking_type": None,
            "can_override": False
        }


def check_auto_task_running() -> Dict[str, Any]:
    """
    检查自动巡检任务是否正在运行（用于手动诊断前的检查）
    
    Returns:
        Dict: {
            "auto_running": bool,
            "can_cancel": bool,
            "diagnosis_id": Optional[str],
            "elapsed_seconds": float,
            "estimated_remaining": float
        }
    """
    with _lock:
        _check_and_reset_timeout(TASK_TYPE_AUTO)
        
        auto_state = _task_states.get(TASK_TYPE_AUTO, {})
        is_running = auto_state.get("is_running", False)
        
        if is_running:
            elapsed = time.time() - auto_state["start_timestamp"] if auto_state.get("start_timestamp") else 0
            current_step = auto_state.get("current_step", 0)
            total_steps = auto_state.get("total_steps", 10)
            
            # 估算剩余时间
            if current_step > 0 and elapsed > 0:
                avg_time_per_step = elapsed / current_step
                remaining_steps = total_steps - current_step
                estimated_remaining = avg_time_per_step * remaining_steps
            else:
                estimated_remaining = 60  # 默认估算 60 秒
            
            return {
                "auto_running": True,
                "can_cancel": True,
                "diagnosis_id": auto_state.get("diagnosis_id"),
                "elapsed_seconds": elapsed,
                "estimated_remaining": estimated_remaining,
                "current_step": current_step,
                "total_steps": total_steps
            }
        
        return {
            "auto_running": False,
            "can_cancel": False,
            "diagnosis_id": None,
            "elapsed_seconds": 0,
            "estimated_remaining": 0
        }


def request_cancel_auto_task(reason: str = "user_request") -> Dict[str, Any]:
    """
    请求取消自动巡检任务（优雅取消）
    
    Args:
        reason: 取消原因
        
    Returns:
        Dict: {
            "success": bool,
            "message": str,
            "diagnosis_id": Optional[str]
        }
    """
    with _lock:
        auto_state = _task_states.get(TASK_TYPE_AUTO, {})
        
        if not auto_state.get("is_running"):
            return {
                "success": True,
                "message": "没有正在运行的自动巡检任务",
                "diagnosis_id": None
            }
        
        # 设置取消标志
        auto_state["cancel_requested"] = True
        auto_state["cancel_reason"] = reason
        
        diagnosis_id = auto_state.get("diagnosis_id")
        print(f"[CANCEL] 已请求取消自动巡检任务，ID: {diagnosis_id}，原因: {reason}")
        
        return {
            "success": True,
            "message": "已发送取消请求，任务将在安全点停止",
            "diagnosis_id": diagnosis_id
        }


def check_cancel_requested(task_type: str) -> bool:
    """
    检查是否收到了取消请求（供诊断任务在安全点调用）
    
    Args:
        task_type: 任务类型
        
    Returns:
        bool: True 表示应该取消
    """
    with _lock:
        state = _task_states.get(task_type, {})
        return state.get("cancel_requested", False)


def confirm_task_cancelled(task_type: str) -> bool:
    """
    确认任务已被取消（供诊断任务在退出前调用）
    
    Args:
        task_type: 任务类型
        
    Returns:
        bool: True 表示确认成功
    """
    with _lock:
        state = _task_states.get(task_type, {})
        if state.get("cancel_requested"):
            from server.utils import get_beijing_now_str
            state["is_running"] = False
            state["is_completed"] = False
            state["status"] = "cancelled"
            state["end_time"] = get_beijing_now_str()
            print(f"[CANCELLED] {task_type} 任务已被取消")
            return True
        return False


def set_task_running(task_type: str, is_running: bool, status: str = "running", 
                     diagnosis_id: str = None) -> bool:
    """
    设置任务运行状态
    
    Args:
        task_type: 任务类型
        is_running: 是否正在运行
        status: 状态描述
        diagnosis_id: 诊断任务 ID
        
    Returns:
        bool: True 表示设置成功，False 表示被同类任务阻塞
    """
    global _task_states
    
    with _lock:
        _check_and_reset_timeout(task_type)
        
        state = _task_states.get(task_type)
        if not state:
            return False
        
        if is_running:
            if state.get("is_running"):
                print(f"[WARN] {task_type} 类型任务已在运行，拒绝重复启动")
                return False
            
            from server.utils import get_beijing_now_str
            state["is_running"] = True
            state["is_completed"] = False
            state["current_step"] = 0
            state["total_steps"] = 10
            state["steps"] = []
            state["start_time"] = get_beijing_now_str()
            state["start_timestamp"] = time.time()
            state["end_time"] = None
            state["status"] = status
            state["diagnosis_id"] = diagnosis_id
            state["cancel_requested"] = False  # 重置取消标志
            state["cancel_reason"] = None  # 清除取消原因
            
            print(f"[TASK_START] {task_type} 类型任务开始运行，ID: {diagnosis_id}")
            print(f"[DIAGNOSIS-{task_type}] 开始诊断，ID: {diagnosis_id}")
        else:
            from server.utils import get_beijing_now_str
            state["is_running"] = False
            state["is_completed"] = (status == "completed")
            state["end_time"] = get_beijing_now_str()
            if status == "cancelled":
                state["status"] = "cancelled"
                state["cancel_requested"] = False  # 重置取消标志
            else:
                state["status"] = status
        
        return True


def update_task_progress(task_type: str, step_data: Dict) -> bool:
    """
    更新任务进度 - 带边界校验
    
    Args:
        task_type: 任务类型
        step_data: 步骤数据
        
    Returns:
        bool: True 表示更新成功，False 表示已达到最大步骤限制
    """
    with _lock:
        state = _task_states.get(task_type)
        if not state:
            return False
        
        # ========== 边界校验：防止步骤超过总步骤限制 ==========
        total_steps = state.get("total_steps", 10)
        current_step = len(state.get("steps", []))
        
        if current_step >= total_steps:
            print(f"[WARN-{task_type}] 已达到最大步骤限制 ({total_steps})，忽略后续步骤更新")
            return False
        
        state["steps"].append(step_data)
        state["current_step"] = len(state["steps"])
        print(f"[PROGRESS-{task_type}] 步骤 {state['current_step']}/{total_steps}")
        return True


def get_task_progress(task_type: str) -> Dict:
    """获取指定类型任务的进度"""
    with _lock:
        _check_and_reset_timeout(task_type)
        state = _task_states.get(task_type, {})
        return state.copy() if isinstance(state, dict) else {}


def get_all_task_progress() -> Dict[str, Dict]:
    """获取所有任务的进度状态"""
    with _lock:
        result = {}
        for task_type in [TASK_TYPE_MANUAL, TASK_TYPE_AUTO]:
            _check_and_reset_timeout(task_type)
            state = _task_states.get(task_type, {})
            result[task_type] = state.copy() if isinstance(state, dict) else {}
        return result


def reset_task_progress(task_type: str = None):
    """
    重置任务进度
    
    Args:
        task_type: 指定类型则只重置该类型，None 则重置所有
    """
    global _task_states
    
    with _lock:
        if task_type:
            _reset_task_state(task_type)
            print(f"[DIAGNOSIS-{task_type}] 进度已重置")
        else:
            for t in [TASK_TYPE_MANUAL, TASK_TYPE_AUTO]:
                _reset_task_state(t)
            print("[DIAGNOSIS] 所有任务进度已重置")


# ============ 兼容旧 API ============

diagnosis_progress = _task_states[TASK_TYPE_MANUAL]

# 当前运行中的任务类型（用于兼容旧 API）
_current_task_type = TASK_TYPE_MANUAL

def set_current_task_type(task_type: str):
    """设置当前任务类型（用于兼容旧 API）"""
    global _current_task_type
    _current_task_type = task_type

def get_current_task_type() -> str:
    """获取当前任务类型"""
    return _current_task_type

def update_diagnosis_progress(step_data, task_type: str = None):
    """兼容旧 API - 更新诊断进度"""
    actual_type = task_type or _current_task_type
    return update_task_progress(actual_type, step_data)


def set_diagnosis_running(is_running: bool, status: str = "running", diagnosis_id: str = None):
    """兼容旧 API - 设置运行状态"""
    return set_task_running(TASK_TYPE_MANUAL, is_running, status, diagnosis_id)


def get_diagnosis_progress():
    """兼容旧 API - 获取诊断进度"""
    return get_task_progress(TASK_TYPE_MANUAL)


def reset_diagnosis_progress():
    """兼容旧 API - 重置诊断进度"""
    return reset_task_progress(TASK_TYPE_MANUAL)


def is_diagnosis_in_progress():
    """兼容旧 API - 检查是否正在诊断"""
    return is_task_running(TASK_TYPE_MANUAL)
