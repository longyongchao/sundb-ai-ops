import streamlit as st
import os
import sys

# ========================================================
# 🚀 DB-GPT WebUI 数据库强制对齐补丁 (核心修复)
# ========================================================
# 1. 强制设置环境变量，确保所有子模块都读取 Postgres
PG_URL = "postgresql://postgres:123456@127.0.0.1:5432/dbgpt_metadata"
os.environ["LOCAL_DB_URL"] = PG_URL
os.environ["DATABASE_URL"] = PG_URL

# 2. 拦截并重定向 SQLAlchemy 连接
try:
    import sqlalchemy
    _original_create_engine = sqlalchemy.create_engine
    def _patched_create_engine(*args, **kwargs):
        # 如果检测到连接串里包含 sqlite，强制替换为 postgres
        if args and isinstance(args[0], str) and "sqlite" in args[0]:
            return _original_create_engine(PG_URL, **kwargs)
        return _original_create_engine(*args, **kwargs)
    sqlalchemy.create_engine = _patched_create_engine
except Exception:
    pass

# 3. 运行时驱动检查
try:
    import psycopg2
except ImportError:
    st.error("❌ 严重错误：未检测到 PostgreSQL 驱动！")
    st.code("请在终端执行：D:\\Conda_Latest\\python.exe -m pip install psycopg2-binary")
    st.stop()
# ========================================================

from webui_pages.diagnose import diagnose_page
from webui_pages.reports.resports import reports_page
from webui_pages.utils import *
from streamlit_option_menu import option_menu
from webui_pages.dialogue.dialogue import dialogue_page
from webui_pages.knowledge_base import knowledge_base_page

from configs import VERSION
from server.utils import api_address

api = ApiRequest(base_url=api_address())

if __name__ == "__main__":
    is_lite = True

    st.set_page_config(
        "DB-GPT",
        os.path.join("img", "chat_icon_blue_square_v2.png"),
        layout="wide",
        initial_sidebar_state="expanded"
    )

    css = """
    <style>
        .block-container {
            padding-left: 20px !important;
            padding-right: 20px !important;
            padding-top: 40px !important;
            padding-bottom: 40px !important;
        }
    </style>
    """
    st.write(css, unsafe_allow_html=True)

    pages = {
        "Knowledge Base": {
            "icon": "hdd-stack",
            "func": knowledge_base_page,
        },
        "Chat": {
            "icon": "chat",
            "func": dialogue_page,
        },
        "Diagnosis": {
            "icon": "heart-pulse",
            "func": diagnose_page,
        },
        "History": {
            "icon": "file-earmark-text",
            "func": reports_page,
        }
    }

    with st.sidebar:
        st.caption(
            f"""<p align="right">D-Bot Version：{VERSION}</p>""",
            unsafe_allow_html=True,
        )
        options = list(pages)
        icons = [x["icon"] for x in pages.values()]

        default_index = 0
        selected_page = option_menu(
            "",
            options=options,
            icons=icons,
            default_index=default_index,
        )

    if selected_page in pages:
        pages[selected_page]["func"](api=api, is_lite=is_lite)