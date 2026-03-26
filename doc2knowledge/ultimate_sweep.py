import os, json, re

# 基础根目录
base_dir = r"D:\Graduation_Project\DB-GPT\DB-GPT-main"

# 定义我们要搜刮的重点区域 (不写死完整路径，只写关键部分)
SEARCH_PLAN = [
    {"label": "专家库/运维SOP", "path_part": "doc2knowledge\docs", "ext": ".jsonl"},
    {"label": "监控/可视化", "path_part": "materials\help_documents", "ext": ".md"},
    {"label": "SQL改写/优化器", "path_part": "multiagents\tools\query_advisor", "ext": ".txt"}
]

output_file = "Final_Master_Knowledge_Base.md"
results = []
unique_check = set()

def add_data(label, title, content):
    c_clean = str(content).replace("\n", " ").replace("|", "-").strip()
    if c_clean and c_clean not in unique_check and len(c_clean) > 10:
        results.append((label, str(title).strip(), c_clean))
        unique_check.add(c_clean)

print("🚜 启动终极收割程序，正在地毯式搜寻文件...")

# 递归遍历所有相关目录，防止路径写错
for root, dirs, files in os.walk(base_dir):
    for file in files:
        full_path = os.path.join(root, file)
        
        # 匹配我们想要的知识源
        for plan in SEARCH_PLAN:
            if plan["path_part"].lower() in full_path.lower() and file.endswith(plan["ext"]):
                print(f"📖 发现目标: {full_path}")
                
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    # 1. 解析 JSONL (PDF/Word 的提取结果)
                    if file.endswith(".jsonl"):
                        raw = f.read()
                        rules = re.findall(r'\"rule\"\s*:\s*(\{.*?\})', raw, re.DOTALL)
                        for r_str in rules:
                            try:
                                # 修复括号并解析
                                if r_str.count('{') > r_str.count('}'): r_str += '}'
                                data = json.loads(r_str)
                                add_data(plan["label"], data.get("name") or data.get("question"), data.get("content") or data.get("answer"))
                            except: continue
                    
                    # 2. 解析 MD (监控指标)
                    elif file.endswith(".md"):
                        sections = f.read().split('##')
                        for s in sections:
                            lines = s.strip().split('\n')
                            if len(lines) > 1:
                                add_data(plan["label"], lines[0], " ".join(lines[1:]))

                    # 3. 解析 TXT (SQL 规则和 API)
                    elif file.endswith(".txt"):
                        for line in f:
                            if len(line.strip()) > 15: # 过滤掉太短的行
                                add_data(plan["label"], "核心规则/接口", line)

# 写入终极成果
with open(output_file, 'w', encoding='utf-8') as f:
    f.write("# 🏆 DB-GPT 全场景数据库专家知识库 (毕设最终大合集)\n\n")
    f.write("> 覆盖范围：PDF专家手册、Word应急方案、Prometheus监控、Grafana配置、SQL改写规则、API接口定义\n\n")
    f.write("| 知识维度 | 关键项/规则 | 详细内容 |\n| :--- | :--- | :--- |\n")
    for lab, tit, con in results:
        f.write(f"| {lab} | {tit[:40]} | {con} |\n")

print(f"\n✨ 收割大圆满！")
print(f"📊 最终抓取知识点总数: {len(results)} 条")
print(f"📂 成果文件: {os.path.abspath(output_file)}")