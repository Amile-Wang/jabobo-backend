import os
import sys
from loguru import logger

# Windows 控制台编码设置
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# 1. 创建日志文件夹
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# 2. 移除 Loguru 默认的控制台输出（为了自定义格式）
logger.remove()

# 3. 配置控制台输出（带颜色，适合开发看）
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
    enqueue=True
)

# 4. 配置日志文件（适合生产环境持久化）
logger.add(
    os.path.join(LOG_DIR, "server_{time:YYYY-MM-DD}.log"),
    rotation="00:00",    # 每天凌晨 0 点自动创建一个新文件
    retention="30 days", # 自动清理 30 天前的旧日志
    compression="zip",   # 旧日志自动压缩存储
    level="DEBUG",       # 文件中记录更详细的内容
    encoding="utf-8",
    enqueue=True         # 异步写入，保证高并发下性能不受影响
)

# 导出 logger 供全局使用
__all__ = ["logger"]