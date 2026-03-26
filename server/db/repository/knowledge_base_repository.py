from server.db.models.knowledge_base_model import KnowledgeBaseModel
from server.db.models.knowledge_file_model import KnowledgeFileModel
from server.db.session import with_session
from sqlalchemy.orm import defer
from sqlalchemy import inspect, func
import logging
import os
from server.utils import get_beijing_now_str
from server.knowledge_base.utils import get_doc_path

logging.getLogger("sqlalchemy").setLevel(logging.ERROR)

def get_kb_update_time(kb_name: str) -> str:
    """获取知识库最后更新时间（基于文件修改时间）"""
    try:
        doc_path = get_doc_path(kb_name)
        if not os.path.exists(doc_path):
            return None
        files = [os.path.join(doc_path, f) for f in os.listdir(doc_path) if os.path.isfile(os.path.join(doc_path, f))]
        if not files:
            return None
        latest_mtime = max(os.path.getmtime(f) for f in files)
        from datetime import datetime
        return datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except:
        return None

def get_existing_columns(model):
    """侦测雷达：看看数据库到底有几斤几两"""
    try:
        return [c.name for c in inspect(model).mapper.column_attrs]
    except:
        return ["id", "kb_name"]

def get_safe_query(session, cols):
    """防御盾：只查存在的列"""
    query = session.query(KnowledgeBaseModel)
    # 只要数据库里没有的，统统不许查，防止 SQL 报错
    danger_fields = ['kb_info', 'vs_type', 'embed_model', 'file_count', 'create_time']
    for field in danger_fields:
        if field not in cols:
            query = query.options(defer(getattr(KnowledgeBaseModel, field)))
    return query

@with_session
def list_kbs_from_db(session, min_file_count: int = -1):
    try:
        cols = get_existing_columns(KnowledgeBaseModel)
        kbs = get_safe_query(session, cols).all()
        
        data_list = []
        for kb in kbs:
            db_file_count = session.query(func.count(KnowledgeFileModel.id)).filter(
                KnowledgeFileModel.kb_name == kb.kb_name
            ).scalar() or 0
            
            folder_file_count = 0
            try:
                doc_path = get_doc_path(kb.kb_name)
                if os.path.exists(doc_path):
                    folder_file_count = len([f for f in os.listdir(doc_path) 
                                            if os.path.isfile(os.path.join(doc_path, f))])
            except:
                pass
            
            actual_file_count = max(db_file_count, folder_file_count)
            
            update_time = get_kb_update_time(kb.kb_name)
            
            d = {
                "kb_name": str(kb.kb_name),
                "kb_info": str(getattr(kb, 'kb_info', '')) if 'kb_info' in cols else "Space",
                "vs_type": str(getattr(kb, 'vs_type', 'chroma')) if 'vs_type' in cols else "chroma",
                "embed_model": str(getattr(kb, 'embed_model', 'm3e-base')) if 'embed_model' in cols else "m3e-base",
                "file_count": actual_file_count,
                "db_file_count": db_file_count,
                "folder_file_count": folder_file_count,
                "create_time": str(getattr(kb, 'create_time', '')) if 'create_time' in cols else get_beijing_now_str(),
                "update_time": update_time,
            }
            data_list.append(d)
        return data_list
    except Exception as e:
        print(f"UI 列表加载防御触发: {e}")
        return []

@with_session
def load_kb_from_db(session, kb_name, vs_type):
    cols = get_existing_columns(KnowledgeBaseModel)
    kb = get_safe_query(session, cols).filter_by(kb_name=kb_name).first()
    if kb:
        v_type = str(getattr(kb, 'vs_type', 'chroma')) if 'vs_type' in cols else "chroma"
        e_model = str(getattr(kb, 'embed_model', 'm3e-base')) if 'embed_model' in cols else "m3e-base"
        return kb.kb_name, v_type, e_model
    return None, None, None

@with_session
def kb_exists(session, kb_name, vs_type):
    # 只查 ID 是最稳的
    return session.query(KnowledgeBaseModel.id).filter_by(kb_name=kb_name).first() is not None

@with_session
def get_kb_detail(session, kb_name: str) -> dict:
    cols = get_existing_columns(KnowledgeBaseModel)
    kb = get_safe_query(session, cols).filter_by(kb_name=kb_name).first()
    if kb:
        return {
            "kb_name": kb.kb_name,
            "kb_info": str(getattr(kb, 'kb_info', '')) if 'kb_info' in cols else "",
            "vs_type": str(getattr(kb, 'vs_type', '')) if 'vs_type' in cols else "",
            "embed_model": str(getattr(kb, 'embed_model', '')) if 'embed_model' in cols else "",
            "file_count": int(getattr(kb, 'file_count', 0)) if 'file_count' in cols else 0,
            "create_time": str(getattr(kb, 'create_time', '')) if 'create_time' in cols else "",
        }
    return {}

@with_session
def add_kb_to_db(session, kb_name, kb_info, vs_type, embed_model):
    # 写入逻辑暂时保持简单，如果不成也不要卡死整个系统
    try:
        cols = get_existing_columns(KnowledgeBaseModel)
        params = {"kb_name": kb_name}
        if "kb_info" in cols: params["kb_info"] = kb_info
        if "vs_type" in cols: params["vs_type"] = vs_type
        if "embed_model" in cols: params["embed_model"] = embed_model
        # 添加北京时间创建时间
        if "create_time" in cols: params["create_time"] = get_beijing_now_str()
        kb = KnowledgeBaseModel(**params)
        session.add(kb)
        return True
    except:
        return False

@with_session
def delete_kb_from_db(session, kb_name):
    session.query(KnowledgeBaseModel).filter_by(kb_name=kb_name).delete()
    return True