from pyheaven import *
from prompts import *

import os
import json
import time
import itertools
import requests
from termcolor import colored

# config utils
def get_config(key):
    return LoadJson("config.json")[key]

def get_cache(key):
    key = key.lower().strip()
    if not ExistFile("cache.json"):
        SaveJson(dict(), "cache.json")
    
    cache = LoadJson("cache.json")
    if key in cache:
        return cache[key]
    return None

# cache utils
def update_cache(key, value, update=False):
    key = key.lower().strip()
    cache = LoadJson("cache.json")
    if update or (key not in cache):
        cache[key] = value
    SaveJson(cache, "cache.json")

def clear_cache():
    SaveJson(dict(), "cache.json")

# file utils
def str2id(id_str):
    return tuple(int(j) for j in id_str.split('.'))

def parse_id(file_name):
    return str2id(file_name.split(' ')[0])

def parse_depth(file_name):
    return len(parse_id(file_name))

def is_father(file_name1, file_name2):
    id1 = parse_id(file_name1)
    id2 = parse_id(file_name2)
    if id1 == id2[:-1]:
        return True
    elif id1 == (0,) and len(id2) == 1 and id2[0] > 0:
        return True
    return False

def id_sort(nodes, reverse=False):
    return sorted(nodes, key=lambda x: x['id'], reverse=reverse)

def topo_sort(nodes):
    nodes = id_sort(nodes)
    for i, node in enumerate(nodes):
        nodes[i]['book'] = len(node['children'])
    nodes = {node['id_str']: node for node in nodes}
    sorted_nodes = [nodes[key] for key in nodes if nodes[key]['book']==0]; head = 0
    while head < len(sorted_nodes):
        v = sorted_nodes[head]; head += 1
        if v['father']:
            nodes[v['father']]['book'] -= 1
            if not nodes[v['father']]['book']:
                sorted_nodes.append(nodes[v['father']])
    return [{k:v for k,v in node.items() if k!='book'} for node in sorted_nodes]

def read_txt(file_path):
    assert ExistFile(file_path), f"File not found: {file_path}"
    # 强制指定 encoding='utf-8'，解决 Windows 编码报错
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()

# --- 适配 DeepSeek 官方 API 的 LLM 核心类 ---
class LLMCore(object):
    def __init__(self, backend="deepseek-chat"):
        self.backend = backend
        # 即使外部传入 openai_xxx，我们也强制在这里路由到 deepseek
        self.model = "deepseek-chat"
        
    def Query(self, messages, temperature=0, functions=list(), retry_gap=1.0, timeout=10):
        # 从环境变量读取你刚才持久化保存的 Key
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print(colored("Error: OPENAI_API_KEY not found in environment variables!", "red"))
            return None

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        # 修改为 DeepSeek 官方 API 地址
        url = "https://api.deepseek.com/chat/completions"

        cur_timeout = timeout
        while cur_timeout > 0:
            try:
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": False
                }
                
                # 如果有函数调用需求
                if functions:
                    # 注意：DeepSeek 并非所有模型都完美支持 function call，
                    # 如果报错，脚本会自动尝试 retry
                    payload["functions"] = functions

                response = requests.post(url, json=payload, headers=headers, timeout=60)
                
                # 检查 HTTP 状态码
                if response.status_code == 200:
                    output = response.json()
                    if "choices" in output:
                        return output["choices"][0]["message"]
                
                # 打印具体错误信息协助调试
                print(colored(f"DeepSeek API Error (Status {response.status_code}): {response.text}", "red"))

            except Exception as e:
                print(colored(f"Connection Error: {e}. Retrying...", "yellow"))
                time.sleep(retry_gap)
            
            cur_timeout -= 1
        
        return None