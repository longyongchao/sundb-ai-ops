import os
import urllib
import json
from fastapi import File, Form, Body, Query, UploadFile
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field, Json
from typing import List, Dict, Any, Optional

from configs import (EMBEDDING_MODEL,
                     VECTOR_SEARCH_TOP_K, SCORE_THRESHOLD,
                     CHUNK_SIZE, OVERLAP_SIZE, ZH_TITLE_ENHANCE,
                     logger, log_verbose, DEFAULT_VS_TYPES)
from server.utils import BaseResponse, ListResponse, run_in_thread_pool
from server.knowledge_base.utils import (validate_kb_name, list_files_from_folder, get_file_path,
                                         files2docs_in_thread, KnowledgeFile)
from server.knowledge_base.kb_service.base import get_kb_details, KBServiceFactory, get_kb_file_details
from server.db.repository.knowledge_file_repository import get_file_detail
from langchain.docstore.document import Document

# --- 数据模型 ---
class DocumentWithScore(Document):
    score: float = None
    kb_name: str = None

# --- 接口实现 ---

def api_search_docs(
        query: str = Body(..., description="用户输入", examples=["你好"]),
        knowledge_base_name: str = Body(..., description="知识库名称", examples=["samples"]),
        top_k: int = Body(VECTOR_SEARCH_TOP_K, description="匹配向量数"),
        score_threshold: float = Body(SCORE_THRESHOLD, ge=0, le=1),
) -> BaseResponse:
    data = search_docs(query, knowledge_base_name, top_k, score_threshold)
    serialized_data = [doc.dict() if hasattr(doc, "dict") else doc for doc in data]
    return BaseResponse(code=200, msg="Success", data=serialized_data)


def api_search_all_docs(
        query: str = Body(..., description="用户输入", examples=["你好"]),
        top_k: int = Body(VECTOR_SEARCH_TOP_K, description="每个知识库匹配向量数"),
        score_threshold: float = Body(SCORE_THRESHOLD, ge=0, le=1),
) -> BaseResponse:
    """
    全库检索：遍历所有知识库进行联合检索
    返回所有知识库中匹配度最高的文档
    """
    from server.db.repository.knowledge_base_repository import list_kbs_from_db
    
    all_results = []
    kb_list = list_kbs_from_db()
    
    for kb_info in kb_list:
        kb_name = kb_info.get("kb_name")
        if not kb_name:
            continue
        
        try:
            docs = search_docs(query, kb_name, top_k, score_threshold)
            for doc in docs:
                doc.kb_name = kb_name
                if doc.metadata:
                    doc.metadata["kb_name"] = kb_name
                else:
                    doc.metadata = {"kb_name": kb_name}
            all_results.extend(docs)
        except Exception as e:
            logger.warning(f"检索知识库 {kb_name} 时出错: {e}")
            continue
    
    all_results.sort(key=lambda x: x.score if x.score else 0, reverse=True)
    
    top_results = all_results[:top_k * 3]
    
    serialized_data = []
    for doc in top_results:
        doc_dict = doc.dict() if hasattr(doc, "dict") else {"page_content": str(doc), "score": 0}
        doc_dict["kb_name"] = getattr(doc, "kb_name", doc_dict.get("metadata", {}).get("kb_name", "未知"))
        serialized_data.append(doc_dict)
    
    return BaseResponse(
        code=200, 
        msg="Success", 
        data=serialized_data,
        total_count=len(all_results)
    )


def search_docs(query, knowledge_base_name, top_k, score_threshold) -> List[DocumentWithScore]:
    data = []
    for vs_type in DEFAULT_VS_TYPES:
        kb = KBServiceFactory.get_service(knowledge_base_name, vs_type)
        if kb is None:
            continue
        docs = kb.search_docs(query, top_k * 2, score_threshold)
        no_replicate_docs = docs[:top_k]
        data.extend([DocumentWithScore(page_content=x[0].page_content, metadata=x[0].metadata, score=x[1]) for x in no_replicate_docs])
    return data


def search_all_kbs(query, top_k, score_threshold) -> List[DocumentWithScore]:
    """
    全库检索内部函数：遍历所有知识库进行联合检索
    """
    from server.db.repository.knowledge_base_repository import list_kbs_from_db
    
    all_results = []
    kb_list = list_kbs_from_db()
    
    for kb_info in kb_list:
        kb_name = kb_info.get("kb_name")
        if not kb_name:
            continue
        
        try:
            docs = search_docs(query, kb_name, top_k, score_threshold)
            for doc in docs:
                doc.kb_name = kb_name
                if doc.metadata:
                    doc.metadata["kb_name"] = kb_name
                else:
                    doc.metadata = {"kb_name": kb_name}
            all_results.extend(docs)
        except Exception as e:
            logger.warning(f"检索知识库 {kb_name} 时出错: {e}")
            continue
    
    all_results.sort(key=lambda x: x.score if x.score else 0, reverse=True)
    
    return all_results[:top_k * 3]

def kb_file_details(knowledge_base_name: str) -> BaseResponse:
    """获取知识库中文件的详细信息（包含文件名、大小、时间等）"""
    if not validate_kb_name(knowledge_base_name):
        return BaseResponse(code=403, msg="Don't attack me", data=[])
    knowledge_base_name = urllib.parse.unquote(knowledge_base_name)
    details = get_kb_file_details(knowledge_base_name)
    return BaseResponse(code=200, msg="Success", data=details or [])

def list_files(knowledge_base_name: str) -> ListResponse:
    if not validate_kb_name(knowledge_base_name):
        return ListResponse(code=403, msg="Don't attack me", data=[])
    knowledge_base_name = urllib.parse.unquote(knowledge_base_name)
    all_doc_names = []
    for vs_type in DEFAULT_VS_TYPES:
        kb = KBServiceFactory.get_service(knowledge_base_name, vs_type)
        if kb: all_doc_names.extend(kb.list_files())
    return ListResponse(data=list(set(all_doc_names)))

# --- 已修复参数命名冲突 ---
def _save_files_in_thread(files, knowledge_base_name, override):
    def save_file(file, knowledge_base_name, override):
        try:
            filename = file.filename
            file_path = get_file_path(knowledge_base_name=knowledge_base_name, doc_name=filename)
            file_content = file.file.read()
            if not os.path.isdir(os.path.dirname(file_path)): 
                os.makedirs(os.path.dirname(file_path))
            
            # 覆盖逻辑检查
            if not override and os.path.exists(file_path):
                return dict(code=400, msg=f"File {filename} already exists", data={"file_name": filename})
            with open(file_path, "wb") as f: 
                f.write(file_content)
            return dict(code=200, msg="Success", data={"file_name": filename})
        except Exception as e:
            return dict(code=500, msg=str(e), data={"file_name": file.filename})

    params = [{"file": f, "knowledge_base_name": knowledge_base_name, "override": override} for f in files]
    for result in run_in_thread_pool(save_file, params=params): 
        yield result

def upload_docs(
        files: List[UploadFile] = File(...),
        knowledge_base_name: str = Form(...),
        override: bool = Form(False),
        to_vector_store: bool = Form(True),
        chunk_size: int = Form(CHUNK_SIZE),
        chunk_overlap: int = Form(OVERLAP_SIZE),
        zh_title_enhance: bool = Form(ZH_TITLE_ENHANCE),
        docs: str = Form(default="{}"),
        not_refresh_vs_cache: bool = Form(False),
) -> BaseResponse:
    # 解析 docs JSON 字符串
    try:
        docs = json.loads(docs) if docs else {}
    except:
        docs = {}
    if not validate_kb_name(knowledge_base_name):
        return BaseResponse(code=403, msg="Knowledge base name invalid")

    failed_files = {}
    file_names = list(docs.keys())
    
    for result in _save_files_in_thread(files, knowledge_base_name, override):
        filename = result["data"]["file_name"]
        if result["code"] != 200: 
            failed_files[filename] = result["msg"]
        if filename not in file_names: 
            file_names.append(filename)

    if to_vector_store:
        res = update_docs(knowledge_base_name, file_names, chunk_size, chunk_overlap, zh_title_enhance, True, docs, True)
        if res.code != 200:
            return res
        failed_files.update(res.data.get("failed_files", {}))
        
        if not not_refresh_vs_cache:
            for vs_type in DEFAULT_VS_TYPES:
                kb = KBServiceFactory.get_service(knowledge_base_name, vs_type)
                if kb: kb.save_vector_store()
                
    return BaseResponse(code=200, msg="Done", data={"failed_files": failed_files})

def delete_docs(
        knowledge_base_name: str = Body(..., examples=["samples"]),
        file_names: List[str] = Body(..., examples=[["test.txt"]]),
        delete_content: bool = Body(False),
        not_refresh_vs_cache: bool = Body(False),
) -> BaseResponse:
    knowledge_base_name = urllib.parse.unquote(knowledge_base_name)
    failed_files = {}
    for vs_type in DEFAULT_VS_TYPES:
        kb = KBServiceFactory.get_service(knowledge_base_name, vs_type)
        if kb is None: continue
        for file_name in file_names:
            try:
                kb_file = KnowledgeFile(filename=file_name, knowledge_base_name=knowledge_base_name)
                kb.delete_doc(kb_file, delete_content, not_refresh_vs_cache=True)
            except Exception as e: 
                failed_files[file_name] = str(e)
        if not not_refresh_vs_cache: 
            kb.save_vector_store()
    return BaseResponse(code=200, msg="Delete Done", data={"failed_files": failed_files})

def update_info(
    knowledge_base_name: str = Body(..., examples=["samples"]),
    kb_info: str = Body("", examples=["new info"]),
) -> BaseResponse:
    if not knowledge_base_name:
        return BaseResponse(code=422, msg="Missing knowledge_base_name")
        
    kb_name = urllib.parse.unquote(knowledge_base_name)
    for vs_type in DEFAULT_VS_TYPES:
        kb = KBServiceFactory.get_service(kb_name, vs_type)
        if kb:
            kb.update_info(kb_info)
    return BaseResponse(code=200, msg="Success", data={"kb_info": kb_info})

def update_docs(
        knowledge_base_name: str = Body(..., description="知识库名称"),
        file_names: List[str] = Body(..., description="文件名列表"),
        chunk_size: int = Body(CHUNK_SIZE, description="分块大小"),
        chunk_overlap: int = Body(OVERLAP_SIZE, description="分块重叠"),
        zh_title_enhance: bool = Body(False, description="中文标题增强"),
        override_custom_docs: bool = Body(False, description="覆盖自定义文档"),
        docs: Dict = Body({}, description="自定义文档"),
        not_refresh_vs_cache: bool = Body(False, description="不刷新向量缓存"),
) -> BaseResponse:
    failed_files = {}
    kb_files = []
    for file_name in file_names:
        if file_name not in docs:
            try: 
                kb_files.append(KnowledgeFile(filename=file_name, knowledge_base_name=knowledge_base_name))
            except Exception as e: 
                failed_files[file_name] = str(e)
                
    for vs_type in DEFAULT_VS_TYPES:
        kb = KBServiceFactory.get_service(knowledge_base_name, vs_type)
        if kb is None: continue
        for status, result in files2docs_in_thread(kb_files, chunk_size=chunk_size, chunk_overlap=chunk_overlap, zh_title_enhance=zh_title_enhance):
            if status:
                kb_file = KnowledgeFile(filename=result[1], knowledge_base_name=knowledge_base_name)
                kb_file.splited_docs = result[2]
                kb.update_doc(kb_file, not_refresh_vs_cache=True)
            else: 
                failed_files[result[1]] = result[2]
        if not not_refresh_vs_cache: 
            kb.save_vector_store()
            
    return BaseResponse(code=200, msg="Update Done", data={"failed_files": failed_files})

def download_doc(
        knowledge_base_name: str = Query(...), 
        file_name: str = Query(...), 
        preview: bool = Query(False)
):
    kb_file = KnowledgeFile(filename=file_name, knowledge_base_name=knowledge_base_name)
    if os.path.exists(kb_file.filepath):
        return FileResponse(
            path=kb_file.filepath, 
            filename=kb_file.filename, 
            content_disposition_type="inline" if preview else "attachment"
        )
    return BaseResponse(code=404, msg="Not Found")

def docs_text_split_content(
    knowledge_base_name: str = Body(..., examples=["samples"]),
    file_names: List[str] = Body(..., examples=[["test.txt"]]),
) -> BaseResponse:
    """预览选中文档的分词内容"""
    try:
        data = []
        for file_name in file_names:
            kb_file = KnowledgeFile(filename=file_name, knowledge_base_name=knowledge_base_name)
            if os.path.exists(kb_file.filepath):
                docs = kb_file.file2docs()
                data.append({
                    "file_name": file_name,
                    "contents": [doc.page_content for doc in docs[:10]]
                })
        res_data = [{"vs_type": vs, "data": data} for vs in DEFAULT_VS_TYPES]
        return BaseResponse(code=200, msg="Success", data=res_data)
    except Exception as e:
        return BaseResponse(code=500, msg=f"Error: {str(e)}")

def recreate_vector_store(
        knowledge_base_name: str = Body(...), 
        allow_empty_kb: bool = Body(True), 
        embed_model: str = Body(EMBEDDING_MODEL), 
        chunk_size: int = Body(CHUNK_SIZE), 
        chunk_overlap: int = Body(OVERLAP_SIZE), 
        zh_title_enhance: bool = Body(ZH_TITLE_ENHANCE), 
        not_refresh_vs_cache: bool = Body(False)
):
    def output():
        for vs_type in DEFAULT_VS_TYPES:
            kb = KBServiceFactory.get_service(knowledge_base_name, vs_type, embed_model)
            if not kb: continue
            kb.clear_vs()
            kb.create_kb()
            files = list_files_from_folder(knowledge_base_name)
            if not files and not allow_empty_kb:
                yield json.dumps({"code": 404, "msg": "No files found"}, ensure_ascii=False)
                return

            for i, (status, result) in enumerate(files2docs_in_thread([(f, knowledge_base_name) for f in files], chunk_size=chunk_size, chunk_overlap=chunk_overlap, zh_title_enhance=zh_title_enhance)):
                if status:
                    kb_file = KnowledgeFile(filename=result[1], knowledge_base_name=knowledge_base_name)
                    kb_file.splited_docs = result[2]
                    kb.add_doc(kb_file, not_refresh_vs_cache=True)
                    yield json.dumps({"code": 200, "finished": i+1, "total": len(files), "doc": result[1]}, ensure_ascii=False)
            if not not_refresh_vs_cache: 
                kb.save_vector_store()
                
    return StreamingResponse(output(), media_type="text/event-stream")