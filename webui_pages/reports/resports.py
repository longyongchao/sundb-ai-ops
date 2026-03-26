import streamlit as st
from streamlit.components.v1 import declare_component
from webui_pages.utils import *
import os

def reports_page(api: ApiRequest, is_lite: bool = False):
    # 1. 获取模型列表
    if "model_list" not in st.session_state:
        # 获取列表，并确保它至少是个空列表而不是 None
        model_list = api.diagnose_diagnose_llm_model_list()
        st.session_state["model_list"] = model_list if model_list is not None else []

    # 2. 安全地设置当前模型 (修复 'NoneType' object is not subscriptable)
    if "current_model" not in st.session_state:
        if len(st.session_state["model_list"]) > 0:
            st.session_state["current_model"] = st.session_state["model_list"][0]
        else:
            # 如果列表为空，给一个占位符，防止后面 api 调用报错
            st.session_state["current_model"] = "No Model Found"
            st.warning("⚠️ 后端未检测到运行中的模型，请检查 server 端日志或 model_config.py 配置。")

    # 3. 获取诊断历史记录 (增加判空逻辑)
    if st.session_state["current_model"] != "No Model Found":
        st.session_state["diagnose_histories"] = api.diagnose_histories(model=st.session_state["current_model"])
    else:
        st.session_state["diagnose_histories"] = []

    # 4. 加载自定义组件
    component_path = os.path.join(os.path.dirname(__file__), 'reports_ui/build_dist')
    my_component = declare_component("my_component", path=component_path)
    
    # 5. 渲染组件
    response = my_component(args={
        "modelList": st.session_state["model_list"],
        "currentModel": st.session_state["current_model"],
        "diagnoseHistories": st.session_state["diagnose_histories"]
    }, key="my_component")

    # 6. 处理组件交互
    try:
        if response and "model" in response:
            if response["model"] and response["model"] != st.session_state["current_model"]:
                st.session_state["current_model"] = response["model"]
                st.session_state["diagnose_histories"] = api.diagnose_histories(model=st.session_state["current_model"])
                st.rerun()
    except Exception as e:
        # 调试时可以在这里用 st.error(e) 看看报错
        print(f"Component Interaction Error: {e}")