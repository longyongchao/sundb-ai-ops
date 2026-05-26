#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : api.py
@Author  : LI
@Date    : 2026
@Desc    : D-Bot 数据库智能诊断系统 - FastAPI 服务入口模块
            基于 D-Bot 论文 (VLDB 2024) 实现，提供数据库异常诊断 RESTful API
"""

import sys
import os
import logging

logger = logging.getLogger(__name__)

os.environ['NO_PROXY'] = '*'
for env_key in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
    os.environ.pop(env_key, None)

import asyncio
from typing import List, Literal
from server.utils import (
    BaseResponse,
    ListResponse,
    FastAPI,
    MakeFastAPIOffline,
    get_server_configs,
    get_prompt_template)
from server.llm_api import (list_running_models, list_config_models,
                            change_llm_model, stop_llm_model,
                            get_model_config, list_search_engines, llm_model)
from server.embeddings_api import embed_texts_endpoint
from server.chat.feedback import chat_feedback
from server.chat.completion import completion
from server.chat.search_engine_chat import search_engine_chat
from server.chat.openai_chat import openai_chat
from server.chat.chat import chat
from starlette.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Body
import uvicorn
import argparse
from configs.server_config import OPEN_CROSS_DOMAIN
from configs.model_config import NLTK_DATA_PATH
try:
    from configs import VERSION
except ImportError:
    VERSION = "1.0.0"
import nltk

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
nltk.data.path = [NLTK_DATA_PATH] + nltk.data.path


async def document():
    """API 文档重定向"""
    return RedirectResponse(url="/docs")


def create_app(run_mode: str = None):
    """
    创建 FastAPI 应用实例
    
    @param run_mode: 运行模式
    @return: FastAPI 应用实例
    """
    app = FastAPI(title="Datachat API Server", version=VERSION)
    MakeFastAPIOffline(app)
    if OPEN_CROSS_DOMAIN:
        app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
                           allow_headers=["*"])
    mount_app_routes(app, run_mode=run_mode)
    return app


def mount_app_routes(app: FastAPI, run_mode: str = None):
    """
    挂载所有 API 路由
    
    @param app: FastAPI 应用实例
    @param run_mode: 运行模式
    """
    app.get("/", summary="swagger 文档")(document)

    app.post("/chat/fastchat", tags=["Chat"])(openai_chat)
    app.post("/chat/chat", tags=["Chat"])(chat)
    app.post("/chat/search_engine_chat", tags=["Chat"])(search_engine_chat)
    app.post("/chat/feedback", tags=["Chat"])(chat_feedback)

    mount_knowledge_routes(app)
    mount_alert_routes(app)
    mount_auth_routes(app)
    mount_diagnose_routes(app)
    mount_evolution_routes(app)
    mount_anomaly_routes(app)
    mount_config_routes(app)

    from server.utils import all_embed_models
    app.get("/llm_model/list_models", tags=["LLM Model Management"])(llm_model)
    app.get("/llm_model/embed_models", tags=["LLM Model Management"])(all_embed_models)
    app.post("/llm_model/list_running_models", tags=["LLM Model Management"])(list_running_models)
    app.post("/llm_model/list_config_models", tags=["LLM Model Management"])(list_config_models)
    app.post("/llm_model/stop", tags=["LLM Model Management"])(stop_llm_model)
    app.post("/llm_model/change", tags=["LLM Model Management"])(change_llm_model)

    app.post("/server/configs", tags=["Server State"])(get_server_configs)
    app.post("/server/list_search_engines", tags=["Server State"])(list_search_engines)


def mount_diagnose_routes(app: FastAPI):
    """
    挂载诊断模块 API 路由
    实现论文 D-Bot Section 6 - Tree Search 诊断算法
    
    @param app: FastAPI 应用实例
    """
    try:
        from server.diagnose.diagnose import (
            diagnose_status, get_diagnose_terminal_output, run_diagnose,
            quick_diagnose, get_diagnosis_result, get_dashboard_metrics,
            get_database_connection_status, get_slow_queries_api,
            get_knowledge_base, match_anomaly_api, get_diagnosis_progress_api,
            translate_text,
            get_diagnosis_history, get_diagnosis_record_detail,
            get_diagnosis_statistics, export_diagnosis_report,
            reset_diagnosis_status, get_diagnosis_status_all,
            check_auto_task_status, cancel_auto_diagnosis
        )
        
        app.get("/diagnose/diagnose_status", tags=["Diagnose"])(diagnose_status)
        app.get("/diagnose/terminal_output", tags=["Diagnose"])(get_diagnose_terminal_output)
        app.post("/diagnose/run_diagnose", tags=["Diagnose"])(run_diagnose)
        
        app.post("/diagnose/quick", tags=["Diagnose"])(quick_diagnose)
        app.get("/diagnose/result", tags=["Diagnose"])(get_diagnosis_result)
        app.get("/diagnose/progress", tags=["Diagnose"])(get_diagnosis_progress_api)
        app.post("/diagnose/translate_text", tags=["Diagnose"])(translate_text)
        
        # 任务隔离相关接口
        app.get("/diagnose/status/all", tags=["Diagnose"])(get_diagnosis_status_all)
        app.post("/diagnose/reset_status", tags=["Diagnose"])(reset_diagnosis_status)
        
        # 优雅取消相关接口
        app.get("/diagnose/auto_task/status", tags=["Diagnose"])(check_auto_task_status)
        app.post("/diagnose/auto_task/cancel", tags=["Diagnose"])(cancel_auto_diagnosis)
        
        app.get("/api/dashboard/metrics", tags=["Dashboard"])(get_dashboard_metrics)
        
        app.get("/api/database/status", tags=["Database"])(get_database_connection_status)
        app.get("/api/database/slow_queries", tags=["Database"])(get_slow_queries_api)
        app.get("/api/knowledge/base", tags=["Knowledge"])(get_knowledge_base)
        app.post("/api/knowledge/match", tags=["Knowledge"])(match_anomaly_api)
        
        app.get("/api/diagnosis/history", tags=["Diagnosis Records"])(get_diagnosis_history)
        app.get("/api/diagnosis/detail/{record_id}", tags=["Diagnosis Records"])(get_diagnosis_record_detail)
        app.get("/api/diagnosis/statistics", tags=["Diagnosis Records"])(get_diagnosis_statistics)
        app.post("/api/diagnosis/export/{record_id}", tags=["Diagnosis Records"])(export_diagnosis_report)
        
        logger.info("All Diagnose routes mounted (including Tree Search + Real DB API + Diagnosis Records)")
    except Exception as e:
        import traceback
        logger.error(f"Failed to mount diagnose routes: {e}")
        traceback.print_exc()
    
    # SunDB TRC 日志解析接口
    try:
        from server.diagnose.sundb_trc_api import (
            upload_trc, upload_trc_directory,
            get_trc_fault_events, get_trc_timeline, get_trc_aeu_list,
            trc_diagnose,
        )
        app.post("/diagnose/upload_trc", tags=["SunDB TRC"])(upload_trc)
        app.post("/diagnose/upload_trc_directory", tags=["SunDB TRC"])(upload_trc_directory)
        app.post("/diagnose/trc_diagnose", tags=["SunDB TRC"])(trc_diagnose)
        app.get("/diagnose/trc/fault_events", tags=["SunDB TRC"])(get_trc_fault_events)
        app.get("/diagnose/trc/timeline", tags=["SunDB TRC"])(get_trc_timeline)
        app.get("/diagnose/trc/aeu_list", tags=["SunDB TRC"])(get_trc_aeu_list)
        logger.info("SunDB TRC routes mounted")
    except Exception as e:
        logger.warning(f"Failed to mount SunDB TRC routes: {e}")

    # LILAC 通用日志解析接口
    try:
        from server.diagnose.lilac_api import (
            lilac_parse, lilac_parse_csv, lilac_parse_text,
            lilac_cache_stats, lilac_cache_templates, lilac_cache_clear,
            lilac_seed,
        )
        app.post("/diagnose/lilac/parse", tags=["LILAC"])(lilac_parse)
        app.post("/diagnose/lilac/parse_csv", tags=["LILAC"])(lilac_parse_csv)
        app.post("/diagnose/lilac/parse_text", tags=["LILAC"])(lilac_parse_text)
        app.get("/diagnose/lilac/cache/stats", tags=["LILAC"])(lilac_cache_stats)
        app.get("/diagnose/lilac/cache/templates", tags=["LILAC"])(lilac_cache_templates)
        app.delete("/diagnose/lilac/cache", tags=["LILAC"])(lilac_cache_clear)
        app.post("/diagnose/lilac/seed", tags=["LILAC"])(lilac_seed)
        logger.info("LILAC routes mounted")
    except Exception as e:
        logger.warning(f"Failed to mount LILAC routes: {e}")

    mount_testcase_routes(app)
    mount_anomaly_detector_routes(app)


def mount_evolution_routes(app: FastAPI):
    """
    挂载自进化模块 API 路由。

    V0.1 只提供案例池、指标和反馈接口，不改变诊断主流程。
    """
    try:
        from server.evolution.api import (
            create_evolution_feedback,
            get_evolution_case,
            get_evolution_metrics,
            list_evolution_cases,
        )

        app.get("/evolution/cases", tags=["Evolution"])(list_evolution_cases)
        app.get("/evolution/cases/{case_id}", tags=["Evolution"])(get_evolution_case)
        app.get("/evolution/metrics", tags=["Evolution"])(get_evolution_metrics)
        app.post("/evolution/feedback", tags=["Evolution"])(create_evolution_feedback)
        logger.info("Evolution routes mounted")
    except Exception as e:
        logger.warning(f"Failed to mount evolution routes: {e}")


def mount_testcase_routes(app: FastAPI):
    """
    挂载测试文件库 API 路由
    
    @param app: FastAPI 应用实例
    """
    try:
        from server.diagnose.testcase_api import (
            get_testcase_list, get_testcase_categories,
            get_testcases_by_category, get_testcase_detail,
            get_testcase_statistics
        )
        
        app.get("/api/testcases/list", tags=["Test Cases"])(get_testcase_list)
        app.get("/api/testcases/categories", tags=["Test Cases"])(get_testcase_categories)
        app.get("/api/testcases/category/{category_id}", tags=["Test Cases"])(get_testcases_by_category)
        app.get("/api/testcases/{case_id}", tags=["Test Cases"])(get_testcase_detail)
        app.get("/api/testcases/statistics", tags=["Test Cases"])(get_testcase_statistics)
        
        logger.info("Test Cases routes mounted")
    except Exception as e:
        import traceback
        logger.error(f"Failed to mount testcase routes: {e}")
        traceback.print_exc()


def mount_anomaly_detector_routes(app: FastAPI):
    """
    挂载异常检测 API 路由
    
    @param app: FastAPI 应用实例
    """
    try:
        from server.diagnose.anomaly_detector import get_detector
        from server.diagnose.scheduler_service import get_scheduler
        from server.utils import BaseResponse
        
        @app.get("/api/anomaly/status", tags=["Anomaly Detection"])
        async def get_anomaly_status():
            """获取异常检测状态"""
            detector = get_detector()
            return BaseResponse(code=200, msg="Success", data=detector.get_state())
        
        @app.get("/api/anomaly/alerts", tags=["Anomaly Detection"])
        async def get_anomaly_alerts(limit: int = 100):
            """获取告警历史"""
            detector = get_detector()
            return BaseResponse(code=200, msg="Success", data=detector.get_alert_history(limit))
        
        @app.delete("/api/anomaly/alerts", tags=["Anomaly Detection"])
        async def clear_anomaly_alerts():
            """清空告警历史"""
            detector = get_detector()
            detector.clear_alert_history()
            return BaseResponse(code=200, msg="Alerts cleared", data=None)
        
        @app.post("/api/anomaly/thresholds", tags=["Anomaly Detection"])
        async def update_anomaly_thresholds(thresholds: dict = Body(...)):
            """更新异常检测阈值"""
            detector = get_detector()
            detector.update_thresholds(thresholds)
            return BaseResponse(code=200, msg="Thresholds updated", data=detector.thresholds)
        
        @app.get("/api/scheduler/status", tags=["Scheduler"])
        async def get_scheduler_status():
            """获取调度服务状态"""
            scheduler = get_scheduler()
            return BaseResponse(code=200, msg="Success", data=scheduler.get_status())
        
        @app.post("/api/scheduler/auto_diagnosis", tags=["Scheduler"])
        async def set_auto_diagnosis(enabled: bool = Body(..., embed=True)):
            """设置自动诊断开关"""
            scheduler = get_scheduler()
            scheduler.set_auto_diagnosis(enabled)
            return BaseResponse(code=200, msg=f"Auto diagnosis {'enabled' if enabled else 'disabled'}", data=None)
        
        @app.post("/api/scheduler/start", tags=["Scheduler"])
        async def start_scheduler():
            """启动调度服务"""
            scheduler = get_scheduler()
            scheduler.start()
            return BaseResponse(code=200, msg="Scheduler started", data=scheduler.get_status())
        
        @app.post("/api/scheduler/stop", tags=["Scheduler"])
        async def stop_scheduler():
            """停止调度服务"""
            scheduler = get_scheduler()
            scheduler.stop()
            return BaseResponse(code=200, msg="Scheduler stopped", data=None)
        
        @app.post("/api/monitoring/toggle", tags=["Monitoring"])
        async def toggle_monitoring(enabled: bool = Body(..., embed=True)):
            """
            切换监控开关状态
            
            @param enabled: true=开启监控，false=暂停监控
            @return: 操作结果
            """
            scheduler = get_scheduler()
            
            if enabled:
                success = scheduler.resume_monitoring()
                msg = "监控已开启" if success else "开启监控失败"
            else:
                success = scheduler.pause_monitoring()
                msg = "监控已暂停" if success else "暂停监控失败"
            
            return BaseResponse(
                code=200 if success else 500,
                msg=msg,
                data={
                    "monitoring_enabled": scheduler.is_monitoring_active(),
                    "success": success
                }
            )
        
        @app.get("/api/monitoring/status", tags=["Monitoring"])
        async def get_monitoring_status():
            """获取监控状态"""
            scheduler = get_scheduler()
            return BaseResponse(
                code=200,
                msg="Success",
                data={
                    "monitoring_enabled": scheduler.is_monitoring_active(),
                    "auto_diagnosis_enabled": scheduler._auto_diagnosis_enabled,
                    "scheduler_status": scheduler.get_status()
                }
            )
        
        logger.info("Anomaly Detection and Scheduler routes mounted")
    except Exception as e:
        import traceback
        logger.error(f"Failed to mount anomaly detector routes: {e}")
        traceback.print_exc()
    
    mount_history_routes(app)


def mount_history_routes(app: FastAPI):
    """
    挂载历史数据查询 API 路由
    
    @param app: FastAPI 应用实例
    """
    try:
        from server.diagnose.history_api import (
            get_monitoring_history,
            get_alert_history,
            get_history_statistics,
            get_trend_data,
            update_alert_status
        )
        
        app.get("/api/history/monitoring", tags=["History"])(get_monitoring_history)
        app.get("/api/history/alerts", tags=["History"])(get_alert_history)
        app.get("/api/history/statistics", tags=["History"])(get_history_statistics)
        app.get("/api/history/trend", tags=["History"])(get_trend_data)
        app.put("/api/history/alerts/{alert_id}/status", tags=["History"])(update_alert_status)
        
        logger.info("History routes mounted")
    except Exception as e:
        import traceback
        logger.error(f"Failed to mount history routes: {e}")
        traceback.print_exc()
    
    mount_notification_routes(app)


def mount_notification_routes(app: FastAPI):
    """
    挂载通知 API 路由
    
    @param app: FastAPI 应用实例
    """
    try:
        from server.diagnose.notification_api import (
            get_unread_notifications,
            get_all_notifications,
            mark_notification_read,
            mark_all_read,
            get_unread_count
        )
        
        app.get("/api/notifications/unread", tags=["Notifications"])(get_unread_notifications)
        app.get("/api/notifications/all", tags=["Notifications"])(get_all_notifications)
        app.put("/api/notifications/read", tags=["Notifications"])(mark_notification_read)
        app.put("/api/notifications/read-all", tags=["Notifications"])(mark_all_read)
        app.get("/api/notifications/count", tags=["Notifications"])(get_unread_count)
        
        logger.info("Notification routes mounted")
    except Exception as e:
        import traceback
        logger.error(f"Failed to mount notification routes: {e}")
        traceback.print_exc()


def mount_alert_routes(app: FastAPI):
    """
    挂载告警模块 API 路由
    
    @param app: FastAPI 应用实例
    """
    try:
        from server.report.report import histories, diagnose_llm_model_list, delete_history, clear_all_histories, get_user_stats
        app.get("/report/histories", tags=["Alert"])(histories)
        app.get("/reports", tags=["Alert"])(histories)  # 添加 /reports 路由，与前端保持一致
        app.get("/report/diagnose_llm_model_list", tags=["Report"])(diagnose_llm_model_list)
        app.delete("/report/histories/{file_name}", tags=["Report"])(delete_history)
        app.delete("/report/histories", tags=["Report"])(clear_all_histories)
        app.get("/api/user/stats", tags=["User"])(get_user_stats)
    except Exception as e:
        logger.warning(f"Failed to mount alert routes: {e}")


def mount_auth_routes(app: FastAPI):
    """
    挂载认证模块 API 路由
    
    @param app: FastAPI 应用实例
    """
    try:
        from server.auth.auth_service import login, logout, verify_token, check_auth, init_default_user, register
        app.post("/api/auth/login", tags=["Auth"])(login)
        app.post("/api/auth/logout", tags=["Auth"])(logout)
        app.post("/api/auth/register", tags=["Auth"])(register)
        app.get("/api/auth/verify", tags=["Auth"])(verify_token)
        app.get("/api/auth/check", tags=["Auth"])(check_auth)
        
        init_default_user()
        logger.info("Auth routes mounted")
    except Exception as e:
        logger.warning(f"Failed to mount auth routes: {e}")


def mount_anomaly_routes(app: FastAPI):
    """
    挂载异常注入模块 API 路由
    用于模拟数据库异常场景，验证诊断系统准确性
    
    @param app: FastAPI 应用实例
    """
    try:
        from server.anomaly.api import (
            inject_anomaly, inject_anomaly_async,
            get_evaluation_results, add_evaluation_result,
            clear_evaluation_results, get_anomaly_types
        )
        app.post("/api/anomaly/inject", tags=["Anomaly"])(inject_anomaly)
        app.post("/api/anomaly/inject_async", tags=["Anomaly"])(inject_anomaly_async)
        app.get("/api/anomaly/types", tags=["Anomaly"])(get_anomaly_types)
        
        app.get("/api/evaluation/results", tags=["Evaluation"])(get_evaluation_results)
        app.post("/api/evaluation/add", tags=["Evaluation"])(add_evaluation_result)
        app.delete("/api/evaluation/clear", tags=["Evaluation"])(clear_evaluation_results)
        
        logger.info("Anomaly routes mounted")
    except Exception as e:
        logger.warning(f"Failed to mount anomaly routes: {e}")


def mount_config_routes(app: FastAPI):
    """
    挂载系统配置管理 API 路由
    提供 LLM、数据库、通知、安全等配置的 CRUD 接口
    
    @param app: FastAPI 应用实例
    """
    try:
        from server.config.config_api import (
            get_all_settings, get_llm_settings, save_llm_settings,
            get_database_settings, save_database_settings,
            get_notification_settings, save_notification_settings,
            get_security_settings, save_security_settings,
            test_database_connection, test_llm_connection,
            LLMSettings, DatabaseSettings, NotificationSettings, SecuritySettings
        )
        
        @app.get("/api/settings/all", tags=["Settings"])
        async def api_get_all_settings():
            """获取所有系统配置"""
            return await get_all_settings()
        
        @app.get("/api/settings/llm", tags=["Settings"])
        async def api_get_llm_settings():
            """获取 LLM 模型配置"""
            return await get_llm_settings()
        
        @app.post("/api/settings/llm", tags=["Settings"])
        async def api_save_llm_settings(settings: LLMSettings):
            """保存 LLM 模型配置"""
            return await save_llm_settings(settings)
        
        @app.post("/api/settings/llm/test", tags=["Settings"])
        async def api_test_llm_connection(settings: LLMSettings):
            """测试 LLM API 连接"""
            return await test_llm_connection(settings)
        
        @app.get("/api/settings/database", tags=["Settings"])
        async def api_get_database_settings():
            """获取数据库连接配置"""
            return await get_database_settings()
        
        @app.post("/api/settings/database", tags=["Settings"])
        async def api_save_database_settings(settings: DatabaseSettings):
            """保存数据库连接配置"""
            return await save_database_settings(settings)
        
        @app.post("/api/settings/database/test", tags=["Settings"])
        async def api_test_database_connection(settings: DatabaseSettings):
            """测试数据库连接"""
            return await test_database_connection(settings)
        
        @app.get("/api/settings/notification", tags=["Settings"])
        async def api_get_notification_settings():
            """获取通知配置"""
            return await get_notification_settings()
        
        @app.post("/api/settings/notification", tags=["Settings"])
        async def api_save_notification_settings(settings: NotificationSettings):
            """保存通知配置"""
            return await save_notification_settings(settings)
        
        @app.get("/api/settings/security", tags=["Settings"])
        async def api_get_security_settings():
            """获取安全配置"""
            return await get_security_settings()
        
        @app.post("/api/settings/security", tags=["Settings"])
        async def api_save_security_settings(settings: SecuritySettings):
            """保存安全配置"""
            return await save_security_settings(settings)
        
        logger.info("Config routes mounted")
    except Exception as e:
        logger.warning(f"Failed to mount config routes: {e}")


def mount_knowledge_routes(app: FastAPI):
    """
    挂载知识库管理 API 路由
    实现论文 D-Bot Section 3 - 知识库构建与检索
    
    @param app: FastAPI 应用实例
    """
    try:
        from server.chat.knowledge_base_chat import knowledge_base_chat
        from server.knowledge_base.kb_api import list_kbs, create_kb, delete_kb, update_kb_info
        from server.knowledge_base.kb_doc_api import (list_files, upload_docs, delete_docs, 
                                                     update_docs, download_doc, recreate_vector_store,
                                                     kb_file_details, api_search_docs, api_search_all_docs)

        app.get("/knowledge_base/list_knowledge_bases", tags=["Knowledge Base Management"])(list_kbs)
        app.post("/knowledge_base/create_knowledge_base", tags=["Knowledge Base Management"])(create_kb)
        app.post("/knowledge_base/delete_knowledge_base", tags=["Knowledge Base Management"])(delete_kb)
        app.post("/knowledge_base/update_info", tags=["Knowledge Base Management"])(update_kb_info)
        
        app.get("/knowledge_base/list_files", tags=["Knowledge Base Management"])(list_files)
        app.get("/knowledge_base/kb_file_details", tags=["Knowledge Base Management"])(kb_file_details)
        app.post("/knowledge_base/upload_docs", tags=["Knowledge Base Management"])(upload_docs)
        app.post("/knowledge_base/delete_docs", tags=["Knowledge Base Management"])(delete_docs)
        app.post("/knowledge_base/update_docs", tags=["Knowledge Base Management"])(update_docs)
        app.get("/knowledge_base/download_doc", tags=["Knowledge Base Management"])(download_doc)
        app.post("/knowledge_base/recreate_vector_store", tags=["Knowledge Base Management"])(recreate_vector_store)
        app.post("/knowledge_base/search_docs", tags=["Knowledge Base Management"])(api_search_docs)
        app.post("/knowledge_base/search_all_docs", tags=["Knowledge Base Management"])(api_search_all_docs)
        
        app.post("/chat/knowledge_base_chat", tags=["Chat"])(knowledge_base_chat)

        logger.info("Knowledge Base routes mounted")
    except Exception as e:
        logger.error(f"Failed to mount knowledge routes: {e}")


def run_api(host, port, **kwargs):
    """
    启动 API 服务
    
    @param host: 服务地址
    @param port: 服务端口
    """
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7861)
    args = parser.parse_args()

    app = create_app()
    logger.info("API Server Starting")
    run_api(host=args.host, port=args.port)
