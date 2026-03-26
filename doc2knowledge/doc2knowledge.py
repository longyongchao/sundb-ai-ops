from utilss import *
import ast
import sys
import os
import pypdf  
import json
import itertools
import re  
import time
from tqdm import tqdm as TQDM

sys.path.append("..")
try:
    from text_splitter.structured_document_splitter import StructuredDocumentSplitter, read_structured_docx, write_tree_to_files
except ImportError:
    print(colored("Warning: text_splitter 模块未找到，如果只处理PDF则不影响。", "yellow"))

def Initialize(doc, target_dir):
    path = os.path.join(doc, target_dir)
    if not os.path.exists(path):
        os.makedirs(path)

def Summarize(idx, title, content, llm, summary_min_length=400):
    return llm.Query(SUMMARIZE_PROMPT_MSG + MSG(CONTENT_TEMPLATE.format(idx=idx,title=title,content=content)))["content"] if len(content)>=summary_min_length else content

def CascadingSummary(args):
    doc_path = args.doc
    chunks_path = os.path.join(doc_path, "raw")

    if not os.path.exists(chunks_path):
        os.makedirs(chunks_path)

    files = [f for f in os.listdir(chunks_path) if f.endswith('.txt')]
    # 增加排序确保顺序正确
    files.sort(key=lambda x: [int(d) for d in re.findall(r'\d+', x)])
    
    nodes = [{
        'id': parse_id(chunk_name),
        'id_str': '.'.join([str(x) for x in parse_id(chunk_name)]),
        'name': chunk_name,
        'title': chunk_name.split(' ', 1)[-1][:-4],
        'content': read_txt(os.path.join(chunks_path, chunk_name)),
        'father': None,
        'children': [],
    } for chunk_name in files]

    if not nodes:
        print(colored("No text chunks found in raw folder.", "red"))
        return [], {}

    nodes_mapping = {node['id_str']: node for node in nodes}
    nodes_structure = {node['id_str']: {k:v for k,v in node.items() if k!='content'} for node in nodes}
    
    for node1, node2 in itertools.permutations(nodes_mapping.values(), 2):
        if is_father(node1['name'], node2['name']):
            nodes_mapping[node1['id_str']]['children'].append(node2['id_str'])
            nodes_structure[node1['id_str']]['children'].append(node2['id_str'])
            nodes_mapping[node2['id_str']]['father'] = node1['id_str']
            nodes_structure[node2['id_str']]['father'] = node1['id_str']
    
    nodes = topo_sort(list(nodes_mapping.values()))
    nodes_mapping = {node['id_str']: node for node in nodes}
    
    for i, v in enumerate(TQDM(nodes)):
        children = sorted([c for c in v['children']], key=lambda x:str2id(x))
        nodes[i]['index'] = [INDEX_TEMPLATE.format(idx=v['id_str'], title=v['title'])] + [
            INDEX_TEMPLATE.format(idx=c, title=nodes_mapping[c]['title']) for c in children
        ]
        nodes[i]['full_index'] = [INDEX_TEMPLATE.format(idx=v['id_str'], title=v['title'])] + sum(
            [nodes_mapping[c]['full_index'] for c in children], []
        )
        nodes[i]['content_summary'] = Summarize(idx=v['id_str'], title=v['title'], content=v['content'], llm=args.llm, summary_min_length=args.summary_min_length)
        v_summary = nodes[i]['content_summary']
        nodes[i]['summaries'] = [CONTENT_TEMPLATE.format(idx=v['id_str'], title=v['title'], content=v_summary)] + [
            CONTENT_TEMPLATE.format(idx=nodes_mapping[c]['id_str'], title=nodes_mapping[c]['title'], content=nodes_mapping[c].get('summary', '')) for c in children
        ]
        nodes[i]['summary'] = Summarize(idx=v['id_str'], title=v['title'], content="\n\n".join(nodes[i]['summaries']), llm=args.llm, summary_min_length=0) if len(nodes[i]['summaries'])>1 else nodes[i]['content_summary']
        nodes[i]['full_summary'] = DOCUMENT_VIEW_TEMPALTE.format(summaries="\n\n".join(nodes[i]['summaries']), index="\n".join(nodes[i]['full_index']))

    return nodes, nodes_structure

def count_num_tokens(messages):
    return len(str(messages).split())

def ExtractKnowledge(nodes_mapping, root_index, llm, iteration=2, iteration_gap=1, source_file='report_example', target_file="extracted_knowledge.jsonl"):
    if not nodes_mapping or root_index not in nodes_mapping: return []
    
    r = nodes_mapping[root_index]
    source_sections = [r['name']]
    FORCE_JSON_PROMPT = "\n\nIMPORTANT: Extract expert database rules. Respond ONLY with a JSON object: {\"rule\": {\"name\": \"...\", \"content\": \"...\", \"metrics\": [], \"steps\": \"...\"}}. No chat."

    messages = RULES_EXTRACTION_PROMPT_MSG + MSG(r['full_summary'] + FORCE_JSON_PROMPT)
    fail_time = 0
    
    print(colored(f"--- 正在从节点 {root_index} 提取知识 ---", "magenta"))

    while iteration > 0 and fail_time < 5:
        response = llm.Query(messages, functions=[LOOKUP_FUNCTION, SUBMIT_RULE_FUNCTION])
        rule_data = None

        # 尝试多种解析方式
        if response and "function_call" in response:
            try: rule_data = ast.literal_eval(response["function_call"]["arguments"].strip())
            except: pass
        elif response and "content" in response:
            try:
                json_match = re.search(r'\{.*\}', response["content"], re.DOTALL)
                if json_match: rule_data = ast.literal_eval(json_match.group().strip())
            except: pass

        if rule_data:
            rules = [rule_data] if isinstance(rule_data, dict) else rule_data
            for r_item in rules:
                actual_rule = r_item.get('rule', r_item)
                new_knowledge = {'source_sections': str(source_sections), 'rule': actual_rule}
                
                # --- 终极优雅：逐行追加 JSONL，永不乱码 ---
                with open(target_file, 'a', encoding='utf-8') as wf:
                    wf.write(json.dumps(new_knowledge, ensure_ascii=False) + '\n')
                
                print(colored(f"Saved Rule: {str(actual_rule.get('name','未命名'))}", "cyan"))
            
            messages += [{"role": "assistant", "content": f"Saved: {str(rule_data)[:50]}"}]
        else:
            fail_time += 1
        
        iteration -= 1
        if count_num_tokens(messages) > 8000: break
    return []

class DocumentExtractionArgs:
    def __init__(self, backend="openai_gpt-4", doc="./docs/overall_guide", root_index="1", summary_min_length=400, num_iteration=10, iteration_gap=2, clear_cache=True):
        self.backend = backend
        self.doc = doc
        self.root_index = root_index
        self.summary_min_length = summary_min_length
        self.num_iteration = num_iteration
        self.iteration_gap = iteration_gap
        self.clear_cache = clear_cache
        self.llm = None

def DocumentExtraction(args):
    if args.clear_cache: clear_cache()
    target_dir = "extracted_knowledge_test"
    args.llm = LLMCore(backend=args.backend)
    Initialize(args.doc, target_dir)
    nodes, nodes_structure = CascadingSummary(args)
    if not nodes: return False
    nodes_mapping = {node['id_str']: node for node in nodes}
    target_file = os.path.join(args.doc, target_dir, "extracted_knowledge_test.jsonl")
    ExtractKnowledge(nodes_mapping, root_index=args.root_index, llm=args.llm, iteration=args.num_iteration, iteration_gap=args.iteration_gap, source_file=args.doc, target_file=target_file)
    return True

def pdf_to_text_chunks(pdf_path, output_dir):
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    reader = pypdf.PdfReader(pdf_path)
    for i, page in enumerate(reader.pages):
        content = page.extract_text()
        with open(os.path.join(output_dir, f"1.{i+1} Page_{i+1}.txt"), "w", encoding="utf-8") as f:
            f.write(content)

if __name__=="__main__":
    source_folder = "../knowledge_base/samples"
    pdf_name = "29种性能异常与根因分析.pdf"
    full_pdf_path = os.path.join(source_folder, pdf_name)
    target_doc_dir = "./docs/db_expert_kb"
    
    # 第一次运行请取消下面一行的注释以切割PDF
    # pdf_to_text_chunks(full_pdf_path, os.path.join(target_doc_dir, "raw"))

    print(colored(f"--- 开始全书知识提取 (1.2 - 1.19) ---", "green"))
    
    for page_num in range(2, 20): 
        current_index = f"1.{page_num}"
        print(colored(f"\n🚀 正在攻克第 {current_index} 页...", "magenta"))
        
        args_obj = DocumentExtractionArgs(
            backend="deepseek-chat", 
            doc=target_doc_dir, 
            root_index=current_index, 
            num_iteration=2,  # 每页提2次，效率与质量的平衡点
            clear_cache=False 
        )
        DocumentExtraction(args_obj)

    print(colored("\n🏆 全书知识提取任务大功告成！", "cyan"))