import operator
from abc import ABC, abstractmethod

import os
from pathlib import Path
import numpy as np
from langchain.embeddings.base import Embeddings
from langchain.docstore.document import Document

from server.db.repository.knowledge_base_repository import (
    add_kb_to_db, delete_kb_from_db, list_kbs_from_db, kb_exists,
    load_kb_from_db, get_kb_detail,
)
from server.db.repository.knowledge_file_repository import (
    add_file_to_db,
    delete_file_from_db,
    delete_files_from_db,
    file_exists_in_db,
    count_files_from_db,
    list_files_from_db,
    get_file_detail,
    list_docs_from_db,
)

from configs import (kbs_config, VECTOR_SEARCH_TOP_K, SCORE_THRESHOLD,
                     EMBEDDING_MODEL, KB_INFO, DEFAULT_VS_TYPES)
from server.knowledge_base.utils import (
    get_kb_path, get_doc_path, KnowledgeFile,
    list_kbs_from_folder, list_files_from_folder,
)

from typing import List, Union, Dict, Optional

# 导入修复后的本地加载工具
from server.utils import load_local_embeddings
from server.embeddings_api import embed_texts
from server.embeddings_api import embed_documents
from server.knowledge_base.model.kb_document_model import DocumentWithVSId


def normalize(embeddings: List[List[float]]) -> np.ndarray:
    '''
    核心修复：增加对 None 和空值的判断，防止 numpy 报 conjugate 错误。
    '''
    if embeddings is None:
        return np.array([])
    
    # 转换为 numpy 数组进行操作
    embeddings = np.array(embeddings)
    
    if embeddings.size == 0:
        return embeddings

    # 计算 L2 范数
    norm = np.linalg.norm(embeddings, axis=1)
    
    # 增加 1e-9 作为极小值，防止 division by zero
    norm = np.reshape(norm, (norm.shape[0], 1))
    return embeddings / (norm + 1e-9)


class SupportedVSType:
    FAISS = 'faiss'
    CHROMADB = 'chromadb'
    MILVUS = 'milvus'
    DEFAULT = 'default'
    ZILLIZ = 'zilliz'
    PG = 'pg'
    ES = 'es'


class KBService(ABC):

    def __init__(self,
                 knowledge_base_name: str,
                 embed_model: str = EMBEDDING_MODEL,
                 ):
        self.kb_name = knowledge_base_name
        self.kb_info = KB_INFO.get(
            knowledge_base_name,
            f"关于{knowledge_base_name}的知识库")
        self.embed_model = embed_model
        self.kb_path = get_kb_path(self.kb_name)
        self.doc_path = get_doc_path(self.kb_name)
        self.do_init()

    def __repr__(self) -> str:
        return f"{self.kb_name} @ {self.embed_model}"

    def save_vector_store(self):
        pass

    def create_kb(self):
        if not os.path.exists(self.doc_path):
            os.makedirs(self.doc_path)
        self.do_create_kb()
        print("========知识库入库=======" + f"KnowledgeBase {self.kb_name} created")
        status = add_kb_to_db(
            self.kb_name,
            self.kb_info,
            self.vs_type(),
            self.embed_model)
        return status

    def clear_vs(self):
        self.do_clear_vs()
        status = delete_files_from_db(self.kb_name)
        return status

    def drop_kb(self):
        self.do_drop_kb()
        status = delete_kb_from_db(self.kb_name)
        return status

    def _docs_to_embeddings(self, docs: List[Document]) -> Dict:
        return embed_documents(
            docs=docs,
            embed_model=self.embed_model,
            to_query=False)

    def add_doc(
            self,
            kb_file: KnowledgeFile,
            docs: List[Document] = [],
            **kwargs):
        if docs:
            custom_docs = True
            for doc in docs:
                doc.metadata.setdefault("source", kb_file.filename)
        else:
            docs = kb_file.file2text()
            custom_docs = False

        if docs:
            for doc in docs:
                try:
                    source = doc.metadata.get("source", "")
                    rel_path = Path(source).relative_to(self.doc_path)
                    doc.metadata["source"] = str(
                        rel_path.as_posix().strip("/"))
                except Exception as e:
                    pass
            
            self.delete_doc(kb_file)
            doc_infos = self.do_add_doc(docs, **kwargs)
            status = add_file_to_db(kb_file,
                                    custom_docs=custom_docs,
                                    docs_count=len(docs),
                                    doc_infos=doc_infos)
        else:
            status = False
        return status

    def delete_doc(
            self,
            kb_file: KnowledgeFile,
            delete_content: bool = False,
            **kwargs):
        self.do_delete_doc(kb_file, **kwargs)
        status = delete_file_from_db(kb_file)
        if delete_content and os.path.exists(kb_file.filepath):
            os.remove(kb_file.filepath)
        return status

    def update_info(self, kb_info: str):
        self.kb_info = kb_info
        status = add_kb_to_db(
            self.kb_name,
            self.kb_info,
            self.vs_type(),
            self.embed_model)
        return status

    def update_doc(
            self,
            kb_file: KnowledgeFile,
            docs: List[Document] = [],
            **kwargs):
        if os.path.exists(kb_file.filepath):
            self.delete_doc(kb_file, **kwargs)
            return self.add_doc(kb_file, docs=docs, **kwargs)

    def exist_doc(self, file_name: str):
        return file_exists_in_db(
            KnowledgeFile(
                knowledge_base_name=self.kb_name,
                filename=file_name))

    def list_files(self):
        return list_files_from_db(self.kb_name)

    def count_files(self):
        return count_files_from_db(self.kb_name)

    def search_docs(self,
                    query: str,
                    top_k: int = VECTOR_SEARCH_TOP_K,
                    score_threshold: float = SCORE_THRESHOLD,
                    ):
        docs = self.do_search(query, top_k, score_threshold)
        return docs

    def get_doc_by_ids(self, ids: List[str]) -> List[Document]:
        return []

    def list_docs(
            self,
            file_name: str = None,
            metadata: Dict = {}) -> List[DocumentWithVSId]:
        doc_infos = list_docs_from_db(
            kb_name=self.kb_name,
            file_name=file_name,
            metadata=metadata)
        docs = []
        for x in doc_infos:
            doc_info_s = self.get_doc_by_ids([x["id"]])
            if doc_info_s:
                doc_with_id = DocumentWithVSId(
                    **doc_info_s[0].dict(), id=x["id"])
                docs.append(doc_with_id)
        return docs

    @abstractmethod
    def do_create_kb(self):
        pass

    @staticmethod
    def list_kbs_type():
        return list(kbs_config.keys())

    @classmethod
    def list_kbs(cls):
        # 强制拦截 list_kbs 报错，防止 UI 崩溃
        try:
            return list_kbs_from_db()
        except:
            return []

    def exists(self, kb_name: str = None, vs_type: str = None):
        kb_name = kb_name or self.kb_name
        vs_type = vs_type or self.vs_type()
        return kb_exists(kb_name, vs_type)

    @abstractmethod
    def vs_type(self) -> str:
        pass

    @abstractmethod
    def do_init(self):
        pass

    @abstractmethod
    def do_drop_kb(self):
        pass

    @abstractmethod
    def do_search(self,
                  query: str,
                  top_k: int,
                  score_threshold: float,
                  ) -> List[Document]:
        pass

    @abstractmethod
    def do_add_doc(self,
                    docs: List[Document],
                    ) -> List[Dict]:
        pass

    @abstractmethod
    def do_delete_doc(self,
                      kb_file: KnowledgeFile):
        pass

    @abstractmethod
    def do_clear_vs(self):
        pass


class KBServiceFactory:

    @staticmethod
    def get_service(kb_name: str,
                    vector_store_type: Union[str, SupportedVSType],
                    embed_model: str = EMBEDDING_MODEL,
                    ) -> KBService:
        if isinstance(vector_store_type, str):
            # --- 核心防御逻辑 ---
            vs_name = vector_store_type.upper()
            if vs_name == "CHROMA": vs_name = "CHROMADB"
            
            # 获取枚举，找不到就默认 FAISS
            vector_store_type = getattr(SupportedVSType, vs_name, SupportedVSType.FAISS)
            
        if SupportedVSType.FAISS == vector_store_type:
            from server.knowledge_base.kb_service.faiss_kb_service import FaissKBService
            return FaissKBService(kb_name, embed_model=embed_model)
        elif SupportedVSType.CHROMADB == vector_store_type:
            from server.knowledge_base.kb_service.chroma_kb_service import ChromaKBService
            return ChromaKBService(kb_name, embed_model=embed_model)
        elif SupportedVSType.PG == vector_store_type:
            from server.knowledge_base.kb_service.pg_kb_service import PGKBService
            return PGKBService(kb_name, embed_model=embed_model)
        elif SupportedVSType.MILVUS == vector_store_type:
            from server.knowledge_base.kb_service.milvus_kb_service import MilvusKBService
            return MilvusKBService(kb_name, embed_model=embed_model)
        elif SupportedVSType.ZILLIZ == vector_store_type:
            from server.knowledge_base.kb_service.zilliz_kb_service import ZillizKBService
            return ZillizKBService(kb_name, embed_model=embed_model)
        elif SupportedVSType.ES == vector_store_type:
            from server.knowledge_base.kb_service.es_kb_service import ESKBService
            return ESKBService(kb_name, embed_model=embed_model)
        elif SupportedVSType.DEFAULT == vector_store_type:
            from server.knowledge_base.kb_service.default_kb_service import DefaultKBService
            return DefaultKBService(kb_name)
        
        # 最终兜底
        from server.knowledge_base.kb_service.faiss_kb_service import FaissKBService
        return FaissKBService(kb_name, embed_model=embed_model)

    @staticmethod
    def get_service_by_name(kb_name: str, vs_type: str) -> KBService:
        try:
            _load_data = load_kb_from_db(kb_name, vs_type)
            if _load_data is None or _load_data[0] is None:
                return None
            _, vs_type, embed_model = _load_data
            return KBServiceFactory.get_service(kb_name, vs_type, embed_model)
        except:
            return None

    @staticmethod
    def get_default():
        return KBServiceFactory.get_service("default", SupportedVSType.DEFAULT)


def get_kb_details() -> List[Dict]:
    try:
        kbs_in_folder = {kb:
                         {"kb_name": kb, "vs_type": "", "kb_info": "",
                          "embed_model": "", "file_count": 0,
                          "create_time": None, "update_time": None, "in_folder": True, "in_db": False}
                         for kb in list_kbs_from_folder()}

        kbs_in_db = {kb['kb_name']: kb for kb in KBService.list_kbs()}

        for kb_name, kb_detail in kbs_in_db.items():
            if kb_name in kbs_in_folder:
                kb_detail["in_db"] = True
                kbs_in_folder[kb_name].update(kb_detail)
            else:
                kb_detail.update(in_folder=False, in_db=True)
                kbs_in_folder[kb_name] = kb_detail

        for kb_name in kbs_in_folder:
            files = list_files_from_folder(kb_name)
            if files:
                latest_mtime = 0
                for f in files:
                    try:
                        mtime = os.path.getmtime(f)
                        if mtime > latest_mtime:
                            latest_mtime = mtime
                    except:
                        pass
                if latest_mtime > 0:
                    from datetime import datetime
                    kbs_in_folder[kb_name]["update_time"] = datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M:%S")

        data = [dict(No=i + 1, **v) for i, v in enumerate(kbs_in_folder.values())]
        return data
    except Exception as e:
        print(f"Error getting KB details: {e}")
        return []


def get_kb_file_details(kb_name: str) -> List[Dict]:
    v_type = DEFAULT_VS_TYPES[0] if DEFAULT_VS_TYPES else "faiss"
    kb = KBServiceFactory.get_service_by_name(kb_name, v_type)
    
    files_in_folder = list_files_from_folder(kb_name)
    files_in_db = kb.list_files() if kb else []
    result = {}

    for doc_path in files_in_folder:
        doc_name = os.path.basename(doc_path)
        
        try:
            file_stat = os.stat(doc_path)
            file_size = file_stat.st_size
            file_mtime = file_stat.st_mtime
        except:
            file_size = 0
            file_mtime = None
        
        result[doc_name] = {
            "kb_name": kb_name,
            "file_name": doc_name,
            "file_ext": os.path.splitext(doc_name)[-1],
            "file_version": 0,
            "document_loader": "",
            "docs_count": 0,
            "text_splitter": "",
            "create_time": file_mtime,
            "file_mtime": file_mtime,
            "file_size": file_size,
            "in_folder": True,
            "in_db": False,
        }
    
    for doc in files_in_db:
        doc_detail = get_file_detail(kb_name, doc)
        if doc_detail:
            doc_detail["in_db"] = True
            if doc in result.keys():
                folder_file_size = result[doc].get("file_size", 0)
                folder_file_mtime = result[doc].get("file_mtime")
                
                result[doc].update(doc_detail)
                
                if folder_file_size and folder_file_size > 0:
                    result[doc]["file_size"] = folder_file_size
                elif not result[doc].get("file_size") or result[doc].get("file_size") == 0:
                    if folder_file_size and folder_file_size > 0:
                        result[doc]["file_size"] = folder_file_size
                
                if folder_file_mtime:
                    result[doc]["file_mtime"] = folder_file_mtime
                elif not result[doc].get("file_mtime"):
                    result[doc]["file_mtime"] = result[doc].get("create_time")
            else:
                doc_detail["in_folder"] = False
                result[doc] = doc_detail

    data = []
    for i, v in enumerate(result.values()):
        v['No'] = i + 1
        data.append(v)

    return data


class EmbeddingsFunAdapter(Embeddings):
    def __init__(self, embed_model: str = EMBEDDING_MODEL):
        self.embed_model = embed_model
        # --- 核心修复：强制在适配器初始化时加载本地模型 ---
        print(f"--- [DEBUG] 适配器正在尝试接管模型: {self.embed_model} ---")
        try:
            self.local_model = load_local_embeddings(self.embed_model)
        except:
            self.local_model = None
        
        if self.local_model is not None:
            print(f"[OK] [SUCCESS] 适配器已成功接管本地模型: {self.embed_model}")
        else:
            print(f"[WARN] [WARNING] 适配器未能加载本地模型，将尝试使用 API 备份。")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # 优先使用本地模型
        if self.local_model:
            return self.local_model.embed_documents(texts)
        
        # 备选 API 逻辑
        res = embed_texts(
            texts=texts,
            embed_model=self.embed_model,
            to_query=False)
        if res is None or res.data is None:
            return []
        embeddings = res.data
        return normalize(embeddings).tolist()

    def embed_query(self, text: str) -> List[float]:
        if self.local_model:
            return self.local_model.embed_query(text)
            
        res = embed_texts(
            texts=[text],
            embed_model=self.embed_model,
            to_query=True)
        if res is None or res.data is None:
            return []
        embeddings = res.data
        query_embed = embeddings[0]
        query_embed_2d = np.reshape(query_embed, (1, -1))
        normalized_query_embed = normalize(query_embed_2d)
        if normalized_query_embed.size > 0:
            return normalized_query_embed[0].tolist()
        return []


def score_threshold_process(score_threshold, k, docs):
    if score_threshold is not None and score_threshold > 0:
        docs = [
            (doc, float(similarity))
            for doc, similarity in docs
            if float(similarity) <= score_threshold
        ]
    return docs[:k]
