# LILAC 模板变量泛化优化说明

## 1. 问题背景

上一阶段已经修复了 `timestamp`、`level`、`component` 为空的问题，但重新测试后发现模板层面仍存在变量泛化不足：

```text
PacketResponder 1 for block blk_38865049064139660 terminating
Created MRAppMaster for application appattempt_1445144423722_0020_000001
time: 0.<*>
status: 200
```

这些内容在官方金标准中通常应被泛化为：

```text
PacketResponder <*> for block <*> terminating
Created MRAppMaster for application <*>
time: <*>
status: <*>
```

## 2. 修改文件

```text
server/diagnose/lilac/preprocessor.py
server/diagnose/lilac/parser.py
server/diagnose/lilac/llm_template_extractor.py
tests/lilac/test_preprocessor.py
docs/lilac_template_generalization_fix.md
```

## 3. 修改目标

本次优化不是改变 LILAC 论文思路，而是减少当前工程实现中过早 `static` / `Drain3` 导致的模板不泛化问题，使流程更接近：

```text
cache hit -> use cache
cache miss + dynamic body -> LLM
LLM failed -> Drain3
```

## 4. 主要修改

### 4.1 增强 mask 规则

在 `preprocessor.py` 中扩展 `MASK_PATTERNS`，新增对日志领域动态变量的识别：

```text
blk_-6952295868487656571
appattempt_1445144423722_0020_000001
application_1445144423722_0020
container_1445144423722_0020_01_000001
status: 200
len: 1893
time: 0.2477829
"GET /v2/... HTTP/1.1"
PacketResponder 1
```

优化后，代表样例的 `masked_body` 变为：

```text
HDFS:
PacketResponder <*> for block <*> terminating

Hadoop:
Created MRAppMaster for application <*>

OpenStack:
<*> "GET <*>" status: <*> len: <*> time: <*>
```

### 4.2 收紧 static 快捷路径

原逻辑中，只要 `masked_body == body`，就可能直接走 `static`。

现在新增 `_looks_dynamic_body()` 判断。如果日志正文里仍存在明显动态特征，例如 block id、application id、UUID、IP、长数字、浮点数、HTTP 请求等，即使 mask 没命中，也不会直接当成 static 模板。

### 4.3 增加模板归一化

在 `parser.py` 中新增 `_normalize_template()`，用于修复 LLM 或 Drain3 输出中的半泛化模板，例如：

```text
time: 0.<*>     -> time: <*>
status: 200     -> status: <*>
blk_<*>         -> <*>
"GET <*> HTTP/1.1" -> "GET <*>"
```

### 4.4 优化 LLM Prompt

在 `llm_template_extractor.py` 中增强 prompt，明确告诉 LLM：

```text
block id
application id
container id
request id
status code
byte length
duration
floating point cost
```

这些都应该被视为运行时变量，并加入 HDFS、Hadoop、OpenStack 风格示例。

## 5. 与论文思路的关系

LILAC 论文的主线是：

```text
adaptive parsing cache -> cache miss -> LLM parsing -> cache update
```

本次修改没有绕开 cache，也没有让所有日志无脑调用 LLM，而是避免明显动态日志被误判为 `static`，使它们在 cache miss 后更有机会进入 LLM 或 Drain3 解析。因此这是对当前实现的工程修正，而不是改变论文思路。

## 6. 验证命令

```bat
cd /d C:\Users\liuPP\Desktop\sundb-ai-ops-feat-lilac-drain3
python -m pytest tests\lilac\test_preprocessor.py tests\lilac\test_parser_optimizations.py -q
```

当前验证结果：

```text
31 passed
```

`py_compile` 在当前环境中遇到 `__pycache__` 写权限问题，但相关测试已正常导入并执行通过。

## 7. 重新测试注意事项

重新跑三个数据集前必须清空缓存，否则旧模板会影响新结果：

```bat
curl.exe -X DELETE http://localhost:7861/diagnose/lilac/cache
```

建议输出新文件名，例如：

```text
HDFS_2k_lilac_qwen_generalized.json
Hadoop_2k_lilac_qwen_generalized.json
OpenStack_2k_lilac_qwen_generalized.json
```

