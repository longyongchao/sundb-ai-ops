import json, os
path = r'D:/Graduation_Project/DB-GPT/DB-GPT-main/doc2knowledge/docs/db_expert_kb/extracted_knowledge_test/extracted_knowledge_test.jsonl'
def run():
    if not os.path.exists(path): return print('File not found')
    with open(path, 'r', encoding='utf-8') as f: data = json.load(f)
    print('\n' + '='*40 + '\n✨ 提取到的知识预览 (中文无乱码) ✨\n' + '='*40)
    u = {}
    for k, v in data.items():
        r = v['rule']; c = r.get('content', ''); n = r.get('name', '未命名')
        if c not in u:
            u[c] = n; print(f'📍 规则: {n}\n📝 内容: {c}\n' + '-'*30)
run()