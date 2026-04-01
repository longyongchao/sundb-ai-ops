# SunDB AI-Ops

基于 LLM 的数据库智能运维系统。

## 快速启动

### 前置条件

- Python >= 3.10
- Node.js >= 18

### 1. 后端

```bash
# 安装依赖
pip install -r requirements.txt

# 首次运行：生成配置文件
python copy_config_example.py

# 首次运行：复制环境变量文件并填入实际值
cp .env.example .env
# 编辑 .env，配置以下变量：
#   DEEPSEEK_API_KEY    — DeepSeek API 密钥
#   PG_HOST / PG_PORT / PG_USER / PG_PASSWORD / PG_DATABASE — PostgreSQL 连接信息
#   DEFAULT_ADMIN_PASSWORD — 管理员初始密码

# 修改 configs/model_config.py 中的 LLM 配置（API Key 等）

# 首次运行：初始化知识库
python init_database.py --recreate-vs

# 启动后端服务（端口 7861）
python run_server.py
```

API 文档：http://localhost:7861/docs

### 2. 前端

```bash
cd webui-react

# 安装依赖
npm install

# 启动开发服务器（端口 3001，自动代理到后端 7861）
npm run dev
```

访问：http://localhost:3001
