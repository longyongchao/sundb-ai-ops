import os
import sys
from configs import (
    KB_ROOT_PATH,
    CHUNK_SIZE,
    OVERLAP_SIZE,
    ZH_TITLE_ENHANCE,
    logger,
    log_verbose,
    text_splitter_dict,
    LLM_MODELS,
    TEXT_SPLITTER_NAME,
)

import importlib
from text_splitter import zh_title_enhance as func_zh_title_enhance
import langchain.document_loaders
from langchain.docstore.document import Document
from langchain.text_splitter import TextSplitter
from pathlib import Path
from server.utils import run_in_thread_pool, get_model_worker_config
import json
import yaml
from typing import List, Union,Dict, Tuple, Generator
import chardet


def validate_kb_name(knowledge_base_id: str) -> bool:
    if "../" in knowledge_base_id:
        return False
    return True


def get_kb_path(knowledge_base_name: str):
    return os.path.join(KB_ROOT_PATH, knowledge_base_name)


def get_doc_path(knowledge_base_name: str):
    return os.path.join(get_kb_path(knowledge_base_name), "content")


def get_vs_path(knowledge_base_name: str, vector_name: str):
    return os.path.join(get_kb_path(knowledge_base_name), "vector_store", vector_name)


def get_file_path(knowledge_base_name: str, doc_name: str):
    return os.path.join(get_doc_path(knowledge_base_name), doc_name)


def list_kbs_from_folder():
    return [f for f in os.listdir(KB_ROOT_PATH)
            if os.path.isdir(os.path.join(KB_ROOT_PATH, f))]


def list_files_from_folder(kb_name: str):
    doc_path = get_doc_path(kb_name)
    result = []

    def is_skiped_path(path: str):
        tail = os.path.basename(path).lower()
        for x in ["temp", "tmp", ".", "~$"]:
            if tail.startswith(x):
                return True
        return False

    def process_entry(entry):
        if is_skiped_path(entry.path):
            return
        if entry.is_symlink():
            target_path = os.path.realpath(entry.path)
            with os.scandir(target_path) as target_it:
                for target_entry in target_it:
                    process_entry(target_entry)
        elif entry.is_file():
            result.append(entry.path)
        elif entry.is_dir():
            with os.scandir(entry.path) as it:
                for sub_entry in it:
                    process_entry(sub_entry)

    with os.scandir(doc_path) as it:
        for entry in it:
            process_entry(entry)
    return result


DIAGNOSE_FILE_DICT = {"JSONLoader": [".json", ".jsonl"]}
KNOWLEDGE_EXTRACTION_FILE_DICT = {"UnstructuredWordDocumentLoader": [".docx", ".doc"]}

LOADER_DICT = {
    # 文档类
    "UnstructuredHTMLLoader": ['.html', '.htm'],
    "UnstructuredMarkdownLoader": ['.md', '.markdown'],
    "UnstructuredWordDocumentLoader": ['.docx', '.doc'],
    "UnstructuredPowerPointLoader": ['.ppt', '.pptx'],
    "UnstructuredFileLoader": ['.txt', '.text', '.log', '.out'],
    
    # PDF - 使用 PyPDFLoader 或 RapidOCRPDFLoader
    "PyPDFLoader": ['.pdf'],
    
    # 数据类
    "JSONLoader": ['.json'],
    "JSONLinesLoader": ['.jsonl'],
    "CSVLoader": [".csv"],
    "UnstructuredExcelLoader": ['.xlsx', '.xls'],
    
    # 代码类
    "PythonLoader": ['.py'],
    # SQL 和其他代码文件作为普通文本处理
    "UnstructuredFileLoader_extra": ['.sql', '.sh', '.bash', '.bat', '.ps1', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.go', '.rs', '.rb', '.php'],
    
    # 配置类
    "TomlLoader": ['.toml'],
    "UnstructuredXMLLoader": ['.xml'],
    # YAML 和其他配置文件作为普通文本处理
    "UnstructuredFileLoader_config": ['.yaml', '.yml', '.conf', '.cfg', '.ini', '.env', '.properties'],
    
    # 其他格式
    "RapidOCRLoader": ['.png', '.jpg', '.jpeg', '.bmp', '.gif'],
    "UnstructuredEmailLoader": ['.eml', '.msg'],
    "UnstructuredEPubLoader": ['.epub'],
    "NotebookLoader": ['.ipynb'],
    "UnstructuredODTLoader": ['.odt'],
    "UnstructuredRSTLoader": ['.rst'],
    "UnstructuredRTFLoader": ['.rtf'],
    "SRTLoader": ['.srt'],
    "UnstructuredTSVLoader": ['.tsv'],
}

# 构建支持的扩展名列表（去重）
def _build_supported_exts():
    exts = []
    for loader_name, extensions in LOADER_DICT.items():
        for ext in extensions:
            if ext not in exts:
                exts.append(ext)
    return exts

SUPPORTED_EXTS = _build_supported_exts()


def _new_json_dumps(obj, **kwargs):
    kwargs["ensure_ascii"] = False
    return _origin_json_dumps(obj, **kwargs)

if json.dumps is not _new_json_dumps:
    _origin_json_dumps = json.dumps
    json.dumps = _new_json_dumps


class JSONLinesLoader(langchain.document_loaders.JSONLoader):
    """
    自定义 JSONL 加载器，逐行读取 JSONL 文件，支持错误容忍
    """
    def __init__(self, file_path, **kwargs):
        # 强制设置 json_lines=True
        kwargs['json_lines'] = True
        # 设置默认的 jq_schema
        kwargs.setdefault('jq_schema', '.')
        kwargs.setdefault('text_content', False)
        super().__init__(file_path, **kwargs)


class RobustJSONLinesLoader:
    """
    更健壮的 JSONL 加载器，能够跳过格式错误的行
    """
    def __init__(self, file_path, **kwargs):
        self.file_path = file_path
        self.kwargs = kwargs
    
    def load(self) -> List[Document]:
        """读取 JSONL 或 JSON 数组文件，自动检测格式"""
        docs = []
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                return docs
            
            if content.startswith('['):
                try:
                    data_list = json.loads(content)
                    if isinstance(data_list, list):
                        for idx, data in enumerate(data_list):
                            if isinstance(data, dict):
                                content_str = json.dumps(data, ensure_ascii=False)
                            else:
                                content_str = str(data)
                            docs.append(Document(
                                page_content=content_str,
                                metadata={
                                    'source': self.file_path,
                                    'index': idx
                                }
                            ))
                        logger.info(f"JSON 数组文件 {self.file_path} 成功加载 {len(docs)} 条记录")
                        return docs
                except json.JSONDecodeError as e:
                    logger.warning(f"文件 {self.file_path} 看起来像 JSON 数组但解析失败，尝试按 JSONL 处理: {e}")
            
            for line_num, line in enumerate(content.split('\n'), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    content_str = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
                    docs.append(Document(
                        page_content=content_str,
                        metadata={
                            'source': self.file_path,
                            'line': line_num
                        }
                    ))
                except json.JSONDecodeError as e:
                    logger.warning(f"JSONL 文件 {self.file_path} 第 {line_num} 行格式错误，已跳过: {str(e)[:50]}")
                    continue
        except Exception as e:
            logger.error(f"读取 JSONL 文件 {self.file_path} 失败: {e}")
        return docs


# 注册到 langchain
langchain.document_loaders.JSONLinesLoader = RobustJSONLinesLoader


def get_LoaderClass(file_extension):
    """根据文件扩展名获取对应的加载器类名"""
    for LoaderClass, extensions in LOADER_DICT.items():
        if file_extension in extensions:
            # 特殊处理：带后缀的加载器名称映射到实际加载器
            if LoaderClass in ['UnstructuredFileLoader_extra', 'UnstructuredFileLoader_config']:
                return 'UnstructuredFileLoader'
            return LoaderClass
    return None


def get_loader(loader_name: str, file_path: str, loader_kwargs: Dict = None):
    loader_kwargs = loader_kwargs or {}
    try:
        if loader_name in ["RapidOCRPDFLoader", "RapidOCRLoader","FilteredCSVLoader"]:
            document_loaders_module = importlib.import_module('document_loaders')
        else:
            document_loaders_module = importlib.import_module('langchain.document_loaders')
        DocumentLoader = getattr(document_loaders_module, loader_name)
    except Exception as e:
        document_loaders_module = importlib.import_module('langchain.document_loaders')
        DocumentLoader = getattr(document_loaders_module, "UnstructuredFileLoader")

    def metadata_func(sample: Dict, additional_fields: Dict) -> Dict:
        return {**sample, **additional_fields}

    if loader_name == "UnstructuredFileLoader":
        loader_kwargs.setdefault("autodetect_encoding", True)
    
    # PDF 文件处理
    elif loader_name == "PyPDFLoader":
        try:
            # 尝试使用 PyPDFLoader
            document_loaders_module = importlib.import_module('langchain.document_loaders')
            DocumentLoader = getattr(document_loaders_module, "PyPDFLoader", None)
            if DocumentLoader:
                return DocumentLoader(file_path, **loader_kwargs)
        except:
            pass
        # 如果 PyPDFLoader 不可用，使用 UnstructuredFileLoader 作为备选
        loader_kwargs.setdefault("autodetect_encoding", True)
    elif loader_name == "CSVLoader":
        if not loader_kwargs.get("encoding"):
            with open(file_path, 'rb') as struct_file:
                encode_detect = chardet.detect(struct_file.read())
            if encode_detect is None:
                encode_detect = {"encoding": "utf-8"}
            loader_kwargs["encoding"] = encode_detect["encoding"]
    
    # [OK] 核心修复逻辑：增强 JSONLoader 的兼容性，不再强制要求 metrics 字段
    elif loader_name == "JSONLoader":
        loader_kwargs.setdefault("jq_schema", ".") # 默认读取全量
        loader_kwargs.setdefault("text_content", False)
        # 如果你确实需要保留 metadata_func
        # loader_kwargs.setdefault("metadata_func", metadata_func)
        
    elif loader_name == "JSONLinesLoader":
        # JSONL 文件：每行是一个独立的 JSON 对象
        # 不需要额外设置，JSONLinesLoader 类已经处理好了
        pass
    

    loader = DocumentLoader(file_path, **loader_kwargs)
    return loader


def make_text_splitter(
        splitter_name: str = TEXT_SPLITTER_NAME,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = OVERLAP_SIZE,
        llm_model: str = LLM_MODELS[0],
):
    splitter_name = splitter_name or "SpacyTextSplitter"
    try:
        if splitter_name == "MarkdownHeaderTextSplitter":
            headers_to_split_on = text_splitter_dict[splitter_name]['headers_to_split_on']
            text_splitter = langchain.text_splitter.MarkdownHeaderTextSplitter(
                headers_to_split_on=headers_to_split_on)
        else:
            try:
                text_splitter_module = importlib.import_module('text_splitter')
                TextSplitter = getattr(text_splitter_module, splitter_name)
            except:
                text_splitter_module = importlib.import_module('langchain.text_splitter')
                TextSplitter = getattr(text_splitter_module, splitter_name)

            if text_splitter_dict[splitter_name]["source"] == "tiktoken":
                try:
                    text_splitter = TextSplitter.from_tiktoken_encoder(
                        encoding_name=text_splitter_dict[splitter_name]["tokenizer_name_or_path"],
                        pipeline="zh_core_web_sm",
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap
                    )
                except:
                    text_splitter = TextSplitter.from_tiktoken_encoder(
                        encoding_name=text_splitter_dict[splitter_name]["tokenizer_name_or_path"],
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap
                    )
            elif text_splitter_dict[splitter_name]["source"] == "huggingface":
                if text_splitter_dict[splitter_name]["tokenizer_name_or_path"] == "":
                    config = get_model_worker_config(llm_model)
                    text_splitter_dict[splitter_name]["tokenizer_name_or_path"] = config.get("model_path")

                from transformers import AutoTokenizer
                tokenizer = AutoTokenizer.from_pretrained(
                    text_splitter_dict[splitter_name]["tokenizer_name_or_path"],
                    trust_remote_code=True)
                text_splitter = TextSplitter.from_huggingface_tokenizer(
                    tokenizer=tokenizer,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap
                )
            else:
                try:
                    text_splitter = TextSplitter(
                        pipeline="zh_core_web_sm",
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap
                    )
                except:
                    text_splitter = TextSplitter(
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap
                    )
    except Exception as e:
        text_splitter_module = importlib.import_module('langchain.text_splitter')
        TextSplitter = getattr(text_splitter_module, "RecursiveCharacterTextSplitter")
        text_splitter = TextSplitter(chunk_size=chunk_size, chunk_overlap=50)
    return text_splitter


class KnowledgeFile:
    def __init__(
            self,
            filename: str,
            knowledge_base_name: str,
            loader_kwargs: Dict = {},
    ):
        self.kb_name = knowledge_base_name
        self.filename = filename
        self.ext = os.path.splitext(filename)[-1].lower()
        if self.ext not in SUPPORTED_EXTS:
            raise ValueError(f"暂未支持的文件格式 {self.filename}")
        self.loader_kwargs = loader_kwargs
        self.filepath = get_file_path(knowledge_base_name, filename)
        self.docs = None
        self.splited_docs = None
        self.document_loader_name = get_LoaderClass(self.ext)
        self.text_splitter_name = TEXT_SPLITTER_NAME

    def convert_yaml_to_json(self, content):
        try:
            if isinstance(content, dict): return json.dumps(content)
            json.loads(content)
            return content
        except:
            try:
                yaml_content = yaml.safe_load(content)
                return json.dumps(yaml_content)
            except:
                return str(content)

    def file2docs(self, refresh: bool = False):
        if self.docs is None or refresh:
            logger.info(f"[{self.document_loader_name}] 加载文件: {self.filepath}")
            loader = get_loader(loader_name=self.document_loader_name,
                                file_path=self.filepath,
                                loader_kwargs=self.loader_kwargs)
            self.docs = loader.load()

            # 兼容性处理：防止 JSON 内容解析失败
            if self.document_loader_name == 'JSONLoader':
                for doc in self.docs:
                    if hasattr(doc, 'page_content'):
                        doc.page_content = self.convert_yaml_to_json(doc.page_content)
            
            # JSONL 文件特殊处理
            if self.document_loader_name == 'JSONLinesLoader':
                for doc in self.docs:
                    if hasattr(doc, 'page_content'):
                        doc.page_content = self.convert_yaml_to_json(doc.page_content)
        return self.docs

    def docs2texts(
            self,
            docs: List[Document] = None,
            zh_title_enhance: bool = ZH_TITLE_ENHANCE,
            refresh: bool = False,
            chunk_size: int = CHUNK_SIZE,
            chunk_overlap: int = OVERLAP_SIZE,
            text_splitter: TextSplitter = None,
    ):
        docs = docs or self.file2docs(refresh=refresh)
        if not docs:
            return []
        if self.ext not in [".csv"]:
            if text_splitter is None:
                text_splitter = make_text_splitter(splitter_name=self.text_splitter_name, chunk_size=chunk_size,
                                                   chunk_overlap=chunk_overlap)
            if self.text_splitter_name == "MarkdownHeaderTextSplitter":
                docs = text_splitter.split_text(docs[0].page_content)
            else:
                docs = text_splitter.split_documents(docs)

        if not docs:
            return []

        if zh_title_enhance:
            docs = func_zh_title_enhance(docs)
        self.splited_docs = docs
        return self.splited_docs

    def file2text(
            self,
            zh_title_enhance: bool = ZH_TITLE_ENHANCE,
            refresh: bool = False,
            chunk_size: int = CHUNK_SIZE,
            chunk_overlap: int = OVERLAP_SIZE,
            text_splitter: TextSplitter = None,
    ):
        if self.splited_docs is None or refresh:
            docs = self.file2docs()
            self.splited_docs = self.docs2texts(docs=docs,
                                                zh_title_enhance=zh_title_enhance,
                                                refresh=refresh,
                                                chunk_size=chunk_size,
                                                chunk_overlap=chunk_overlap,
                                                text_splitter=text_splitter)
        return self.splited_docs

    def file_exist(self):
        return os.path.isfile(self.filepath)

    def get_mtime(self):
        return os.path.getmtime(self.filepath)

    def get_size(self):
        return os.path.getsize(self.filepath)


def files2docs_in_thread(
        files: List[Union[KnowledgeFile, Tuple[str, str], Dict]],
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = OVERLAP_SIZE,
        zh_title_enhance: bool = ZH_TITLE_ENHANCE,
) -> Generator:
    def file2docs(*, file: KnowledgeFile, **kwargs) -> Tuple[bool, Tuple[str, str, List[Document]]]:
        try:
            return True, (file.kb_name, file.filename, file.file2text(**kwargs))
        except Exception as e:
            msg = f"错误：无法解析文件 {file.filename}。详情: {str(e)}"
            logger.error(msg)
            return False, (file.kb_name, file.filename, msg)
    
    kwargs_list = []
    for file in files:
        kwargs = {}
        try:
            if isinstance(file, tuple):
                file = KnowledgeFile(filename=file[0], knowledge_base_name=file[1])
            elif isinstance(file, dict):
                filename = file.pop("filename")
                kb_name = file.pop("kb_name")
                kwargs.update(file)
                file = KnowledgeFile(filename=filename, knowledge_base_name=kb_name)
            kwargs["file"] = file
            kwargs["chunk_size"] = chunk_size
            kwargs["chunk_overlap"] = chunk_overlap
            kwargs["zh_title_enhance"] = zh_title_enhance
            kwargs_list.append(kwargs)
        except Exception as e:
            yield False, ("unknown", "unknown", str(e))
    
    for result in run_in_thread_pool(func=file2docs, params=kwargs_list):
        yield result
