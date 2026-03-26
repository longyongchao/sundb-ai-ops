# D-Bot 前端 - 毕设增量开发文档

## 📋 项目概述

本项目基于 D-Bot 论文 (VLDB 2024) 实现，包含以下核心功能：

### 🎯 已实现功能

#### 1. 前端可视化组件 (`src/components/Charts/`)

| 组件 | 文件 | 论文引用 | 说明 |
|------|------|----------|------|
| 资源波动折线图 | `MetricLineChart.jsx` | Section 2.1 | 展示 CPU、内存等指标时间序列 |
| 异常分类饼图 | `AnomalyPieChart.jsx` | Section 2.1 | 展示异常类型分布 |
| 指标相关性热力图 | `DiagnosisHeatMap.jsx` | Section 5.1 | **毕设亮点** - 指标相关性矩阵 |
| 推理过程树形图 | `ReasoningTreeChart.jsx` | Section 6 | **毕设核心** - Thought→Action→Observation |

#### 2. 页面组件 (`src/pages/`)

| 页面 | 路由 | 功能 |
|------|------|------|
| Dashboard | `/dashboard` | 监控仪表盘，展示系统概览 |
| Diagnosis | `/diagnosis` | **核心诊断页面**，Tree Search 推理可视化 |
| Reports | `/reports` | 诊断报告历史管理 |
| Knowledge | `/knowledge` | 知识库管理 |
| KnowledgeChat | `/knowledge-chat` | 知识库对话 |
| Monitoring | `/monitoring` | 实时监控 |
| Settings | `/settings` | 系统配置 |

#### 3. 后端算法 (`server/diagnose/`)

| 文件 | 论文引用 | 说明 |
|------|----------|------|
| `tree_search_service.py` | Section 6 | Tree Search 算法实现 |
| `diagnose.py` | Section 6 | API 接口增强 |

### 🚀 启动方式

```bash
# 1. 安装依赖
cd webui-react
npm install

# 2. 启动开发服务器
npm run dev

# 3. 启动后端 (另一个终端)
cd ..
python server/api.py --host 0.0.0.0 --port 7861
```

### 📡 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/diagnose/quick` | POST | 快速诊断 (Tree Search) |
| `/diagnose/result` | GET | 获取诊断结果 |
| `/api/dashboard/metrics` | GET | 获取仪表盘数据 |

### 📝 论文引用标注

所有新增代码均标注了 `Reference: D-Bot Paper Section X`，方便写论文时引用。

### 🔧 Mock 数据支持

所有组件都支持 Mock 数据，在后端未就绪时也能正常演示。

---

## 文件结构

```
webui-react/src/
├── components/
│   └── Charts/
│       ├── MetricLineChart.jsx    # 资源监控折线图
│       ├── AnomalyPieChart.jsx    # 异常分类饼图
│       ├── DiagnosisHeatMap.jsx   # 相关性热力图 (毕设亮点)
│       ├── ReasoningTreeChart.jsx # 推理过程可视化 (毕设核心)
│       └── index.js
├── pages/
│   ├── Dashboard/     # 仪表盘
│   ├── Diagnosis/     # 诊断页面
│   ├── Reports/       # 报告管理
│   ├── Knowledge/     # 知识库
│   ├── KnowledgeChat/ # 知识对话
│   ├── Monitoring/    # 实时监控
│   └── Settings/      # 系统设置
└── layouts/
    └── MainLayout/    # 主布局

server/diagnose/
├── tree_search_service.py  # Tree Search 算法
└── diagnose.py             # 诊断 API