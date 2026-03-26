import json, os, re

# 路径定义
PATHS = {
    "PDF理论": r"D:\Graduation_Project\DB-GPT\DB-GPT-main\doc2knowledge\docs\db_expert_kb\extracted_knowledge_test\extracted_knowledge_test.jsonl",
    "Word实操": r"D:\Graduation_Project\DB-GPT\DB-GPT-main\doc2knowledge\docs\test_enmo\extracted_knowledge_test\extracted_knowledge_test.jsonl",
    "监控指标": r"D:\Graduation_Project\DB-GPT\DB-GPT-main\materials\help_documents\prometheus.md",
    "SQL优化": r"D:\Graduation_Project\DB-GPT\DB-GPT-main\multiagents\tools\query_advisor\query_rewrite\available_rewrite_rules.txt"
}

output_file = "Ultimate_Expert_Knowledge_Base.md"
final_knowledge = []
unique_cont = set()

def add_entry(name, cont, source):
    name = str(name).replace("\n", " ").strip()
    cont = str(cont).replace("\n", " ").replace("|", " ").strip()
    if cont and cont not in unique_cont and len(cont) > 5:
        final_knowledge.append((name, cont, source))
        unique_cont.add(cont)

print("🚀 开始暴力全量收割...")

# 1. 暴力扫描 JSONL (针对 PDF 和 Word)
for label, path in PATHS.items():
    if not os.path.exists(path) or not path.endswith(".jsonl"): continue
    print(f"🔍 正在深入探测: {label}")
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        raw = f.read()
        # 使用正则把所有形如 "rule": { ... } 的内容全抠出来
        rules = re.findall(r'\"rule\"\s*:\s*(\{.*?\})', raw, re.DOTALL)
        for r_str in rules:
            try:
                # 修复可能存在的截断
                if r_str.count('{') > r_str.count('}'): r_str += '}'
                r_obj = json.loads(r_str)
                add_entry(r_obj.get('name') or r_obj.get('question'), 
                          r_obj.get('content') or r_obj.get('answer'), label)
            except: continue

# 2. 扫描 MD (Prometheus)
if os.path.exists(PATHS["监控指标"]):
    with open(PATHS["监控指标"], 'r', encoding='utf-8') as f:
        for p in f.read().split('##')[1:]:
            lines = p.strip().split('\n')
            add_entry(lines[0], " ".join(lines[1:])[:300], "监控指标")

# 3. 扫描 TXT (SQL 优化)
if os.path.exists(PATHS["SQL优化"]):
    with open(PATHS["SQL优化"], 'r', encoding='utf-8') as f:
        for line in f:
            if ':' in line:
                n, c = line.split(':', 1)
                add_entry(n, c, "SQL优化")

# 写入大报告
with open(output_file, 'w', encoding='utf-8') as f:
    f.write("# 🏆 DB-GPT 全场景数据库专家知识库 (毕设终极版)\n\n| 来源维度 | 知识点/规则名称 | 核心知识内容 |\n| :--- | :--- | :--- |\n")
    for n, c, s in final_knowledge:
        f.write(f"| {s} | {n[:30]} | {c} |\n")

print(f"\n✨ 收割完毕！")
print(f"📊 总计抓取有效知识点: {len(final_knowledge)} 条 (之前是 18 条)")
print(f"📂 成果文件: {os.path.abspath(output_file)}")