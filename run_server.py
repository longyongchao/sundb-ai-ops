#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
直接启动后端服务脚本
"""
import sys
import os
import subprocess

# ========== Windows 系统 UTF-8 编码设置 ==========
# 强制将 Python 标准输入输出的编码设为 UTF-8，解决 Windows 下 GBK 编码问题
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')

# 设置项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['NO_PROXY'] = '*'
for env_key in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
    os.environ.pop(env_key, None)

# 自动安装缺失的依赖
REQUIRED_PACKAGES = ['rank_bm25']
for package in REQUIRED_PACKAGES:
    try:
        __import__(package)
    except ImportError:
        print(f"正在安装缺失的依赖: {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package, "-q"])
        print(f"✅ {package} 安装完成")

import uvicorn
from server.api import create_app
from server.diagnose.db_connector import start_metrics_collector, get_real_metrics
from server.diagnose.anomaly_detector import init_detector
from server.diagnose.scheduler_service import init_scheduler

def on_anomaly_detected(alerts, metrics):
    """异常检测回调函数"""
    print(f"\n{'='*50}")
    print(f"[异常检测] 检测到 {len(alerts)} 个告警")
    for alert in alerts:
        print(f"  - [{alert.severity.upper()}] {alert.alertname}: {alert.description}")
    print(f"{'='*50}\n")

def on_diagnosis_triggered(alerts, metrics):
    """自动诊断触发回调函数"""
    print(f"\n{'='*50}")
    print(f"[自动诊断] 触发自动诊断，告警数: {len(alerts)}")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    app = create_app()
    
    # 启动系统指标收集器
    start_metrics_collector()
    print("✅ 系统指标收集器已启动")
    
    # 初始化异常检测器
    detector = init_detector(
        thresholds={
            "cpu_usage": 0.80,
            "memory_usage": 0.85,
            "disk_io_util": 0.90,
            "slow_query_count": 10
        },
        min_diagnosis_interval=300,
        on_anomaly_detected=on_anomaly_detected,
        on_diagnosis_triggered=on_diagnosis_triggered
    )
    print("✅ 异常检测器已初始化")
    
    # 初始化调度服务（默认不自动启动，需用户手动开启）
    scheduler = init_scheduler(
        metrics_collector=get_real_metrics,
        anomaly_detector=detector,
        auto_diagnosis_enabled=True,
        auto_start=False  # 【2024修复】默认关闭监控，需用户手动开启
    )
    print("✅ 调度服务已初始化（监控默认关闭）")
    
    # 打印所有路由
    print("\n" + "="*50)
    print("已注册的路由:")
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            print(f"  {route.methods} {route.path}")
    print("="*50 + "\n")
    
    print("📋 自动监控功能已启用:")
    print("   ✅ 监控数据采集（10秒/次）")
    print("   ✅ 异常检测判断（30秒/次）")
    print("   ✅ 监控数据持久化（1分钟/次）")
    print("   ✅ 自动诊断触发（检测到异常后）")
    print("")
    print("📊 历史数据查询 API:")
    print("   - GET /api/history/monitoring - 获取监控历史")
    print("   - GET /api/history/alerts - 获取告警历史")
    print("   - GET /api/history/statistics - 获取统计信息")
    print("")
    
    uvicorn.run(app, host="0.0.0.0", port=7861)
