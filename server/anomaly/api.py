"""
异常注入 API
提供前端触发异常注入的接口
"""
import os
import sys
import json
import subprocess
import threading
from datetime import datetime
from fastapi import Body
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server.utils import BaseResponse

# 异常注入脚本路径
ANOMALY_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts", "generate_anomaly.py"
)

# 评估结果存储路径
EVALUATION_RESULTS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "evaluation_results.json"
)

# 确保目录存在
os.makedirs(os.path.dirname(EVALUATION_RESULTS_FILE), exist_ok=True)


# 内存中的评估结果缓存
evaluation_results = []


def load_evaluation_results():
    """加载评估结果"""
    global evaluation_results
    try:
        if os.path.exists(EVALUATION_RESULTS_FILE):
            with open(EVALUATION_RESULTS_FILE, 'r', encoding='utf-8') as f:
                evaluation_results = json.load(f)
    except Exception as e:
        print(f"[WARNING] 加载评估结果失败: {e}")
        evaluation_results = []


def save_evaluation_results():
    """保存评估结果"""
    try:
        with open(EVALUATION_RESULTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(evaluation_results, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARNING] 保存评估结果失败: {e}")


# 启动时加载
load_evaluation_results()


def inject_anomaly(
    anomaly_type: str = Body(..., description="异常类型: slow_sql, lock, log"),
    duration: int = Body(30, description="持续时间(秒)"),
    threads: int = Body(5, description="线程数(锁竞争)"),
    count: int = Body(100, description="日志数量")
) -> BaseResponse:
    """
    注入异常 - 触发故障模拟
    """
    try:
        # 构建命令
        cmd = [
            sys.executable,
            ANOMALY_SCRIPT,
            "--type", anomaly_type,
            "--duration", str(duration),
            "--threads", str(threads),
            "--count", str(count)
        ]
        
        print(f"[INFO] 执行异常注入: {' '.join(cmd)}")
        
        # 执行脚本
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=duration + 60  # 超时时间
        )
        
        if result.returncode == 0:
            # 解析输出
            output = result.stdout
            
            return BaseResponse(
                code=200,
                msg="异常注入成功",
                data={
                    "type": anomaly_type,
                    "duration": duration,
                    "output": output,
                    "timestamp": datetime.now().isoformat()
                }
            )
        else:
            return BaseResponse(
                code=500,
                msg=f"异常注入失败: {result.stderr}",
                data={"error": result.stderr}
            )
            
    except subprocess.TimeoutExpired:
        return BaseResponse(
            code=500,
            msg="异常注入超时",
            data={"error": "Timeout"}
        )
    except Exception as e:
        return BaseResponse(
            code=500,
            msg=f"异常注入失败: {str(e)}",
            data={"error": str(e)}
        )


def inject_anomaly_async(
    anomaly_type: str = Body(..., description="异常类型"),
    duration: int = Body(30, description="持续时间"),
    threads: int = Body(5, description="线程数"),
    count: int = Body(100, description="日志数量")
) -> BaseResponse:
    """
    异步注入异常 - 立即返回，后台执行
    """
    def run_injection():
        try:
            cmd = [
                sys.executable,
                ANOMALY_SCRIPT,
                "--type", anomaly_type,
                "--duration", str(duration),
                "--threads", str(threads),
                "--count", str(count)
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 60)
        except Exception as e:
            print(f"[ERROR] 后台注入失败: {e}")
    
    # 启动后台线程
    thread = threading.Thread(target=run_injection)
    thread.daemon = True
    thread.start()
    
    return BaseResponse(
        code=200,
        msg="异常注入已启动",
        data={
            "type": anomaly_type,
            "duration": duration,
            "status": "running"
        }
    )


def get_evaluation_results() -> BaseResponse:
    """
    获取评估结果列表
    """
    return BaseResponse(
        code=200,
        msg="Success",
        data=evaluation_results
    )


def add_evaluation_result(
    anomaly_type: str = Body(..., description="异常类型"),
    diagnosis_time: float = Body(..., description="诊断耗时(秒)"),
    root_cause: str = Body(..., description="诊断根因"),
    is_hit: bool = Body(..., description="是否命中知识库"),
    suggestion: str = Body(..., description="建议摘要")
) -> BaseResponse:
    """
    添加评估结果
    """
    global evaluation_results
    
    result = {
        "id": len(evaluation_results) + 1,
        "anomaly_type": anomaly_type,
        "detection_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "diagnosis_time": round(diagnosis_time, 2),
        "root_cause": root_cause,
        "is_hit": is_hit,
        "hit_status": "Hit" if is_hit else "Miss",
        "suggestion": suggestion[:100] + "..." if len(suggestion) > 100 else suggestion
    }
    
    evaluation_results.append(result)
    save_evaluation_results()
    
    return BaseResponse(
        code=200,
        msg="评估结果已添加",
        data=result
    )


def clear_evaluation_results() -> BaseResponse:
    """
    清空评估结果
    """
    global evaluation_results
    evaluation_results = []
    save_evaluation_results()
    
    return BaseResponse(
        code=200,
        msg="评估结果已清空"
    )


def get_anomaly_types() -> BaseResponse:
    """
    获取支持的异常类型
    """
    return BaseResponse(
        code=200,
        msg="Success",
        data={
            "types": [
                {
                    "value": "slow_sql",
                    "label": "慢SQL (CPU波动)",
                    "description": "向测试表写入海量数据并执行无索引关联查询",
                    "params": ["duration"]
                },
                {
                    "value": "lock",
                    "label": "锁竞争 (死锁/行锁)",
                    "description": "通过多线程模拟两个事务互锁或长事务行锁",
                    "params": ["duration", "threads"]
                },
                {
                    "value": "log",
                    "label": "错误日志",
                    "description": "生成符合PostgreSQL标准格式的错误日志文件",
                    "params": ["count"]
                }
            ]
        }
    )