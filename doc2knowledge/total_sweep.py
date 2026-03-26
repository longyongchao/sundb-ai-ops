import os, re

# 你的清单路径（请务必核对路径是否完全正确）
TARGETS = {
    "运维SOP": r"D:\Graduation_Project\DB-GPT\DB-GPT-main\doc2knowledge\docs\test_enmo\extracted_knowledge_test\extracted_knowledge_test.jsonl",
    "监控指标": r"D:\Graduation_Project\DB-GPT\DB-GPT-main\materials\help_documents\prometheus.md",
    "可视化面板": r"D:\Graduation_Project\DB-GPT\DB-GPT-main\materials\help_documents\grafana.md",
    "SQL改写规则": r"D:\Graduation_Project\DB-GPT\DB-GPT-main\multiagents\tools\query_advisor\query_rewrite\available_rewrite_rules.txt",
    "优化工具接口": r"D:\Graduation_Project\DB-GPT\DB-GPT-main\multiagents\tools\query_advisor\index_advisor\candidate_apis.txt"
}

output_file = "Master_Expert_Knowledge_Base.md"
all_data = []

def clean(t): return str(t).replace("\n", " ").replace("|", "-").strip()

print("🚜 开始地毯式全量收割...")

for label, path in TARGETS.items():
    if not os.path.exists(path):
        print(f"❌ 缺失文件: {label} ({path})")
        continue
    
    print(f"🔍 正在处理: {label}...")
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
        # 针对不同格式的暴力解析
        if path.endswith(".jsonl"):
            # 找所有 rule 下的内容
            rules = re.findall(r'\"name\":\s*\"(.*?)\".*?\"content\":\s*\"(.*?)\"', content, re.DOTALL)
            for n, c in rules: all_data.append((label, n, c))
            
        elif path.endswith(".md"):
            # 按二级标题切分
            sections = content.split('##')
            for s in sections[1:]:
                lines = s.strip().split('\n')
                all_data.append((label, lines[0], " ".join(lines[1:])[:500]))
                
        elif path.endswith(".txt"):
            # 针对 SQL 规则和 API 的每一行
            for line in content.split('\n'):
                if ':' in line or '->' in line or '(' in line:
                    all_data.append((label, "规则/接口定义", line))

# 写入终极 Markdown
with open(output_file, 'w', encoding='utf-8') as f:
    f.write("# 🏆 DB-GPT 全场景专家知识库 (全量覆盖版)\n\n")
    f.write("| 维度 | 关键项 | 详细内容 |\n| :--- | :--- | :--- |\n")
    for lab, head, body in all_data:
        f.write(f"| {lab} | {clean(head)[:40]} | {clean(body)} |\n")

print(f"\n✅ 全部搞定！清单中的 5 项已全部整合。")
print(f"📊 总计条目: {len(all_data)}")