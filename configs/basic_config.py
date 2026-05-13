import logging
import os
import langchain
import tempfile
import shutil


# 版本号
VERSION = "0.3.0"

# 是否显示详细日志
log_verbose = False
langchain.verbose = False

# 通常情况下不需要更改以下内容

# 日志格式
LOG_FORMAT = "%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s"
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logging.basicConfig(format=LOG_FORMAT)


# 日志存储路径
LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
if not os.path.exists(LOG_PATH):
    os.mkdir(LOG_PATH)

# 确保 fastchat 日志也写入 logs/ 目录（无论从哪个入口启动）
try:
    import fastchat.constants
    fastchat.constants.LOGDIR = LOG_PATH
except ImportError:
    pass

# 临时文件目录，主要用于文件对话
BASE_TEMP_DIR = os.path.join(tempfile.gettempdir(), "chatchat")
if os.path.isdir(BASE_TEMP_DIR):
    shutil.rmtree(BASE_TEMP_DIR)
os.makedirs(BASE_TEMP_DIR, exist_ok=True)
