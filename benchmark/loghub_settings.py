"""Loghub-2.0 数据集配置（14 个数据集）

每个数据集包含:
- log_file: 相对于 datasets/{mode}_dataset/ 的文件路径
- log_format: Loghub 日志头模板，<Field> 为命名字段，<Content> 为待解析正文
- regex: dataset-specific 预处理正则，匹配项替换为 <*>
"""

benchmark_settings = {
    "HDFS": {
        "log_file": "HDFS/HDFS_{mode}.log",
        "log_format": "<Date> <Time> <Pid> <Level> <Component>: <Content>",
        "regex": [r"blk_-?\d+", r"/?(\d+\.){3}\d+", (r":\d+", ":<*>")],
        "depth": 4,
        "st": 0.5,
    },
    "Hadoop": {
        "log_file": "Hadoop/Hadoop_{mode}.log",
        "log_format": "<Date> <Time> <Level> \\[<Process>\\] <Component>: <Content>",
        "regex": [r"(\d+\.){3}\d+"],
        "depth": 4,
        "st": 0.5,
    },
    "Spark": {
        "log_file": "Spark/Spark_{mode}.log",
        "log_format": "<Date> <Time> <Level> <Component>: <Content>",
        "regex": [r"(\d+\.){3}\d+", r"\b[0-9a-f]{8}\b"],
        "depth": 4,
        "st": 0.5,
    },
    "Zookeeper": {
        "log_file": "Zookeeper/Zookeeper_{mode}.log",
        "log_format": "<Date> <Time> - <Level>  \\[<Node>:<Component>@<Id>\\] - <Content>",
        "regex": [r"(/|)(\d+\.){3}\d+"],
        "depth": 4,
        "st": 0.5,
    },
    "BGL": {
        "log_file": "BGL/BGL_{mode}.log",
        "log_format": "<Label> <Timestamp> <Date> <Node> <Time> <NodeRepeat> <Type> <Component> <Level> <Content>",
        "regex": [r"core\.\d+"],
        "depth": 4,
        "st": 0.5,
    },
    "HPC": {
        "log_file": "HPC/HPC_{mode}.log",
        "log_format": "<LogId> <Node> <Component> <State> <Time> <Flag> <Content>",
        "regex": [r"=\d+"],
        "depth": 4,
        "st": 0.5,
    },
    "Thunderbird": {
        "log_file": "Thunderbird/Thunderbird_{mode}.log",
        "log_format": "<Label> <Timestamp> <Date> <User> <Month> <Day> <Time> <Location> <Component>(\\[<PID>\\])?: <Content>",
        "regex": [r"(\d+\.){3}\d+"],
        "depth": 4,
        "st": 0.5,
    },
    "Windows": {
        "log_file": "Windows/Windows_{mode}.log",
        "log_format": "<Date> <Time>, <Level>                  <Component>    <Content>",
        "regex": [r"0x.*?\s"],
        "depth": 4,
        "st": 0.7,
    },
    "Linux": {
        "log_file": "Linux/Linux_{mode}.log",
        "log_format": "<Month> <Date> <Time> <Level> <Component>(\\[<PID>\\])?: <Content>",
        "regex": [r"(\d+\.){3}\d+", r"\d{2}:\d{2}:\d{2}"],
        "depth": 6,
        "st": 0.39,
    },
    "Mac": {
        "log_file": "Mac/Mac_{mode}.log",
        "log_format": "<Month>  <Date> <Time> <User> <Component>\\[<PID>\\]( \\(<Address>\\))?: <Content>",
        "regex": [r"([\w-]+\.){2,}[\w-]+"],
        "depth": 6,
        "st": 0.7,
    },
    "OpenSSH": {
        "log_file": "OpenSSH/OpenSSH_{mode}.log",
        "log_format": "<Date> <Day> <Time> <Component> sshd\\[<Pid>\\]: <Content>",
        "regex": [r"(\d+\.){3}\d+", r"([\w-]+\.){2,}[\w-]+"],
        "depth": 6,
        "st": 0.6,
    },
    "OpenStack": {
        "log_file": "OpenStack/OpenStack_{mode}.log",
        "log_format": "<Logrecord> <Date> <Time> <Pid> <Level> <Component> \\[<ADDR>\\] <Content>",
        "regex": [r"((\d+\.){3}\d+,?)+", r"/.+?\s", r"\d+"],
        "depth": 5,
        "st": 0.5,
    },
    "Apache": {
        "log_file": "Apache/Apache_{mode}.log",
        "log_format": "\\[<Time>\\] \\[<Level>\\] <Content>",
        "regex": [r"(\d+\.){3}\d+"],
        "depth": 4,
        "st": 0.5,
    },
    "Proxifier": {
        "log_file": "Proxifier/Proxifier_{mode}.log",
        "log_format": "\\[<Time>\\] <Program> - <Content>",
        "regex": [
            r"<\d+\ssec",
            r"([\w-]+\.){2,}[\w-]+(:\d+)?",
            (r"\s*\([^)]*\)", ""),
            r"\d{2}:\d{2}(:\d{2})*",
            r"[KGTM]B",
            r"\d+",
        ],
        "depth": 3,
        "st": 0.6,
    },
    "HealthApp": {
        "log_file": "HealthApp/HealthApp_{mode}.log",
        "log_format": "<Time>\\|<Component>\\|<Pid>\\|<Content>",
        "regex": [],
        "depth": 4,
        "st": 0.2,
    },
}

DATASETS_2K = list(benchmark_settings.keys())
DATASETS_FULL = list(benchmark_settings.keys())
