import pdb
import urllib
from server.utils import BaseResponse, ListResponse
from server.knowledge_base.utils import validate_kb_name
from server.knowledge_base.kb_service.base import KBServiceFactory
from server.db.repository.knowledge_base_repository import list_kbs_from_db, get_kb_detail
from configs import EMBEDDING_MODEL, logger, log_verbose, DEFAULT_VS_TYPES
from fastapi import Body


def list_kbs():
    # Get List of Knowledge Base
    return BaseResponse(code=200, data=list_kbs_from_db())

def kb_detail(knowledge_base_name: str) -> BaseResponse:
    # Get List of Knowledge Base
    return BaseResponse(
        code=200,
        message="获取知识库详情成功",
        data=get_kb_detail(knowledge_base_name))

def create_kb(
        knowledge_base_name: str = Body(..., examples=["samples"]),
        info: str = Body(default=""),
        embed_model: str = Body(EMBEDDING_MODEL),
        ) -> BaseResponse:
    print("====DEFAULT_VS_TYPES===", DEFAULT_VS_TYPES)
    # Create selected knowledge base
    if not validate_kb_name(knowledge_base_name):
        return BaseResponse(code=403, msg="Don't attack me")
    if knowledge_base_name is None or knowledge_base_name.strip() == "":
        return BaseResponse(code=404, msg="知识库名称不能为空，请重新填写知识库名称")
    
    # 检查知识库是否已存在
    existing_kb = KBServiceFactory.get_service_by_name(knowledge_base_name, DEFAULT_VS_TYPES[0] if DEFAULT_VS_TYPES else 'chroma')
    if existing_kb is not None:
        return BaseResponse(code=200, msg=f"知识库 {knowledge_base_name} 已存在")
    
    for vs_type in DEFAULT_VS_TYPES:
        kb = KBServiceFactory.get_service_by_name(knowledge_base_name, vs_type)
        if kb is not None:
            continue
        kb = KBServiceFactory.get_service(
            knowledge_base_name, vs_type, embed_model)
        try:
            if info:
                kb.kb_info = info
            kb.create_kb()
        except Exception as e:
            # 如果是已存在错误，跳过
            if "already exists" in str(e).lower() or "UniqueConstraintError" in str(type(e)):
                logger.info(f"知识库 {knowledge_base_name} 在 {vs_type} 中已存在，跳过创建")
                continue
            msg = f"创建知识库出错： {e}"
            logger.error(f'{e.__class__.__name__}: {msg}',
                         exc_info=e if log_verbose else None)
            continue

    return BaseResponse(code=200, msg=f"已新增知识库 {knowledge_base_name}")


def delete_kb(
    knowledge_base_name: str = Body(..., embed=True),
    ) -> BaseResponse:
    if not validate_kb_name(knowledge_base_name):
        return BaseResponse(code=403, msg="Don't attack me")
    knowledge_base_name = urllib.parse.unquote(knowledge_base_name)

    from server.knowledge_base.kb_service.chroma_kb_service import ChromaKBService
    from server.db.repository.knowledge_base_repository import delete_kb_from_db
    from server.db.repository.knowledge_file_repository import delete_files_from_db
    
    try:
        ChromaKBService.delete_collection_directly(knowledge_base_name)
        logger.info(f"[OK] 向量库集合删除成功: {knowledge_base_name}")
    except Exception as e:
        logger.warning(f"删除向量库集合时出错: {e}")

    try:
        delete_files_from_db(knowledge_base_name)
        logger.info(f"[OK] 知识库文件记录删除成功: {knowledge_base_name}")
    except Exception as e:
        logger.warning(f"删除知识库文件记录时出错: {e}")

    try:
        delete_kb_from_db(knowledge_base_name)
        logger.info(f"[OK] 知识库元数据删除成功: {knowledge_base_name}")
    except Exception as e:
        logger.error(f"删除知识库元数据时出错: {e}")

    return BaseResponse(code=200, msg=f"成功删除知识库 {knowledge_base_name}")

def update_kb_info(
    knowledge_base_name: str = Body(..., examples=["samples"]),
    info: str = Body(..., examples=["新的知识库介绍"]),
) -> BaseResponse:
    """
    补全修复：更新知识库的介绍信息
    """
    if not validate_kb_name(knowledge_base_name):
        return BaseResponse(code=403, msg="Don't attack me")
    
    found = False
    for vs_type in DEFAULT_VS_TYPES:
        kb = KBServiceFactory.get_service_by_name(knowledge_base_name, vs_type)
        if kb is not None:
            try:
                kb.kb_info = info
                # 这里假设底层服务有 update_kb_info 方法，如果没有则直接通过属性修改
                if hasattr(kb, 'update_kb_info'):
                    kb.update_kb_info(info)
                found = True
            except Exception as e:
                logger.error(f"更新知识库信息失败 ({vs_type}): {e}")
                continue
    
    if found:
        return BaseResponse(code=200, msg=f"成功更新知识库 {knowledge_base_name} 的信息")
    return BaseResponse(code=404, msg=f"未找到知识库 {knowledge_base_name}")
