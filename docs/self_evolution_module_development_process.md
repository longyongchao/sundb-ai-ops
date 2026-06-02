# SunDB AI-Ops 自进化模块代码级开发流程文档

## 1. 文档目标

本文档用于指导在现有 SunDB AI-Ops 项目中开发“自进化模块”。交付目标分为三类：

- 工程交付：新增可运行、可测试、可回滚的 `server/evolution/` 后端模块，并逐步接入诊断、反馈、回放和版本发布流程。
- 软著交付：形成相对独立的软件功能模块、源代码、设计文档、用户手册、测试报告和版本说明，可整理为“SunDB AI-Ops 自进化智能诊断优化软件 V1.0”的软著材料。
- 专利交付：沉淀完整技术交底材料，围绕“诊断轨迹采集、结果评价、模式挖掘、候选补丁生成、沙盒回放、安全门控、版本回滚”的闭环形成专利方案。

说明：本文是研发流程和材料沉淀建议，不构成法律意见。正式软著和专利申请前，应由知识产权或专利代理人员复核。

## 2. 开发原则

1. 不改写原诊断主流程，只在关键节点旁路采集和评估。
2. 自进化候选默认不直接影响线上诊断，必须先进入候选池。
3. 任何自动生成的知识、提示词、工具策略、检索策略都必须带证据链、版本号和回滚信息。
4. 第一阶段只做“记录和可视化”，第二阶段才做“候选生成”，第三阶段再做“门控发布”。
5. 高风险动作，如自动执行优化 SQL，不纳入 V1.0；V1.0 只给出建议和候选补丁。

## 3. 分支与版本建议

建议新建开发分支：

```bash
git checkout -b codex/self-evolution-module
```

建议软著登记版本号使用：

```text
SunDB AI-Ops 自进化智能诊断优化软件 V1.0
```

建议版本节奏：

| 版本 | 目标 | 可登记/可演示材料 | 状态 |
| --- | --- | --- | --- |
| V0.1 | 诊断案例采集、评分器、反馈关联、自进化 API | 源码、接口说明、数据结构、单元测试 | **已完成** |
| V0.2 | 模式挖掘、候选生成 | 算法说明、测试报告 | **已完成** |
| V0.3 | 沙盒回放、安全门控、版本注册 | 回放报告、流程图 | 待开发 |
| V1.0 | 前端页面完善、完整闭环演示、文档归档 | 软著材料、专利交底书 | 待开发 |

## 4. 目标目录结构

新增后端目录：

```text
server/evolution/
  __init__.py              ✅ V0.1
  schemas.py               ✅ V0.1
  collector.py             ✅ V0.1
  evaluator.py             ✅ V0.1
  api.py                   ✅ V0.1 + V0.2 接口
  pattern_miner.py         ✅ V0.2（4 种规则挖掘）
  candidate_generator.py   ✅ V0.2（4 种候选生成器）
  replay_runner.py         ⬜ V0.3 待开发
  gatekeeper.py            ⬜ V0.3 待开发
  registry.py              ⬜ V0.3 待开发
```

新增数据库文件：

```text
server/db/models/evolution_model.py       ✅ V0.1+V0.2（EvolutionCase/Feedback/Pattern/Candidate）
server/db/repository/evolution_repository.py  ✅ V0.1+V0.2
```

新增测试：

```text
tests/unit/test_evolution_collector.py          ✅ V0.1（4 个测试）
tests/unit/test_evolution_evaluator.py          ✅ V0.1（4 个测试）
tests/unit/test_evolution_api.py                ✅ V0.1（5 个测试）
tests/unit/test_evolution_pattern_miner.py      ✅ V0.2（18 个测试）
tests/unit/test_evolution_candidate_generator.py ✅ V0.2（10 个测试）
tests/unit/test_evolution_gatekeeper.py         ⬜ V0.3 待开发
```

可选前端：

```text
webui-react/src/pages/Evolution/  ✅ 已完成（V0.1 基础页面）
webui-react/src/api/evolution.js  ✅ 已完成（通过 utils/api.jsx 集成）
```

## 5. 第一阶段：数据模型与仓储层

### 5.1 数据库模型（V0.1 + V0.2 已完成，V0.3 待扩展）

文件：`server/db/models/evolution_model.py`

计划六张表，当前已实现四张：

| 表名 | 状态 | 说明 |
| --- | --- | --- |
| `evolution_cases` | ✅ V0.1 | 诊断案例快照（输入/轨迹/知识/输出/资产版本/评分） |
| `evolution_feedback` | ✅ V0.1 | 用户反馈与指标恢复记录 |
| `evolution_patterns` | ✅ V0.2 | 从历史案例挖掘的失败模式 |
| `evolution_candidates` | ✅ V0.2 | 候选补丁（knowledge/tool/prompt/retrieval） |
| `evolution_experiments` | ⬜ V0.3 | 沙盒回放实验结果 |
| `evolution_artifacts` | ⬜ V0.3 | 已发布的版本化资产 |

V0.2 新增模型字段：

```python
class EvolutionPattern(Base):
    __tablename__ = "evolution_patterns"
    id, pattern_type, cluster_key, evidence_case_ids,
    failure_signature, suggested_update_type, confidence,
    status, create_time

class EvolutionCandidate(Base):
    __tablename__ = "evolution_candidates"
    id, candidate_type, source_pattern_id (FK→evolution_patterns),
    patch_content, expected_benefit, risk_level, status,
    evidence_case_ids, base_artifact_version, target_artifact_type,
    create_time, update_time
```

### 5.2 注册模型（已完成）

文件：`server/db/session.py`，已实际导入的模型：

```python
try:
    from server.db.models.evolution_model import (
        EvolutionCase, EvolutionFeedback,   # V0.1
        EvolutionPattern, EvolutionCandidate,  # V0.2
    )
except Exception:
    pass
```

项目使用 `Base.metadata.create_all(bind=engine)` 自动建表，无需 Alembic。V0.3 新增 `EvolutionExperiment`、`EvolutionArtifact` 时按相同方式追加导入即可。

### 5.3 仓储层（V0.1 + V0.2 已完成）

文件：`server/db/repository/evolution_repository.py`

**V0.1 已实现：**

```python
create_evolution_case(payload)
get_evolution_case_by_id(case_id)
get_evolution_case_by_record_id(record_id)
list_evolution_cases(limit, offset, label, status, anomaly_type)
count_evolution_cases(label, status, anomaly_type)
list_evolution_cases_for_mining(limit)          # 供模式挖掘专用（返回 negative+uncertain）
create_evolution_feedback(payload)
list_feedback_for_case(case_id)
update_evolution_case_score(case_id, outcome_score, label)
get_evolution_metrics()                          # 综合统计（V0.2 起含 Pattern/Candidate 计数）
```

**V0.2 新增：**

```python
create_evolution_pattern(payload)
get_evolution_pattern_by_id(pattern_id)
list_evolution_patterns(limit, offset, pattern_type, status)
count_evolution_patterns(pattern_type, status)
create_evolution_candidate(payload)
get_evolution_candidate_by_id(candidate_id)
list_evolution_candidates(limit, offset, candidate_type, status, risk_level)
count_evolution_candidates(candidate_type, status, risk_level)
```

验收：

```bash
python -m pytest tests/unit/ -v --basetemp=.pytest_tmp
```

## 6. 第二阶段：Schema 与采集器（V0.1 已完成）

### 6.1 定义内部 Schema（已完成）

文件：`server/evolution/schemas.py`

V0.1 已实现 `EvolutionFeedbackInput`，供 API 层和采集器共用：

```python
class EvolutionFeedbackInput(BaseModel):
    record_id: Optional[int]           # 诊断记录 ID
    case_id: Optional[int]             # 自进化案例 ID
    evolution_case_id: Optional[int]   # 同 case_id，兼容前端命名
    message_id: Optional[str]          # 聊天消息 ID
    feedback_type: str                 # 反馈类型，默认 "user_feedback"
    score: Optional[float]             # 评分，支持 0-100 或 0-1
    reason: str                        # 反馈原因
    accepted: Optional[bool]           # 诊断建议是否被采纳
    metric_recovery: Optional[Dict]    # 修复后指标恢复情况
    recurrence: Optional[bool]         # 同类问题是否复发
    raw_feedback: Dict[str, Any]       # 原始反馈内容
```

> **说明**：`EvolutionCaseInput` 暂不需要，采集器 `capture_diagnosis_result()` 直接接收 `anomaly_info` 和 `result` 字典，内部完成快照构建和脱敏。如未来需要对外暴露案例提交接口，可再新增此 Schema。

### 6.2 实现采集器（V0.1 已完成）

文件：`server/evolution/collector.py`

V0.1 实现了以下关键能力（比原设计骨架更完整）：

- `sanitize_snapshot(value)`：递归脱敏，自动遮蔽 password/token/api_key 等敏感字段，截断超长字符串（默认 4000 字符），处理不可序列化对象
- `build_case_fingerprint(anomaly_info, result)`：基于异常类型、描述、根因组合生成 SHA-256 指纹，用于去重和聚类
- `get_current_asset_versions()`：计算知识库文件 SHA-256 哈希，记录知识、检索策略、工具策略、提示词的版本快照
- `capture_diagnosis_result(anomaly_info, result, record_id)`：采集完整诊断快照（输入、推理轨迹、知识命中、输出、资产版本），写入 `evolution_cases`
- `capture_user_feedback(...)`：采集用户反馈，自动关联 `evolution_case`，并触发评分器更新 `outcome_score` 和 `label`

额外实现的 `reflection_insights` 字段采集支持 Tree Search 的反思步骤，以及 `quick_action_guide` 的输出快照。

### 6.3 接入诊断流程（V0.1 已完成）

修改文件：`server/diagnose/diagnose.py`

接入位置：`quick_diagnose()` 中 `_save_diagnosis_to_database(...)` 成功后。

V0.1 已实现，采集失败不影响诊断主流程，`result` 中携带 `evolution_case_id`：

```python
try:
    from server.evolution.collector import capture_diagnosis_result
    evolution_case_id = capture_diagnosis_result(
        anomaly_info=anomaly_info,
        result=result,
        record_id=result.get("record_id")
    )
    if evolution_case_id:
        result["evolution_case_id"] = evolution_case_id
        logger.info(f"自进化案例已采集，ID: {evolution_case_id}, record_id={record_id}")
except Exception as evolution_error:
    logger.warning(f"自进化案例采集失败，不影响诊断主流程: {evolution_error}")
```

### 6.4 接入反馈流程（V0.1 已完成）

修改文件：`server/chat/feedback.py`

V0.1 已实现，在原 `feedback_message_to_db()` 后追加自进化反馈写入。前端可传 `record_id`、`evolution_case_id`、`accepted` 三个扩展参数，采集失败不影响原反馈流程。

## 7. 第三阶段：评分器（V0.1 已完成）

文件：`server/evolution/evaluator.py`

输入：`EvolutionCase`（dict）、反馈（dict）、修复后指标（dict）。

输出：`{"outcome_score": float, "label": str}`。

V0.1 已完整实现五个子评分维度（与设计一致）：

```python
score = (
    0.35 * calc_root_cause_match(case, feedback)   # 根因匹配度（基于置信度）
    + 0.25 * calc_metric_recovery(case, post_metrics)  # 指标恢复度
    + 0.15 * calc_user_feedback(feedback)           # 用户反馈评分
    + 0.15 * calc_recurrence(case, feedback)        # 复发惩罚
    + 0.10 * calc_efficiency(case)                  # 诊断效率
)
```

**关键设计决策**：无反馈时直接返回 `{"outcome_score": 0.0, "label": "uncertain_case"}`，不基于模型置信度自动打高分，避免自我强化偏差。

已通过测试：

- 无反馈 → `uncertain_case`
- 高评分反馈 + 有根因 + 耗时合理 → `positive_case`（score ≥ 0.75）
- 无根因 + 负反馈 + 复发 + 超时 → `negative_case`（score ≤ 0.45）
- `metric_recovery` 支持布尔值、0-1 浮点、before/after 数值三种格式

## 8. 第四阶段：模式挖掘与候选生成（V0.2 已完成）

### 8.1 模式挖掘器（V0.2 已完成）

文件：`server/evolution/pattern_miner.py`

入口函数：`mine_patterns(min_cases=3, save=True) -> List[Dict]`

V0.2 实现了四条规则（全部不依赖机器学习，零外部依赖）：

| 规则 | 触发条件 | 输出模式 | 置信度范围 |
| --- | --- | --- | --- |
| `missing_knowledge` | 同异常类型中 knowledge_chunks_used=0 的案例 ≥ min_cases | 知识空洞 | 0.50 ~ 0.95 |
| `wrong_tool_selection` | 慢 SQL 类案例未调用 explain_query/index 工具 ≥ min_cases | 工具缺失 | 0.50 ~ 0.90 |
| `low_confidence_prompt` | 有工具调用但根因置信度 < 0.5 的案例 ≥ min_cases | 提示词缺陷 | 0.40 ~ 0.85 |
| `retrieval_weight_issue` | BM25 与向量分数差值 > 0.3 的案例 ≥ min_cases | 检索权重失衡 | 0.40 ~ 0.80 |

每条模式包含：`evidence_case_ids`、`failure_signature`、`confidence`、`suggested_update_type`。

### 8.2 候选生成器（V0.2 已完成）

文件：`server/evolution/candidate_generator.py`

入口函数：
- `generate_candidates_from_pattern(pattern, save=True) -> List[Dict]`
- `generate_all_candidates(patterns, save=True) -> List[Dict]`

每种模式对应的候选类型：

| 模式类型 | 候选类型 | 目标资产 | 风险等级 |
| --- | --- | --- | --- |
| `missing_knowledge` | `knowledge_patch` | knowledge | low |
| `wrong_tool_selection` | `tool_strategy_patch` | tool_policy | medium |
| `low_confidence_prompt` | `prompt_patch` | prompt | medium |
| `retrieval_weight_issue` | `retrieval_strategy_patch` | retrieval_policy | low |

所有候选默认 `status="pending"`，不影响线上诊断。候选的 `patch_content` 包含完整的操作描述、证据摘要和应用建议。

## 9. 第五阶段：沙盒回放、门控与版本注册

### 9.1 沙盒回放

文件：`server/evolution/replay_runner.py`

第一版建议只做离线模拟，不直接调用真实数据库优化动作。

函数签名：

```python
def replay_candidate(candidate_id: int, testcase_dir: str = "diagnostic_test_cases") -> dict:
    """在测试用例和历史案例上对比候选版本与基线版本。"""
```

输出指标：

- `baseline_accuracy`
- `candidate_accuracy`
- `top3_hit_rate`
- `avg_latency`
- `regression_cases`
- `cost_change`

### 9.2 安全门控

文件：`server/evolution/gatekeeper.py`

门控逻辑：

```python
def evaluate_gate(candidate: dict, experiment: dict) -> dict:
    pass_gate = True
    reasons = []

    if experiment["candidate_accuracy"] < experiment["baseline_accuracy"] + 0.05:
        pass_gate = False
        reasons.append("accuracy_improvement_below_threshold")

    if experiment.get("regression_cases"):
        pass_gate = False
        reasons.append("has_regression_cases")

    if candidate.get("risk_level") == "high":
        pass_gate = False
        reasons.append("high_risk_requires_manual_review")

    decision = "auto_promote" if pass_gate else "manual_review"
    return {"pass_gate": pass_gate, "decision": decision, "reasons": reasons}
```

### 9.3 版本注册

文件：`server/evolution/registry.py`

实现：

```python
def promote_candidate(candidate_id: int, approved_by: str = "system") -> dict:
    """将通过门控的候选发布为新 artifact version。"""


def rollback_artifact(artifact_type: str, target_version: str) -> dict:
    """回滚指定类型资产到目标版本。"""


def get_active_artifact_versions() -> dict:
    """返回当前诊断链路使用的知识、策略、提示词版本。"""
```

要求：

- 所有版本写入 `evolution_artifacts`。
- 每个版本保存 `content_hash`。
- 发布后只切换“当前生效版本”，不删除历史版本。

## 10. 第六阶段：API 开发

文件：`server/evolution/api.py`

### V0.1 已实现接口

| API | 方法 | 用途 | 状态 |
| --- | --- | --- | --- |
| `/evolution/cases` | GET | 查看自进化案例池（支持 label/status/anomaly_type 过滤、分页） | ✅ 已完成 |
| `/evolution/cases/{case_id}` | GET | 查看单个案例详情及其反馈列表 | ✅ 已完成 |
| `/evolution/metrics` | GET | 查看自进化收益指标（案例数、反馈数、平均评分、标签分布） | ✅ 已完成 |
| `/evolution/feedback` | POST | 提交用户反馈，自动触发评分更新 | ✅ 已完成 |

### V0.2 已实现接口

| API | 方法 | 用途 | 状态 |
| --- | --- | --- | --- |
| `/evolution/patterns` | GET | 查看挖掘出的模式列表（支持 pattern_type/status 过滤、分页） | ✅ 已完成 |
| `/evolution/candidates` | GET | 查看候选更新列表（支持 candidate_type/status/risk_level 过滤） | ✅ 已完成 |
| `/evolution/candidates/generate` | POST | 触发模式挖掘 + 候选生成，结果持久化并返回摘要 | ✅ 已完成 |

### V0.3 待实现接口

| API | 方法 | 用途 | 阶段 |
| --- | --- | --- | --- |
| `/evolution/replay/{candidate_id}` | POST | 触发候选沙盒回放 | V0.3 |
| `/evolution/promote/{candidate_id}` | POST | 发布通过门控的候选 | V0.3 |
| `/evolution/rollback/{artifact_type}/{version}` | POST | 回滚指定类型资产到历史版本 | V0.3 |

> **路由顺序提示**：固定路径必须注册在动态路径（带 `{param}` 的路由）之前，否则固定路径会被动态参数吞掉。FastAPI 按注册顺序匹配路由，已修复 `/api/testcases/statistics` 在 `/{case_id}` 之前的问题。

## 11. 第七阶段：前端开发

第一版可只通过 Swagger 验证；若做前端，建议增加 `Evolution` 页面。

页面结构：

```text
Evolution/
  index.jsx
  EvolutionOverview.jsx
  CasePoolTable.jsx
  CandidateReviewTable.jsx
  ArtifactVersionPanel.jsx
```

核心视图：

- 自进化总览：案例数、正/负/不确定案例比例、候选数、已发布版本。
- 案例池：展示 `record_id`, `anomaly_type`, `outcome_score`, `label`, `create_time`。
- 候选审批：展示候选内容、证据案例、风险等级、回放结果。
- 版本管理：展示当前资产版本，提供回滚按钮。

前端 API：

```javascript
export const evolutionAPI = {
  listCases: (params) => api.get('/evolution/cases', { params }),
  metrics: () => api.get('/evolution/metrics'),
  generateCandidates: (data) => api.post('/evolution/candidates/generate', data),
  replayCandidate: (id) => api.post(`/evolution/replay/${id}`),
  promoteCandidate: (id) => api.post(`/evolution/promote/${id}`),
  rollbackArtifact: (type, version) => api.post(`/evolution/rollback/${type}/${version}`),
}
```

## 12. 测试流程

### 12.1 单元测试（当前共 41 个，全部通过）

| 测试文件 | 测试数 | 覆盖内容 | 状态 |
| --- | --- | --- | --- |
| `test_evolution_collector.py` | 4 | sanitize_snapshot 脱敏截断、指纹稳定性、快照提取、不可序列化容错 | ✅ V0.1 |
| `test_evolution_evaluator.py` | 4 | 无反馈保持不确定、正负案例边界、metric_recovery 三种格式 | ✅ V0.1 |
| `test_evolution_api.py` | 5 | 案例列表/详情/指标/反馈、诊断集成（含 evolution_case_id） | ✅ V0.1 |
| `test_evolution_pattern_miner.py` | 18 | 四种规则的触发/不触发/边界、DB 保存、DB 异常容错 | ✅ V0.2 |
| `test_evolution_candidate_generator.py` | 10 | 四种候选生成、未知类型跳过、save=False、多模式批量 | ✅ V0.2 |
| `test_evolution_gatekeeper.py` | — | 门控规则、回归拒绝、高风险拦截 | ⬜ V0.3 待补充 |

运行全部：

```bash
python -m pytest tests/unit/ -v --basetemp=.pytest_tmp
```

### 12.2 集成测试（已通过）

`TestEvolutionDiagnosisIntegration`（在 `test_evolution_api.py` 中）：

1. Mock `run_tree_search_diagnosis()` 和 `_save_diagnosis_to_database()` 返回固定结果。
2. 调用 `/diagnose/quick`。
3. 断言返回中包含 `record_id=101` 和 `evolution_case_id=202`。

### 12.3 手动验收演示流程

启动后端：

```bash
python server/api.py --port 7861
# 或
start_backend.bat
```

访问 Swagger：`http://localhost:7861/docs`

**完整演示步骤（V0.1 + V0.2）：**

| 步骤 | 接口 | 说明 |
| --- | --- | --- |
| 1 | `POST /diagnose/quick` | 提交诊断请求，返回 `evolution_case_id` |
| 2 | `POST /evolution/feedback` | 提交负反馈（score=10, accepted=false） |
| 3 | `GET /evolution/cases` | 确认 label 更新为 `negative_case` |
| 4 | `POST /evolution/candidates/generate?min_cases=1` | 触发挖掘（min_cases=1 便于演示单案例） |
| 5 | `GET /evolution/patterns` | 查看挖掘出的模式和置信度 |
| 6 | `GET /evolution/candidates` | 查看生成的候选补丁内容 |
| 7 | `GET /evolution/metrics` | 查看完整统计（案例/反馈/模式/候选数量） |

## 13. 代码审查清单

提交前逐项检查：

- 新增模型已被 `server/db/session.py` 导入。
- 所有仓储函数使用 `@with_session`。
- 诊断主流程中的自进化调用均被 `try/except` 包裹。
- API 返回 `BaseResponse`。
- 所有候选默认 `pending`，不会自动影响线上诊断。
- 所有 JSON 字段可序列化。
- 测试不依赖真实 PostgreSQL、真实 LLM、真实 Prometheus。
- 日志中不输出敏感 SQL 字面量、密码、API Key。
- 软著和专利材料中不公开未脱敏生产数据。

## 14. 软著材料沉淀

开发过程中同步维护以下材料，避免最后倒推：

| 材料 | 建议来源 | 说明 |
| --- | --- | --- |
| 源程序鉴别材料 | `server/evolution/`, `server/db/models/evolution_model.py`, `server/db/repository/evolution_repository.py`, 前端 Evolution 页面 | 可选取自进化模块核心代码 |
| 软件设计说明书 | 本文档、方案文档、数据库设计、接口说明 | 描述模块结构、算法、流程 |
| 用户手册 | Evolution 页面操作说明、Swagger 使用说明 | 说明如何查看案例、候选、回放、发布、回滚 |
| 测试报告 | pytest 输出、手工验收记录、回放指标 | 证明软件可运行 |
| 版本说明 | V0.1 到 V1.0 changelog | 说明新增功能和完成日期 |
| 截图材料 | Swagger、前端页面、回放报告 | 辅助证明功能完整 |

软著命名建议：

```text
SunDB AI-Ops 自进化智能诊断优化软件 V1.0
```

软著功能描述建议：

```text
本软件面向数据库智能运维场景，提供诊断案例采集、用户反馈关联、诊断结果评分、失败模式挖掘、候选知识补丁生成、沙盒回放验证、安全门控发布和版本回滚等功能，用于提升数据库异常诊断系统的持续优化能力和可审计能力。
```

官方依据提示：

- 《计算机软件著作权登记办法》规定，申请软件著作权登记通常需要提交软件著作权登记申请表、软件鉴别材料和相关证明文件。
- 软件鉴别材料包括程序和文档的鉴别材料；通常由源程序和任一种文档前、后各连续 30 页组成，少于 60 页则提交全部。

## 15. 专利材料沉淀

研发过程中要保留以下证据和材料：

| 专利材料 | 研发产物 |
| --- | --- |
| 背景技术问题 | 当前诊断系统无法自动验证和发布经验更新 |
| 技术方案 | 采集、评分、挖掘、候选、回放、门控、发布、回滚闭环 |
| 数据结构 | `EvolutionCase`, `EvolutionPattern`, `EvolutionCandidate`, `EvolutionArtifact` |
| 流程图 | Mermaid 图、架构图、时序图 |
| 具体实施例 | 慢 SQL、锁等待、内存异常三类案例 |
| 技术效果 | 准确率提升、耗时降低、复发率降低、回归风险可控 |
| 对比实验 | 候选前后 Top-1/Top-3 命中率、耗时、工具调用成本 |

建议专利名称：

```text
一种基于诊断轨迹与沙盒回放门控的数据库智能运维自进化方法及系统
```

建议权利要求主线：

1. 获取数据库异常输入、诊断树推理轨迹、知识检索结果、工具调用结果和诊断输出。
2. 根据用户反馈、修复后指标恢复情况、复发情况和诊断成本计算诊断质量评分。
3. 对历史诊断案例进行聚类和成功失败对比，识别缺失知识、错误工具选择或提示词缺陷。
4. 生成带证据链的候选更新。
5. 在历史案例和测试用例中对候选更新进行沙盒回放。
6. 根据安全门控规则决定发布、复核或拒绝。
7. 将发布后的知识、策略或提示词作为版本化资产注册，并在诊断时绑定版本号以支持回滚。

专利保密要求：

- 在提交专利申请前，不建议公开完整技术交底、关键评分公式、候选生成策略和实验数据。
- 对外演示只展示功能效果，不展示完整候选生成规则。
- 代码仓库若公开，应在申请前确认公开内容不会破坏新颖性。

## 16. 完成定义

**当前状态（V0.2 完成）：**

| 完成标准 | 状态 |
| --- | --- |
| 后端存在独立 `server/evolution/` 模块 | ✅ |
| 每次 `/diagnose/quick` 成功后能生成 `evolution_case` | ✅ |
| 用户反馈能写入 `evolution_feedback` 并触发评分更新 | ✅ |
| 系统能从负/不确定案例挖掘出四种模式（带置信度和证据链） | ✅ |
| 每种模式能生成带 `patch_content` 的候选补丁记录 | ✅ |
| 所有候选默认 `pending`，不影响线上诊断 | ✅ |
| 单元测试覆盖采集器、评分器、API、模式挖掘、候选生成（共 41 个） | ✅ |

**V1.0 剩余完成标准（V0.3 + V1.0 待开发）：**

- 至少支持一次离线回放（`replay_runner.py`）和门控判断（`gatekeeper.py`）。
- 至少支持一个资产版本发布和回滚（`registry.py`）。
- 单元测试覆盖门控（`test_evolution_gatekeeper.py`）。
- 已形成软著材料包目录。
- 已形成专利交底材料初稿。

建议归档目录：

```text
materials/ip/self_evolution/
  software_copyright/
    source_code_selection/
    design_spec.md
    user_manual.md
    test_report.md
    version_description.md
  patent_disclosure/
    technical_disclosure.md
    architecture.mmd
    flowchart.mmd
    embodiments.md
    experiment_results.md
```

## 17. 参考依据

- 国家版权局《计算机软件著作权登记办法》公开文本：<https://m.mofcom.gov.cn/aarticle/bh/200311/20031100148039.html>
- 国家知识产权局公开的《中华人民共和国专利法》修法内容：<https://www.cnipa.gov.cn/art/2020/11/23/art_2197_155169.html>
