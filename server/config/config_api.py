#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : config_api.py
@Author  : LI
@Date    : 2026
@Desc    : 系统配置管理模块
            提供 LLM、数据库、通知、安全等配置的持久化存储与读取
"""
import os
import json
from typing import Optional
from pydantic import BaseModel
from server.utils import BaseResponse

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs")


class LLMSettings(BaseModel):
    """
    @class LLMSettings
    @brief 大语言模型配置模型
    @param model_type: 模型类型（deepseek/openai/local）
    @param model_name: 模型名称
    @param api_key: API 密钥
    @param api_base: API 基础 URL
    @param temperature: 生成温度参数
    @param max_tokens: 最大生成 token 数
    """
    model_type: str = "deepseek"
    model_name: str = "deepseek-chat"
    api_key: Optional[str] = None
    api_base: str = "https://api.deepseek.com"
    temperature: float = 0.7
    max_tokens: int = 4096


class DatabaseSettings(BaseModel):
    """
    @class DatabaseSettings
    @brief 数据库连接配置模型
    @param db_type: 数据库类型（postgresql/mysql/sqlite）
    @param host: 主机地址
    @param port: 端口号
    @param username: 用户名
    @param password: 密码
    @param database: 数据库名称
    """
    db_type: str = "postgresql"
    host: str = "localhost"
    port: int = 5432
    username: str = "postgres"
    password: Optional[str] = None
    database: str = "postgres"


class NotificationSettings(BaseModel):
    """
    @class NotificationSettings
    @brief 通知配置模型
    @param email_enabled: 是否启用邮件通知
    @param dingtalk_enabled: 是否启用钉钉通知
    @param wechat_enabled: 是否启用企业微信通知
    @param cpu_threshold: CPU 告警阈值
    @param memory_threshold: 内存告警阈值
    """
    email_enabled: bool = False
    dingtalk_enabled: bool = False
    wechat_enabled: bool = False
    cpu_threshold: int = 80
    memory_threshold: int = 85


class SecuritySettings(BaseModel):
    """
    @class SecuritySettings
    @brief 安全配置模型
    @param api_auth_enabled: 是否启用 API 认证
    @param cors_enabled: 是否启用跨域请求
    @param log_level: 日志级别
    """
    api_auth_enabled: bool = True
    cors_enabled: bool = True
    log_level: str = "INFO"


SETTINGS_FILE = os.path.join(CONFIG_DIR, "user_settings.json")


def load_settings():
    """
    @brief 加载用户配置
    @return: 配置字典
    """
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "llm": LLMSettings().dict(),
        "database": DatabaseSettings().dict(),
        "notification": NotificationSettings().dict(),
        "security": SecuritySettings().dict()
    }


def save_settings(settings: dict):
    """
    @brief 保存用户配置
    @param settings: 配置字典
    @return: 保存成功返回 True
    """
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return True


async def get_all_settings():
    """
    @brief 获取所有配置
    @return: API 响应对象
    """
    return BaseResponse(code=200, msg="success", data=load_settings())


async def get_llm_settings():
    """
    @brief 获取 LLM 配置
    @return: API 响应对象
    """
    settings = load_settings()
    return BaseResponse(code=200, msg="success", data=settings.get("llm", LLMSettings().dict()))


async def save_llm_settings(settings: LLMSettings):
    """
    @brief 保存 LLM 配置
    @param settings: LLM 配置对象
    @return: API 响应对象
    """
    all_settings = load_settings()
    all_settings["llm"] = settings.dict()
    if save_settings(all_settings):
        return BaseResponse(code=200, msg="LLM 配置保存成功")
    return BaseResponse(code=500, msg="保存失败")


async def get_database_settings():
    """
    @brief 获取数据库配置
    @return: API 响应对象
    """
    settings = load_settings()
    return BaseResponse(code=200, msg="success", data=settings.get("database", DatabaseSettings().dict()))


async def save_database_settings(settings: DatabaseSettings):
    """
    @brief 保存数据库配置
    @param settings: 数据库配置对象
    @return: API 响应对象
    """
    all_settings = load_settings()
    all_settings["database"] = settings.dict()
    if save_settings(all_settings):
        return BaseResponse(code=200, msg="数据库配置保存成功")
    return BaseResponse(code=500, msg="保存失败")


async def get_notification_settings():
    """
    @brief 获取通知配置
    @return: API 响应对象
    """
    settings = load_settings()
    return BaseResponse(code=200, msg="success", data=settings.get("notification", NotificationSettings().dict()))


async def save_notification_settings(settings: NotificationSettings):
    """
    @brief 保存通知配置
    @param settings: 通知配置对象
    @return: API 响应对象
    """
    all_settings = load_settings()
    all_settings["notification"] = settings.dict()
    if save_settings(all_settings):
        return BaseResponse(code=200, msg="通知配置保存成功")
    return BaseResponse(code=500, msg="保存失败")


async def get_security_settings():
    """
    @brief 获取安全配置
    @return: API 响应对象
    """
    settings = load_settings()
    return BaseResponse(code=200, msg="success", data=settings.get("security", SecuritySettings().dict()))


async def save_security_settings(settings: SecuritySettings):
    """
    @brief 保存安全配置
    @param settings: 安全配置对象
    @return: API 响应对象
    """
    all_settings = load_settings()
    all_settings["security"] = settings.dict()
    if save_settings(all_settings):
        return BaseResponse(code=200, msg="安全配置保存成功")
    return BaseResponse(code=500, msg="保存失败")


async def test_database_connection(settings: DatabaseSettings):
    """
    @brief 测试数据库连接
    @param settings: 数据库配置对象
    @return: API 响应对象
    """
    try:
        if settings.db_type == "postgresql":
            import psycopg2
            conn = psycopg2.connect(
                host=settings.host,
                port=settings.port,
                user=settings.username,
                password=settings.password or "",
                database=settings.database,
                connect_timeout=5
            )
            conn.close()
            return BaseResponse(code=200, msg="PostgreSQL 连接成功")
        elif settings.db_type == "mysql":
            import pymysql
            conn = pymysql.connect(
                host=settings.host,
                port=settings.port,
                user=settings.username,
                password=settings.password or "",
                database=settings.database,
                connect_timeout=5
            )
            conn.close()
            return BaseResponse(code=200, msg="MySQL 连接成功")
        elif settings.db_type == "sqlite":
            import sqlite3
            conn = sqlite3.connect(settings.database)
            conn.close()
            return BaseResponse(code=200, msg="SQLite 连接成功")
        else:
            return BaseResponse(code=400, msg=f"不支持的数据库类型: {settings.db_type}")
    except Exception as e:
        return BaseResponse(code=500, msg=f"连接失败: {str(e)}")


async def test_llm_connection(settings: LLMSettings):
    """
    @brief 测试 LLM 连接
    @param settings: LLM 配置对象
    @return: API 响应对象
    """
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.api_base
        )
        response = client.chat.completions.create(
            model=settings.model_name,
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=10
        )
        return BaseResponse(code=200, msg="LLM 连接测试成功")
    except Exception as e:
        return BaseResponse(code=500, msg=f"连接失败: {str(e)}")
