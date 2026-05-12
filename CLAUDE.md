# CLAUDE.md

## 项目概览

sundb-ai-ops 是基于 D-Bot (VLDB 2024) 的数据库智能诊断系统，提供 RESTful API 服务。技术栈：Python 3.9 + FastAPI + LangChain + SQLite + DeepSeek LLM。

## 项目结构

```
server/           # 后端服务代码
  api.py          # FastAPI 入口，所有路由在此注册
  utils.py        # 公共工具（BaseResponse, get_ChatOpenAI, robust_json_parse 等）
  diagnose/       # 诊断模块（解析器、API、诊断引擎）
  chat/           # 对话模块
configs/          # 配置常量
tests/            # 测试（按功能模块分子目录）
```

## 开发命令

```bash
# 运行全部测试
python3 -m pytest tests/ -v

# 运行单模块测试
python3 -m pytest tests/lilac/ -v

# 验证模块可导入
python3 -c "from server.diagnose.lilac import LilacParser; print('OK')"

# 启动完整服务（需要 fastchat 等完整依赖）
python3 server/api.py --port 7861
```

## 关键约定

### API 开发模式

- 所有 API 返回 `BaseResponse(code, msg, data)` 格式（来自 `server/utils.py`）
- 路由在 `server/api.py` 的 `mount_*_routes()` 函数中注册，用 try/except 包裹以允许部分模块缺失
- 新模块的 API 层单独放一个文件（如 `server/diagnose/xxx_api.py`），不要混入业务逻辑
- 全局单例用模块级变量 + 延迟初始化函数（`_parser = None; def _get_parser(): ...`）

### 可复用的工具函数（server/utils.py）

| 函数 | 用途 |
|------|------|
| `get_ChatOpenAI(temperature=0.0)` | 获取 LLM 客户端（DeepSeek via OpenAI 兼容 API） |
| `robust_json_parse(text)` | 容错 JSON 解析（处理 LLM 输出中的格式问题） |
| `BaseResponse` | 标准 API 响应模型 |
| `with_llm_semaphore(coro, limit)` | **异步**并发限流，仅适用于 async 上下文 |

### 测试模式

- 每个模块目录下放 `conftest.py`，定义 fixtures（临时数据库、样本文件等）
- 用环境变量控制测试行为（如禁用 LLM/外部依赖）
- API 测试用 `fastapi.testclient.TestClient` 直接测试，不需要启动完整服务
- Mock LLM 时 patch 路径必须是**运行时 import 的路径**（如 `@patch("server.utils.get_ChatOpenAI")`），而非被测模块的本地引用

### Git 工作流

- 功能分支命名：`feat-<模块名>-<特性>`
- 提交粒度：一个独立功能/修复 = 一个 commit
- Commit message 格式：`type(scope): description`，type 为 feat/fix/test/refactor/docs

## 常见陷阱

1. **async vs sync**：`server/utils.py` 中的 `with_llm_semaphore` 是 async 函数，不能在同步代码中用 `with` 调用。同步场景直接调用 `llm.predict()` 即可。

2. **线程安全**：如果一个方法内部调用了同一个锁保护的其他方法，必须用 `threading.RLock()`（可重入锁），否则死锁。

3. **多行日志格式**：SunDB system.trc 等格式的 header 和 body 分两行。逐行解析前需要先做行合并（检测 header-only 行并与下一行拼接）。

4. **完整服务依赖**：`server/api.py` 的 import 链依赖 `fastchat` 等包。开发独立模块时，可构建最小 FastAPI 实例单独测试，不必启动完整服务。

5. **SQLite 并发**：使用 WAL 模式 + `check_same_thread=False` 支持多线程读写，但写操作仍需加锁序列化。

6. **测试隔离**：每个测试用临时文件（`tmp_path`/`tempfile`）创建独立数据库，通过环境变量注入路径，避免测试间互相污染。
