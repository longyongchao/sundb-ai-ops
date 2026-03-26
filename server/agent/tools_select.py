from langchain.tools import Tool
from server.agent.tools import *

## 请注意，如果你是为了使用AgentLM，在这里，你应该使用英文版本。

# 定义工具配置列表，用于循环加载
tools_config = [
    {
        "func": calculate,
        "name": "calculate",
        "description": "Useful for when you need to answer questions about simple calculations",
        "args_schema": CalculatorInput,
    },
    {
        "func": arxiv,
        "name": "arxiv",
        "description": "A wrapper around Arxiv.org for searching and retrieving scientific articles in various fields.",
        "args_schema": ArxivInput,
    },
    {
        "func": weathercheck,
        "name": "weather_check",
        "description": "Check the weather of a city",
        "args_schema": WhetherSchema,
    },
    {
        "func": shell,
        "name": "shell",
        "description": "Use Shell to execute Linux commands",
        "args_schema": ShellInput,
    },
    {
        "func": search_knowledgebase_complex,
        "name": "search_knowledgebase_complex",
        "description": "Use this tool to search local knowledgebase and get information",
        "args_schema": KnowledgeSearchInput,
    },
    {
        "func": search_internet,
        "name": "search_internet",
        "description": "Use this tool to use bing search engine to search the internet",
        "args_schema": SearchInternetInput,
    },
    {
        "func": wolfram,
        "name": "Wolfram",
        "description": "Useful for when you need to calculate difficult formulas",
        "args_schema": WolframInput,
    },
    {
        "func": search_youtube,
        "name": "search_youtube",
        "description": "use this tools to search youtube videos",
        "args_schema": YoutubeInput,
    },
]

tools = []
# 采用安全加载模式，绕过 Pydantic 校验错误
for conf in tools_config:
    try:
        t = Tool.from_function(
            func=conf["func"],
            name=conf["name"],
            description=conf["description"],
            args_schema=conf["args_schema"],
        )
        tools.append(t)
    except Exception as e:
        # 如果某个工具加载失败（如 Pydantic 冲突），打印警告并跳过，保证主程序启动
        print(f"Warning: Tool {conf['name']} failed to load, skipping. Error: {e}")

tool_names = [tool.name for tool in tools]