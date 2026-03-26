from langchain.docstore.document import Document
from configs import EMBEDDING_MODEL, logger, MODEL_PATH
from server.model_workers.base import ApiEmbeddingsParams
from server.utils import BaseResponse, get_model_worker_config, list_embed_models, list_online_embed_models
from fastapi import Body
from typing import Dict, List
import os

online_embed_models = list_online_embed_models()


def embed_texts(
    texts: List[str],
    embed_model: str = EMBEDDING_MODEL,
    to_query: bool = False,
) -> BaseResponse:
    '''
    对文本进行向量化。返回数据格式：BaseResponse(data=List[List[float]])
    '''
    try:
        # 优先检查是否是本地 m3e 模型，直接硬编码逻辑确保离线状态下也能穿透过滤
        if "m3e" in embed_model.lower() or embed_model in list_embed_models():
            from server.utils import load_local_embeddings
            
            # 强制打印调试信息
            print(f"--- [DEBUG] Local Embedding Loading: {embed_model} ---")
            
            embeddings = load_local_embeddings(model=embed_model)
            
            if embeddings is None:
                return BaseResponse(code=500, msg=f"无法加载本地模型 {embed_model}，请检查模型路径是否存在。")
            
            return BaseResponse(data=embeddings.embed_documents(texts))

        # 使用在线API
        if embed_model in list_online_embed_models():
            config = get_model_worker_config(embed_model)
            worker_class = config.get("worker_class")
            worker = worker_class()
            if worker_class.can_embedding():
                params = ApiEmbeddingsParams(texts=texts, to_query=to_query)
                resp = worker.do_embeddings(params)
                return BaseResponse(**resp)

        return BaseResponse(code=500, msg=f"指定的模型 {embed_model} 不支持 Embeddings 功能或未找到配置。")
        
    except Exception as e:
        import traceback
        error_msg = f"文本向量化过程中出现错误：{str(e)}"
        print(f"[ERROR] {error_msg}")
        traceback.print_exc() # 打印详细堆栈到控制台
        logger.error(error_msg)
        return BaseResponse(code=500, msg=error_msg)

def embed_texts_endpoint(
    texts: List[str] = Body(..., description="要嵌入的文本列表", examples=[["hello", "world"]]),
    embed_model: str = Body(EMBEDDING_MODEL, description=f"使用的嵌入模型"),
    to_query: bool = Body(False, description="向量是否用于查询"),
) -> BaseResponse:
    return embed_texts(texts=texts, embed_model=embed_model, to_query=to_query)


def embed_documents(
    docs: List[Document],
    embed_model: str = EMBEDDING_MODEL,
    to_query: bool = False,
) -> Dict:
    """
    将 List[Document] 向量化，转化为 VectorStore.add_embeddings 可以接受的参数
    """
    texts = [x.page_content for x in docs]
    metadatas = [x.metadata for x in docs]
    
    resp = embed_texts(texts=texts, embed_model=embed_model, to_query=to_query)
    embeddings = resp.data
    
    if embeddings is not None:
        return {
            "texts": texts,
            "embeddings": embeddings,
            "metadatas": metadatas,
        }
    else:
        # 如果 embeddings 为 None，抛出异常让上层捕获，而不是静默失败
        raise ValueError(f"向量化失败，模型返回数据为空。错误信息: {resp.msg}")
