"""
Shared test fixtures for the DB-GPT API test suite.

This conftest patches heavy module-level side effects (PostgreSQL connections,
knowledge loading, nltk, model workers, etc.) so that tests can import server
modules without requiring external services or optional dependencies.
"""
import os
import sys
import json
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# 0. Ensure the project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# 1. Session-scoped: patch heavy imports BEFORE any server code is loaded
# ---------------------------------------------------------------------------

def _make_mock_module(name):
    """Create a MagicMock that also acts as a module (has __name__, __path__)."""
    m = MagicMock()
    m.__name__ = name
    m.__path__ = []
    m.__file__ = f"<mock {name}>"
    m.__spec__ = None
    return m


@pytest.fixture(scope="session", autouse=True)
def patch_heavy_imports(tmp_path_factory):
    """
    Patch module-level side effects that happen during import:
      - psycopg2: prevent real PostgreSQL connection attempts
      - fastchat + model_workers: heavy ML deps (websockets, chardet, etc.)
      - langchain_community: optional dep not always installed
      - diagnose.py: prevent load_knowledge() from running
    """
    tmp_dir = tmp_path_factory.mktemp("test_configs")

    # ---- Env vars for configs ----
    os.environ.setdefault("PG_HOST", "127.0.0.1")
    os.environ.setdefault("PG_PORT", "5432")
    os.environ.setdefault("PG_USER", "test")
    os.environ.setdefault("PG_PASSWORD", "test")
    os.environ.setdefault("PG_DATABASE", "test_db")

    # Ensure directories expected by configs exist
    os.makedirs(str(tmp_dir / "diagnostic_files"), exist_ok=True)
    os.makedirs(str(tmp_dir / "diagnostic_results"), exist_ok=True)
    os.makedirs(str(tmp_dir / "logs"), exist_ok=True)

    # ---- psycopg2 ----
    mock_psycopg2 = MagicMock()
    mock_psycopg2.connect.side_effect = Exception("No PG in test env")
    mock_psycopg2.extensions = MagicMock()

    # ---- fastchat (required by server/model_workers/) ----
    mock_fastchat = types.ModuleType("fastchat")
    mock_fastchat.constants = types.ModuleType("fastchat.constants")
    mock_fastchat.constants.LOGDIR = str(tmp_dir / "logs")
    mock_fastchat.conversation = MagicMock()
    mock_fastchat.conversation.Conversation = MagicMock

    mock_serve = types.ModuleType("fastchat.serve")
    mock_base_worker = types.ModuleType("fastchat.serve.base_model_worker")
    mock_base_worker.BaseModelWorker = type("BaseModelWorker", (), {
        "__init__": lambda self, *a, **kw: None,
    })
    mock_base_worker.app = MagicMock()
    mock_model_worker = types.ModuleType("fastchat.serve.model_worker")
    mock_model_worker.app = MagicMock()

    # ---- Collect ALL modules to mock ----
    mocked_modules = {
        # psycopg2
        "psycopg2": mock_psycopg2,
        "psycopg2.extensions": mock_psycopg2.extensions,
        # fastchat
        "fastchat": mock_fastchat,
        "fastchat.constants": mock_fastchat.constants,
        "fastchat.conversation": mock_fastchat.conversation,
        "fastchat.serve": mock_serve,
        "fastchat.serve.base_model_worker": mock_base_worker,
        "fastchat.serve.model_worker": mock_model_worker,
    }

    # Optional deps that model workers / knowledge_base / etc. import at top level
    optional_deps = [
        "langchain",
        "langchain.agents",
        "langchain.agents.agent",
        "langchain.agents.agent_toolkits",
        "langchain.agents.structured_chat",
        "langchain.callbacks",
        "langchain.callbacks.base",
        "langchain.callbacks.manager",
        "langchain.chains",
        "langchain.chains.base",
        "langchain.chains.llm",
        "langchain.chat_models",
        "langchain.document_loaders",
        "langchain.docstore",
        "langchain.docstore.document",
        "langchain.embeddings",
        "langchain.llms",
        "langchain.memory",
        "langchain.memory.chat_memory",
        "langchain.output_parsers",
        "langchain.prompts",
        "langchain.prompts.chat",
        "langchain.pydantic_v1",
        "langchain.schema",
        "langchain.schema.language_model",
        "langchain.schema.output_parser",
        "langchain.text_splitter",
        "langchain.tools",
        "langchain.tools.arxiv",
        "langchain.tools.base",
        "langchain.utilities",
        "langchain.utilities.bing_search",
        "langchain.utilities.duckduckgo_search",
        "langchain.utilities.wolfram_alpha",
        "websockets",
        "chardet",
        "cchardet",
        "cachetools",
        "SparkApi",
        "strsimpy",
        "strsimpy.normalized_levenshtein",
        "markdownify",
        "uvicorn",
        "nltk",
    ]
    for dep in optional_deps:
        if dep not in sys.modules:
            mock_dep = _make_mock_module(dep)
            # cachetools needs `cached` (a decorator) and `TTLCache` (a class)
            if dep == "cachetools":
                mock_dep.cached = lambda cache, **kw: (lambda f: f)  # passthrough decorator
                mock_dep.TTLCache = MagicMock
            if dep == "langchain":
                mock_dep.verbose = False
            if dep == "langchain.callbacks.base":
                mock_dep.BaseCallbackHandler = type("BaseCallbackHandler", (), {})
            if dep == "langchain.memory.chat_memory":
                mock_dep.BaseChatMemory = type("BaseChatMemory", (), {"return_messages": False})
            mocked_modules[dep] = mock_dep

    # langchain_community submodules that may fail to import (missing deps)
    # Force-mock them regardless of whether langchain_community is installed,
    # because the langchain shim can fail when delegating to broken submodules.
    lc_submodules = [
        "langchain_community.document_loaders",
        "langchain_community.chat_models",
        "langchain_community.llms",
        "langchain_community.embeddings",
        "langchain_community.vectorstores",
        "langchain_community.utilities",
        "langchain_community.utilities.duckduckgo_search",
    ]
    for sub in lc_submodules:
        if sub not in sys.modules:
            mocked_modules[sub] = _make_mock_module(sub)

    patches = []
    p = patch.dict("sys.modules", mocked_modules)
    p.start()
    patches.append(p)

    yield

    for p in patches:
        p.stop()


@pytest.fixture(scope="session")
def app(patch_heavy_imports):
    """Create a FastAPI app instance for testing (session-scoped)."""
    # Patch load_knowledge before importing diagnose module
    with patch("server.diagnose.knowledge_loader.load_knowledge", return_value=None):
        with patch("server.diagnose.knowledge_loader.get_all_root_causes", return_value=[]):
            with patch("server.diagnose.knowledge_loader.match_anomaly_to_cause", return_value=None):
                # Patch tree_search_service heavy imports
                try:
                    with patch("server.diagnose.tree_search_service.run_tree_search_diagnosis", return_value={}):
                        from server.api import create_app
                        return create_app()
                except Exception:
                    # If tree_search_service import fails (missing numpy/rank_bm25),
                    # mock the entire module
                    mock_tree = MagicMock()
                    mock_tree.run_tree_search_diagnosis = MagicMock(return_value={})
                    sys.modules.setdefault("server.diagnose.tree_search_service", mock_tree)

                    # Also mock other heavy dependencies if needed
                    for mod_name in [
                        "server.diagnose.db_connector",
                        "server.diagnose.anomaly_detector",
                        "server.diagnose.scheduler_service",
                        "server.diagnose.progress_manager",
                        "server.diagnose.collaborative_executor",
                        "server.diagnose.diagnosis_enhancer",
                        "server.diagnose.consistency_checker",
                    ]:
                        if mod_name not in sys.modules:
                            sys.modules[mod_name] = MagicMock()

                    from server.api import create_app
                    return create_app()


@pytest.fixture(scope="function")
def client(app):
    """Create a new TestClient per test function."""
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 2. Function-scoped: DB mocks
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db_session():
    """Mock SessionLocal and session_scope for tests that hit the DB layer."""
    mock_session = MagicMock()
    mock_session.query.return_value = mock_session
    mock_session.filter.return_value = mock_session
    mock_session.order_by.return_value = mock_session
    mock_session.limit.return_value = mock_session
    mock_session.offset.return_value = mock_session
    mock_session.all.return_value = []
    mock_session.first.return_value = None
    mock_session.count.return_value = 0
    mock_session.commit.return_value = None
    mock_session.rollback.return_value = None
    mock_session.close.return_value = None

    return mock_session


@pytest.fixture
def mock_pg_connection():
    """Mock get_pg_connection() for raw psycopg2 usage."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_cursor.fetchone.return_value = None
    mock_cursor.description = []
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn


@pytest.fixture
def mock_subprocess(monkeypatch):
    """Mock subprocess.run and subprocess.Popen."""
    mock_run = MagicMock()
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="success",
        stderr="",
    )
    mock_popen = MagicMock()
    mock_popen.return_value = MagicMock(
        pid=12345,
        wait=MagicMock(return_value=0),
        communicate=MagicMock(return_value=("output", "")),
    )
    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("subprocess.Popen", mock_popen)
    return mock_run, mock_popen


@pytest.fixture
def mock_diagnosis_repos():
    """Mock diagnosis record/report repository functions."""
    return {
        "list_diagnosis_records": MagicMock(return_value=[]),
        "count_diagnosis_records": MagicMock(return_value=0),
        "get_diagnosis_record": MagicMock(return_value=None),
        "delete_diagnosis_record": MagicMock(return_value=True),
        "get_report_by_record_id": MagicMock(return_value=None),
        "delete_diagnosis_report_by_record_id": MagicMock(return_value=True),
    }


@pytest.fixture
def mock_detector_and_scheduler():
    """Mock get_detector() and get_scheduler() singletons."""
    mock_detector = MagicMock()
    mock_detector.get_state.return_value = {"running": False, "alerts": 0}
    mock_detector.get_alert_history.return_value = []
    mock_detector.clear_alert_history.return_value = None
    mock_detector.thresholds = {"cpu": 80, "memory": 85}
    mock_detector.update_thresholds.return_value = None

    mock_scheduler = MagicMock()
    mock_scheduler.get_status.return_value = {"running": False, "jobs": []}
    mock_scheduler.set_auto_diagnosis.return_value = None
    mock_scheduler.start.return_value = None
    mock_scheduler.stop.return_value = None
    mock_scheduler.resume_monitoring.return_value = True
    mock_scheduler.pause_monitoring.return_value = True
    mock_scheduler.is_monitoring_active.return_value = True
    mock_scheduler._auto_diagnosis_enabled = False

    return mock_detector, mock_scheduler
