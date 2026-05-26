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

| 版本 | 目标 | 可登记/可演示材料 |
| --- | --- | --- |
| V0.1 | 诊断案例采集、反馈关联 | 源码、接口说明、数据结构 |
| V0.2 | 评分器、模式挖掘、候选生成 | 算法说明、测试报告 |
| V0.3 | 沙盒回放、安全门控、版本注册 | 回放报告、流程图 |
| V1.0 | 前端页面、完整闭环演示、文档归档 | 软著材料、专利交底书 |

## 4. 目标目录结构

新增后端目录：

```text
server/evolution/
  __init__.py
  schemas.py
  collector.py
  evaluator.py
  pattern_miner.py
  candidate_generator.py
  replay_runner.py
  gatekeeper.py
  registry.py
  api.py
```

新增数据库文件：

```text
server/db/models/evolution_model.py
server/db/repository/evolution_repository.py
```

新增测试：

```text
tests/unit/test_evolution_collector.py
tests/unit/test_evolution_evaluator.py
tests/unit/test_evolution_api.py
tests/unit/test_evolution_gatekeeper.py
```

可选前端：

```text
webui-react/src/pages/Evolution/
webui-react/src/api/evolution.js
```

## 5. 第一阶段：数据模型与仓储层

### 5.1 新增 SQLAlchemy 模型

文件：`server/db/models/evolution_model.py`

建议定义六张表：

- `EvolutionCase`
- `EvolutionFeedback`
- `EvolutionPattern`
- `EvolutionCandidate`
- `EvolutionExperiment`
- `EvolutionArtifact`

字段骨架：

```python
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from server.db.base import Base


class EvolutionCase(Base):
    __tablename__ = "evolution_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(Integer, ForeignKey("diagnosis_records.id"), nullable=True, index=True)
    diagnosis_id = Column(String(100), nullable=True, index=True)
    case_fingerprint = Column(String(128), nullable=False, index=True)
    anomaly_type = Column(String(100), nullable=True, index=True)
    input_snapshot = Column(JSON, nullable=True)
    trace_snapshot = Column(JSON, nullable=True)
    knowledge_snapshot = Column(JSON, nullable=True)
    output_snapshot = Column(JSON, nullable=True)
    asset_versions = Column(JSON, nullable=True)
    outcome_score = Column(Float, default=0.0)
    label = Column(String(32), default="uncertain_case")
    status = Column(String(32), default="captured")
    create_time = Column(DateTime, default=datetime.now)
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)
```

其他表建议字段：

```text
evolution_feedback:
  id, case_id, record_id, feedback_type, score, reason, accepted,
  metric_recovery, recurrence, raw_feedback, create_time

evolution_patterns:
  id, pattern_type, cluster_key, evidence_case_ids, failure_signature,
  suggested_update_type, confidence, status, create_time

evolution_candidates:
  id, candidate_type, source_pattern_id, patch_content, expected_benefit,
  risk_level, status, evidence_case_ids, base_artifact_version,
  target_artifact_type, create_time, update_time

evolution_experiments:
  id, candidate_id, baseline_metrics, candidate_metrics, regression_cases,
  pass_gate, report, create_time

evolution_artifacts:
  id, artifact_type, version, content_hash, content_snapshot,
  rollback_to, active, promoted_by_candidate_id, create_time
```

### 5.2 注册模型

修改文件：`server/db/session.py`

在已有诊断模型导入后增加：

```python
try:
    from server.db.models.evolution_model import (
        EvolutionCase, EvolutionFeedback, EvolutionPattern,
        EvolutionCandidate, EvolutionExperiment, EvolutionArtifact
    )
except Exception:
    pass
```

项目当前使用 `Base.metadata.create_all(bind=engine)` 自动建表，因此第一阶段可以不引入 Alembic。若后续进入生产，建议补充正式迁移脚本。

### 5.3 新增仓储层

文件：`server/db/repository/evolution_repository.py`

至少实现：

```python
from typing import Dict, List, Optional
from server.db.session import with_session
from server.db.models.evolution_model import EvolutionCase, EvolutionFeedback


@with_session
def create_evolution_case(session, payload: Dict) -> Optional[int]:
    case = EvolutionCase(**payload)
    session.add(case)
    session.flush()
    return case.id


@with_session
def get_evolution_case_by_record_id(session, record_id: int) -> Optional[Dict]:
    case = session.query(EvolutionCase).filter_by(record_id=record_id).first()
    return case.to_dict() if case else None


@with_session
def list_evolution_cases(session, limit: int = 20, offset: int = 0, label: str = None) -> List[Dict]:
    query = session.query(EvolutionCase)
    if label:
        query = query.filter_by(label=label)
    rows = query.order_by(EvolutionCase.create_time.desc()).offset(offset).limit(limit).all()
    return [row.to_dict() for row in rows]


@with_session
def create_evolution_feedback(session, payload: Dict) -> Optional[int]:
    feedback = EvolutionFeedback(**payload)
    session.add(feedback)
    session.flush()
    return feedback.id
```

验收：

- `python -m pytest tests/unit/test_evolution_collector.py`
- 启动服务时不会因为新模型导入失败影响原 API。

## 6. 第二阶段：Schema 与采集器

### 6.1 定义内部 Schema

文件：`server/evolution/schemas.py`

建议使用 Pydantic，方便 API 和内部函数共享：

```python
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvolutionCaseInput(BaseModel):
    record_id: Optional[int] = None
    diagnosis_id: Optional[str] = None
    anomaly_info: Dict[str, Any] = Field(default_factory=dict)
    diagnosis_result: Dict[str, Any] = Field(default_factory=dict)
    asset_versions: Dict[str, str] = Field(default_factory=dict)


class EvolutionFeedbackInput(BaseModel):
    record_id: Optional[int] = None
    case_id: Optional[int] = None
    feedback_type: str = "user_feedback"
    score: Optional[float] = None
    reason: str = ""
    accepted: Optional[bool] = None
    raw_feedback: Dict[str, Any] = Field(default_factory=dict)
```

### 6.2 实现采集器

文件：`server/evolution/collector.py`

核心函数：

```python
import hashlib
import json
from typing import Dict, Any
from server.db.repository.evolution_repository import create_evolution_case


def build_case_fingerprint(anomaly_info: Dict[str, Any], result: Dict[str, Any]) -> str:
    seed = {
        "alert_type": anomaly_info.get("alert_type"),
        "description": anomaly_info.get("description"),
        "root_causes": [rc.get("type") for rc in result.get("root_causes", [])],
    }
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def capture_diagnosis_result(anomaly_info: Dict[str, Any], result: Dict[str, Any], record_id: int = None) -> int:
    search_stats = result.get("search_stats", {})
    reasoning_steps = result.get("reasoning_steps", [])
    retrieved_knowledge = result.get("retrieved_knowledge", [])

    payload = {
        "record_id": record_id or result.get("record_id"),
        "diagnosis_id": anomaly_info.get("diagnosis_id"),
        "case_fingerprint": build_case_fingerprint(anomaly_info, result),
        "anomaly_type": anomaly_info.get("alert_type") or result.get("anomaly_type"),
        "input_snapshot": anomaly_info,
        "trace_snapshot": {
            "reasoning_steps": reasoning_steps,
            "search_stats": search_stats,
            "tool_match_scores": result.get("tool_match_scores", []),
        },
        "knowledge_snapshot": {
            "retrieved_knowledge": retrieved_knowledge,
            "knowledge_chunks_used": search_stats.get("knowledge_matches", 0),
        },
        "output_snapshot": {
            "root_causes": result.get("root_causes", []),
            "solutions": result.get("solutions", []),
            "confidence": result.get("confidence", 0.0),
            "diagnosis_time": result.get("diagnosis_time", 0.0),
        },
        "asset_versions": get_current_asset_versions(),
        "status": "captured",
    }
    return create_evolution_case(payload)


def get_current_asset_versions() -> Dict[str, str]:
    return {
        "knowledge": "builtin-current",
        "retrieval_policy": "default",
        "tool_policy": "default",
        "prompt": "default",
    }
```

### 6.3 接入诊断流程

修改文件：`server/diagnose/diagnose.py`

接入位置：`quick_diagnose()` 中 `_save_diagnosis_to_database(...)` 成功后。

建议补丁逻辑：

```python
try:
    from server.evolution.collector import capture_diagnosis_result
    evolution_case_id = capture_diagnosis_result(
        anomaly_info=anomaly_info,
        result=result,
        record_id=result.get("record_id")
    )
    result["evolution_case_id"] = evolution_case_id
except Exception as evolution_error:
    logger.warning(f"自进化案例采集失败，不影响诊断主流程: {evolution_error}")
```

要求：

- 采集失败不能导致诊断失败。
- `result` 中返回 `evolution_case_id`，方便前端和反馈关联。
- `record_id` 和 `evolution_case_id` 均写入日志。

### 6.4 接入反馈流程

修改文件：`server/chat/feedback.py`

保留原 `feedback_message_to_db()`，追加自进化反馈写入：

```python
try:
    from server.evolution.collector import capture_user_feedback
    capture_user_feedback(
        message_id=message_id,
        score=score,
        reason=reason,
        raw_feedback={"message_id": message_id, "score": score, "reason": reason},
    )
except Exception as evolution_error:
    logger.warning(f"自进化反馈采集失败: {evolution_error}")
```

如果前端能传 `record_id` 或 `evolution_case_id`，优先扩展接口参数；否则第一阶段可以只落 `message_id`，后续通过诊断结果关联。

## 7. 第三阶段：评分器

文件：`server/evolution/evaluator.py`

输入：`EvolutionCase`、反馈、修复后指标。

输出：`outcome_score` 和 `label`。

代码骨架：

```python
def calculate_outcome_score(case: dict, feedback: dict = None, post_metrics: dict = None) -> dict:
    root_cause_match_score = calc_root_cause_match(case, feedback)
    metric_recovery_score = calc_metric_recovery(case, post_metrics)
    user_feedback_score = calc_user_feedback(feedback)
    recurrence_penalty_score = calc_recurrence(case)
    efficiency_score = calc_efficiency(case)

    score = (
        0.35 * root_cause_match_score +
        0.25 * metric_recovery_score +
        0.15 * user_feedback_score +
        0.15 * recurrence_penalty_score +
        0.10 * efficiency_score
    )

    if score >= 0.75:
        label = "positive_case"
    elif score <= 0.45:
        label = "negative_case"
    else:
        label = "uncertain_case"

    return {"outcome_score": round(score, 4), "label": label}
```

测试重点：

- 无反馈时不会报错，进入 `uncertain_case`。
- 高评分反馈 + 有根因 + 耗时合理时进入 `positive_case`。
- 低置信、无根因、负反馈时进入 `negative_case`。

## 8. 第四阶段：模式挖掘与候选生成

### 8.1 模式挖掘器

文件：`server/evolution/pattern_miner.py`

函数签名：

```python
def mine_patterns(start_time=None, end_time=None, min_cases: int = 3) -> list[dict]:
    """从 evolution_cases 中挖掘缺失知识、错误工具选择、提示词缺陷等模式。"""
```

第一版不需要复杂机器学习，先做规则挖掘：

| 模式 | 触发条件 | 输出 |
| --- | --- | --- |
| `missing_knowledge` | 同异常簇低分案例 >= 3 且 `knowledge_chunks_used == 0` | 生成知识补丁候选 |
| `wrong_tool_selection` | 慢 SQL 案例未调用 `explain_query` 或索引工具 | 生成工具策略候选 |
| `low_confidence_prompt` | 有工具证据但根因置信度持续低 | 生成提示词补丁候选 |
| `retrieval_weight_issue` | BM25 命中低、向量命中高，或反之 | 生成检索策略候选 |

### 8.2 候选生成器

文件：`server/evolution/candidate_generator.py`

函数签名：

```python
def generate_candidates_from_pattern(pattern: dict) -> list[dict]:
    """根据模式生成知识、检索、工具或提示词候选补丁。"""
```

候选内容格式：

```json
{
  "candidate_type": "knowledge_patch",
  "target_artifact_type": "knowledge",
  "risk_level": "low",
  "patch_content": {
    "operation": "add",
    "knowledge_block": {
      "cause_name": "missing_index_slow_query",
      "description": "当慢 SQL 扫描大量行且过滤列无索引时，优先检查缺失索引。",
      "metrics": ["slow_query_time", "rows_scanned", "idx_scan"],
      "steps": ["检查执行计划", "确认过滤列", "评估候选索引"]
    }
  },
  "evidence_case_ids": [101, 118, 132]
}
```

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

接口函数：

```python
from server.utils import BaseResponse


def list_evolution_cases(limit: int = 20, offset: int = 0, label: str = None):
    ...


def get_evolution_metrics():
    ...


def generate_evolution_candidates(start_time: str = None, end_time: str = None):
    ...


def replay_evolution_candidate(candidate_id: int):
    ...


def promote_evolution_candidate(candidate_id: int):
    ...


def rollback_evolution_artifact(artifact_type: str, version: str):
    ...
```

修改文件：`server/api.py`

新增挂载函数：

```python
def mount_evolution_routes(app: FastAPI):
    try:
        from server.evolution.api import (
            list_evolution_cases, get_evolution_metrics,
            generate_evolution_candidates, replay_evolution_candidate,
            promote_evolution_candidate, rollback_evolution_artifact,
        )
        app.get("/evolution/cases", tags=["Evolution"])(list_evolution_cases)
        app.get("/evolution/metrics", tags=["Evolution"])(get_evolution_metrics)
        app.post("/evolution/candidates/generate", tags=["Evolution"])(generate_evolution_candidates)
        app.post("/evolution/replay/{candidate_id}", tags=["Evolution"])(replay_evolution_candidate)
        app.post("/evolution/promote/{candidate_id}", tags=["Evolution"])(promote_evolution_candidate)
        app.post("/evolution/rollback/{artifact_type}/{version}", tags=["Evolution"])(rollback_evolution_artifact)
    except Exception as e:
        logger.warning(f"Failed to mount evolution routes: {e}")
```

在 `mount_app_routes()` 中追加：

```python
mount_evolution_routes(app)
```

注意路由顺序：固定路径要放在动态路径前，避免类似 `/api/testcases/statistics` 被动态参数吞掉的问题。

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

### 12.1 单元测试

建议测试文件：

```text
tests/unit/test_evolution_collector.py
tests/unit/test_evolution_evaluator.py
tests/unit/test_evolution_api.py
tests/unit/test_evolution_gatekeeper.py
```

测试重点：

- 采集器能从诊断结果中抽取 `reasoning_steps`、`root_causes`、`solutions`。
- 空字段不会导致采集失败。
- 评分公式边界值正确。
- 候选门控对准确率回退、高风险候选、回归案例能正确拒绝。
- API 返回 `BaseResponse` 风格：`code`, `msg`, `data`。

运行：

```bash
python -m pytest tests/unit/test_evolution_collector.py
python -m pytest tests/unit/test_evolution_evaluator.py
python -m pytest tests/unit/test_evolution_api.py
```

### 12.2 集成测试

建议场景：

1. Mock `run_tree_search_diagnosis()` 返回固定诊断结果。
2. 调用 `/diagnose/quick`。
3. 确认返回中包含 `record_id` 和 `evolution_case_id`。
4. 调用 `/evolution/cases` 能看到该案例。
5. 调用 `/evolution/candidates/generate` 能生成候选。

### 12.3 手动验收

启动后端：

```bash
python run_server.py
```

访问：

```text
http://localhost:7861/docs
```

手动检查：

- `/diagnose/quick`
- `/evolution/cases`
- `/evolution/metrics`
- `/evolution/candidates/generate`
- `/evolution/replay/{candidate_id}`

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

V1.0 完成标准：

- 后端存在独立 `server/evolution/` 模块。
- 每次 `/diagnose/quick` 成功后能生成 `evolution_case`。
- 用户反馈能写入 `evolution_feedback`。
- 系统能生成至少一种候选补丁：建议从 `knowledge_patch` 开始。
- 至少支持一次离线回放和门控判断。
- 至少支持一个资产版本发布和回滚。
- 单元测试覆盖采集器、评分器、API、门控。
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
