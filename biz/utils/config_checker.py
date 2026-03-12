import os
import shutil

from dotenv import load_dotenv

from biz.utils.log import logger

# 指定环境变量文件路径
ENV_FILE_PATH = "conf/.env"
load_dotenv(ENV_FILE_PATH)


REQUIRED_ENV_VARS = [
    "GITLAB_ACCESS_TOKEN",
]


def check_env_vars():
    """检查环境变量"""
    missing_vars = [var for var in REQUIRED_ENV_VARS if var not in os.environ]
    if missing_vars:
        logger.warning(f"缺少环境变量: {', '.join(missing_vars)}")
    else:
        logger.info("所有必要的环境变量均已设置。")


def check_codex():
    logger.info("正在检查 codex 可执行文件...")
    if shutil.which("codex"):
        logger.info("codex 可执行文件存在。")
    else:
        logger.error("未找到 codex 可执行文件，请检查 PATH。")


def check_cache_dir():
    cache_dir = os.path.expanduser(os.getenv("CODEREVIEW_CACHE_DIR", "~/.cache/codereview"))
    logger.info("正在检查缓存目录: %s", cache_dir)
    try:
        os.makedirs(cache_dir, exist_ok=True)
        logger.info("缓存目录可用。")
    except OSError as exc:
        logger.error("缓存目录不可用: %s", exc)


def check_config():
    """主检查入口"""
    logger.info("开始检查配置项...")
    check_env_vars()
    check_codex()
    check_cache_dir()
    logger.info("配置项检查完成。")
