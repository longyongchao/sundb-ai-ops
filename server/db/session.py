import os
from functools import wraps
from contextlib import contextmanager
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session

# ========================================================
# [START] 数据库连接配置（自动检测 PostgreSQL / SQLite）
# ========================================================
PG_URL = "postgresql://postgres:123456@127.0.0.1:5432/dbgpt_metadata"
_USE_PG = False

try:
    import psycopg2
    conn = psycopg2.connect(host="127.0.0.1", port=5432, user="postgres",
                            password="123456", dbname="dbgpt_metadata", connect_timeout=2)
    conn.close()
    _USE_PG = True
    print("[OK] [DB-INIT] PostgreSQL 连接成功")
except Exception:
    _USE_PG = False
    print("[INFO] [DB-INIT] PostgreSQL 不可用，使用 SQLite 作为元数据库")

if _USE_PG:
    import psycopg2.extensions
    # OID 映射修复
    try:
        import sqlalchemy.dialects.postgresql as pg_dialect
        target_modules = []
        if hasattr(pg_dialect, 'psycopg2'):
            target_modules.append(pg_dialect.psycopg2)
        if hasattr(pg_dialect, 'base'):
            target_modules.append(pg_dialect.base)
        for mod in target_modules:
            if hasattr(mod, 'PGDialect_psycopg2'):
                dialect_cls = getattr(mod, 'PGDialect_psycopg2')
                if not hasattr(dialect_cls, 'dbapi_type_map'):
                    dialect_cls.dbapi_type_map = {}
                dialect_cls.dbapi_type_map[1043] = pg_dialect.base.VARCHAR
                dialect_cls.dbapi_type_map[1015] = pg_dialect.base.VARCHAR
        DEC_1043 = psycopg2.extensions.new_type((1043,), "VARCHAR", psycopg2.extensions.UNICODE)
        psycopg2.extensions.register_type(DEC_1043)
    except Exception:
        pass

    engine = create_engine(
        PG_URL,
        pool_pre_ping=True,
        echo=False,
        connect_args={"client_encoding": "utf8"}
    )

    @event.listens_for(engine, "connect")
    def connect(dbapi_connection, connection_record):
        psycopg2.extensions.register_type(psycopg2.extensions.UNICODE, dbapi_connection)
else:
    _SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dbgpt_metadata.db")
    _SQLITE_URL = f"sqlite:///{_SQLITE_PATH}"
    engine = create_engine(_SQLITE_URL, pool_pre_ping=True, echo=False)

# 自动建表 - 需要先导入所有模型类使其注册到 Base.metadata
from server.db.base import Base
from server.db.models.user_model import UserModel
from server.db.models.knowledge_base_model import KnowledgeBaseModel
from server.db.models.knowledge_file_model import KnowledgeFileModel, FileDocModel
from server.db.models.conversation_model import ConversationModel
from server.db.models.chat_history_model import ChatHistoryModel
from server.db.models.knowledge_metadata_model import SummaryChunkModel
from server.db.models.message_model import MessageModel
try:
    from server.db.models.diagnosis_model import (
        DiagnosisRecord, DiagnosisReport, DiagnosisTool,
        TestAnomalyCase, MonitoringHistory, AlertHistory, Notification
    )
except Exception:
    pass
Base.metadata.create_all(bind=engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def session_scope() -> Session:
    session = SessionLocal()
    # --- 数据库自动对齐补丁 (保持之前的 patches 逻辑) ---
    try:
        patches = [
            "ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS kb_info VARCHAR(255);",
            "ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS vs_type VARCHAR(50);",
            "ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS embed_model VARCHAR(100);",
            "ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS file_count INTEGER DEFAULT 0;",
            "ALTER TABLE knowledge_file ADD COLUMN IF NOT EXISTS document_loader_name VARCHAR(100);",
            "ALTER TABLE knowledge_file ADD COLUMN IF NOT EXISTS text_splitter_name VARCHAR(100);",
            "ALTER TABLE knowledge_file ADD COLUMN IF NOT EXISTS file_version INTEGER DEFAULT 1;",
            "ALTER TABLE knowledge_file ADD COLUMN IF NOT EXISTS file_mtime VARCHAR(50);",
            "ALTER TABLE knowledge_file ADD COLUMN IF NOT EXISTS file_size INTEGER DEFAULT 0;",
            "ALTER TABLE knowledge_file ADD COLUMN IF NOT EXISTS custom_docs BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE knowledge_file ADD COLUMN IF NOT EXISTS docs_count INTEGER DEFAULT 0;",
            "CREATE TABLE IF NOT EXISTS file_doc (id SERIAL PRIMARY KEY, kb_name VARCHAR(255), file_name VARCHAR(255), doc_id VARCHAR(255));"
        ]
        for sql in patches:
            try:
                session.execute(text(sql))
            except:
                pass 
        session.commit()
    except Exception as e:
        session.rollback()
    
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        if "unique" in str(e).lower() or "already exists" in str(e).lower():
            pass
        else:
            raise e
    finally:
        session.close()

def with_session(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        with session_scope() as session:
            return f(session, *args, **kwargs)
    return wrapper

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db0() -> Session:
    return SessionLocal()
