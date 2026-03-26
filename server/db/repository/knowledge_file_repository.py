from server.db.models.knowledge_base_model import KnowledgeBaseModel
from server.db.models.knowledge_file_model import KnowledgeFileModel, FileDocModel
from server.db.session import with_session
from server.knowledge_base.utils import KnowledgeFile
from sqlalchemy.orm import defer
from sqlalchemy import inspect
from typing import List, Dict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def get_existing_columns(model):
    """【侦测雷达】获取模型在数据库中实际存在的列名，失败时优雅回退"""
    try:
        return [c.name for c in inspect(model).mapper.column_attrs]
    except Exception as e:
        logger.debug(f"探测表结构跳过缺失字段: {e}")
        return []

def safe_apply_defer(query, model, possible_fields):
    """【防御盾】自动排除数据库中不存在的字段，防止执行 SQL 时崩溃"""
    existing = get_existing_columns(model)
    for field in possible_fields:
        if field not in existing:
            query = query.options(defer(getattr(model, field)))
    return query, existing

@with_session
def list_docs_from_db(session, kb_name: str, file_name: str = None, metadata: Dict = {}) -> List[Dict]:
    query = session.query(FileDocModel).filter_by(kb_name=kb_name)
    danger_fields = ['doc_id', 'meta_data', 'create_time']
    query, cols = safe_apply_defer(query, FileDocModel, danger_fields)

    if file_name:
        query = query.filter(FileDocModel.file_name.ilike(file_name))
    
    if "meta_data" in cols:
        for k, v in metadata.items():
            query = query.filter(FileDocModel.meta_data[k].as_string() == str(v))

    results = []
    for x in query.all():
        results.append({
            "id": x.__dict__.get("doc_id", ""),
            "metadata": x.__dict__.get("meta_data", {})
        })
    return results

def _delete_docs_from_db_internal(session, kb_name: str, file_name: str = None) -> List[Dict]:
    """内部函数：直接使用现有 session 删除文档，避免嵌套 @with_session"""
    query = session.query(FileDocModel).filter_by(kb_name=kb_name)
    if file_name:
        query = query.filter_by(file_name=file_name)
    query.delete()
    return True

@with_session
def delete_docs_from_db(session, kb_name: str, file_name: str = None) -> List[Dict]:
    query = session.query(FileDocModel).filter_by(kb_name=kb_name)
    if file_name:
        query = query.filter_by(file_name=file_name)
    query.delete()
    return True

@with_session
def add_docs_to_db(session, kb_name: str, file_name: str, doc_infos: List[Dict]):
    if not doc_infos:
        return False
    
    cols = get_existing_columns(FileDocModel)
    for d in doc_infos:
        params = {"kb_name": kb_name, "file_name": file_name}
        if "doc_id" in cols: params["doc_id"] = d.get("id")
        if "meta_data" in cols: params["meta_data"] = d.get("metadata")
        
        obj = FileDocModel(**params)
        session.add(obj)
    return True

@with_session
def count_files_from_db(session, kb_name: str) -> int:
    return session.query(KnowledgeFileModel).filter_by(kb_name=kb_name).count()

@with_session
def list_files_from_db(session, kb_name):
    files = session.query(KnowledgeFileModel.file_name).filter_by(kb_name=kb_name).all()
    return [f[0] for f in files]

def _add_docs_to_db_internal(session, kb_name: str, file_name: str, doc_infos: List[Dict]):
    """内部函数：直接使用现有 session 添加文档，避免嵌套 @with_session 导致的死锁"""
    if not doc_infos:
        return False
    
    cols = get_existing_columns(FileDocModel)
    for d in doc_infos:
        params = {"kb_name": kb_name, "file_name": file_name}
        if "doc_id" in cols: params["doc_id"] = d.get("id")
        if "meta_data" in cols: params["meta_data"] = d.get("metadata")
        
        obj = FileDocModel(**params)
        session.add(obj)
    return True

@with_session
def add_file_to_db(session, kb_file: KnowledgeFile, docs_count: int = 0, 
                    custom_docs: bool = False, doc_infos: List[Dict] = []):
    kb = session.query(KnowledgeBaseModel).filter_by(kb_name=kb_file.kb_name).first()
    kb_cols = get_existing_columns(KnowledgeBaseModel)
    file_cols = get_existing_columns(KnowledgeFileModel)
    
    existing_file = session.query(KnowledgeFileModel).filter_by(
        file_name=kb_file.filename, kb_name=kb_file.kb_name).first()

    mtime = kb_file.get_mtime()
    size = kb_file.get_size()

    if existing_file:
        if "file_mtime" in file_cols: existing_file.file_mtime = mtime
        if "file_size" in file_cols: existing_file.file_size = size
        if "docs_count" in file_cols: existing_file.docs_count = docs_count
        if "custom_docs" in file_cols: existing_file.custom_docs = custom_docs
        if "file_version" in file_cols: existing_file.file_version = existing_file.__dict__.get("file_version", 0) + 1
    else:
        params = {"file_name": kb_file.filename, "kb_name": kb_file.kb_name}
        if "file_ext" in file_cols: params["file_ext"] = kb_file.ext
        if "document_loader_name" in file_cols: params["document_loader_name"] = kb_file.document_loader_name
        if "text_splitter_name" in file_cols: params["text_splitter_name"] = kb_file.text_splitter_name or "SpacyTextSplitter"
        if "file_mtime" in file_cols: params["file_mtime"] = mtime
        if "file_size" in file_cols: params["file_size"] = size
        if "docs_count" in file_cols: params["docs_count"] = docs_count
        if "custom_docs" in file_cols: params["custom_docs"] = custom_docs
        
        new_file = KnowledgeFileModel(**params)
        session.add(new_file)
        if kb and "file_count" in kb_cols:
            kb.file_count = kb.__dict__.get("file_count", 0) + 1

    # 使用内部函数避免嵌套 @with_session 导致的死锁
    _add_docs_to_db_internal(session, kb_name=kb_file.kb_name, file_name=kb_file.filename, doc_infos=doc_infos)
    return True

@with_session
def delete_file_from_db(session, kb_file: KnowledgeFile):
    existing_file = session.query(KnowledgeFileModel).filter_by(
        file_name=kb_file.filename, kb_name=kb_file.kb_name).first()
    
    if existing_file:
        session.delete(existing_file)
        # 使用内部函数避免嵌套 @with_session 导致的死锁
        _delete_docs_from_db_internal(session, kb_name=kb_file.kb_name, file_name=kb_file.filename)
        
        kb = session.query(KnowledgeBaseModel).filter_by(kb_name=kb_file.kb_name).first()
        if kb and "file_count" in get_existing_columns(KnowledgeBaseModel):
            kb.file_count = max(0, kb.__dict__.get("file_count", 0) - 1)
    return True

@with_session
def delete_files_from_db(session, knowledge_base_name: str):
    session.query(KnowledgeFileModel).filter_by(kb_name=knowledge_base_name).delete()
    session.query(FileDocModel).filter_by(kb_name=knowledge_base_name).delete()
    
    kb = session.query(KnowledgeBaseModel).filter_by(kb_name=knowledge_base_name).first()
    if kb and "file_count" in get_existing_columns(KnowledgeBaseModel):
        kb.file_count = 0
    return True

@with_session
def file_exists_in_db(session, kb_file: KnowledgeFile):
    return session.query(KnowledgeFileModel.id).filter_by(
        file_name=kb_file.filename, kb_name=kb_file.kb_name).first() is not None

@with_session
def get_file_detail(session, kb_name: str, filename: str) -> dict:
    """最终版：禁止任何 getattr 操作，直接读取内存 __dict__ 绕过 Lazy Loading"""
    from datetime import datetime
    
    query = session.query(KnowledgeFileModel).filter_by(file_name=filename, kb_name=kb_name)
    danger_fields = [
        'file_ext', 'file_version', 'document_loader_name', 'text_splitter_name',
        'create_time', 'file_mtime', 'file_size', 'custom_docs', 'docs_count'
    ]
    query, cols = safe_apply_defer(query, KnowledgeFileModel, danger_fields)
    file = query.first()

    if file:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 核心：使用 __dict__.get 避开 SQLAlchemy 的魔法方法
        d = file.__dict__
        
        return {
            "kb_name": str(file.kb_name),
            "file_name": str(file.file_name),
            "file_ext": str(d.get("file_ext") or ".txt"),
            "file_version": int(d.get("file_version") or 1),
            "document_loader": str(d.get("document_loader_name") or "Unknow"),
            "text_splitter": str(d.get("text_splitter_name") or "SpacyTextSplitter"),
            "create_time": str(d.get("create_time") or now_str),
            "file_mtime": float(d.get("file_mtime") or 0.0),
            "file_size": int(d.get("file_size") or 0),
            "custom_docs": bool(d.get("custom_docs", False)),
            "docs_count": int(d.get("docs_count") or 0),
        }
    return {}