import json
import os

f_in = r"D:\Graduation_Project\DB-GPT\DB-GPT-main\doc2knowledge\docs\db_expert_kb\extracted_knowledge_test\extracted_knowledge_test.jsonl"
f_out_path = "Final_Expert_Knowledge_Base.md"

unique_content = set()
final_rules = []

def add_rule(data):
    rule = data.get("rule", {})
    content = rule.get("content", rule.get("answer", ""))
    if content and content not in unique_content:
        final_rules.append(rule)
        unique_content.add(content)

if os.path.exists(f_in):
    with open(f_in, "r", encoding="utf-8") as f:
        # 核心逻辑：尝试全文件读取（处理大字典），如果失败则逐行读取（处理追加行）
        full_content = f.read().strip()
        
        # 尝试法 1: 解析整个 JSON 字典 (处理你最开始生成的格式)
        try:
            big_data = json.loads(full_content)
            if isinstance(big_data, dict):
                for k, v in big_data.items():
                    add_rule(v)
        except:
            pass

        # 尝试法 2: 逐行解析 (处理后来追加的 JSONL 格式)
        for line in full_content.split('\n'):
            line = line.strip()
            if not line: continue
            try:
                # 过滤掉开头结尾可能干扰的大括号
                if line.startswith('{') and line.endswith('}') or line.endswith(','):
                    line = line.rstrip(',')
                    data = json.loads(line)
                    add_rule(data)
            except:
                continue

    with open(f_out_path, "w", encoding="utf-8") as f:
        f.write("# 📘 数据库性能异常诊断专家知识库\n\n| 规则名称 | 核心知识内容 |\n| :--- | :--- |\n")
        for r in final_rules:
            name = r.get("name", r.get("question", "未命名")).replace("\n", " ").strip()
            cont = r.get("content", r.get("answer", "-")).replace("\n", " ").strip()
            f.write(f"| {name[:40]} | {cont} |\n")
            
    print(f"✨ 这一波收割了 {len(final_rules)} 条核心专家规则！")
else:
    print(f"找不到文件: {f_in}")