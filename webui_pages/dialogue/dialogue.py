import streamlit as st
from webui_pages.utils import *
from streamlit_chatbox import *

# 1. 彻底解决头像路径报错
chat_box = ChatBox()


def dialogue_page(api: ApiRequest, is_lite: bool = False):
    st.session_state.setdefault("history", [])
    if not chat_box.chat_inited:
        chat_box.init_session()

    with st.sidebar:
        # 2. 恢复所有功能选项
        dialogue_modes = ["LLM 对话", "知识库问答", "搜索引擎问答"]
        dialogue_mode = st.selectbox("请选择对话模式：", dialogue_modes, key="dialogue_mode")

        # 强制提醒，DeepSeek 正在工作
        st.info("当前引擎: DeepSeek-V3 (云端)")
        llm_model = "deepseek-chat"
        temperature = st.slider("Temperature:", 0.0, 1.0, 0.7, 0.1)

    chat_box.output_messages()

    if prompt := st.chat_input("请输入您的问题"):
        chat_box.user_say(prompt)
        chat_box.ai_say("思考中...")

        try:
            text = ""
            # 根据模式调用接口
            if dialogue_mode == "LLM 对话":
                res = api.chat_chat(prompt, history=st.session_state.get("history", []), model=llm_model)
            elif dialogue_mode == "知识库问答":
                kb_name = st.session_state.get("selected_kb", "")
                res = api.knowledge_base_chat(prompt, knowledge_base_name=kb_name,
                                              history=st.session_state.get("history", []), model=llm_model)
            else:
                res = api.chat_chat(prompt, model=llm_model)

            # 3. 万能解析逻辑：管它后端传什么，全都转成字
            for d in res:
                content = ""
                if isinstance(d, str):  # 如果传回来的是纯文本
                    content = d
                elif isinstance(d, dict):  # 如果传回来的是字典
                    content = d.get("answer") or d.get("text") or d.get("content") or ""
                else:  # 如果是 Pydantic 对象
                    content = getattr(d, "answer", getattr(d, "text", str(d)))

                if content:
                    text += content
                    chat_box.update_msg(text, streaming=True)

            # 4. 兜底逻辑：如果最后还是没字，检查是否报错
            if not text:
                text = "系统已连接，但未检测到有效回复。请检查您的 DeepSeek API Key 是否有余额。"

            chat_box.update_msg(text, streaming=False)
            st.session_state["history"] = st.session_state["history"] + [{"role": "user", "content": prompt},
                                                                         {"role": "assistant", "content": text}]

        except Exception as e:
            st.error(f"连接失败: {str(e)}")