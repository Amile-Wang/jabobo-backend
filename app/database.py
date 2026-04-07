import pymysql
import os
from pymysql.cursors import DictCursor
from dotenv import load_dotenv
from loguru import logger

class MySQLConnector:
    def __init__(self):
        logger.debug("正在初始化 MySQLConnector...")
        self.config = self._load_config()
        self.connection = None
        self.cursor = None

    def _load_config(self):
        """从.env文件读取配置"""
        try:
            env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
            if not os.path.exists(env_path):
                logger.warning(f"[WARN] 未找到 .env 文件: {env_path}")

            load_dotenv(dotenv_path=env_path)

            base_config = {
                "host": os.getenv("DB_HOST"),
                "port": os.getenv("DB_PORT"),
                "user": os.getenv("DB_USER"),
                "password": os.getenv("DB_PASSWORD"),
                "database": os.getenv("DB_DATABASE"),
                "charset": os.getenv("DB_CHARSET"),
                "autocommit": os.getenv("DB_AUTOCOMMIT")
            }

            base_config = {k: v for k, v in base_config.items() if v is not None}

            if "port" in base_config:
                base_config["port"] = int(base_config["port"])
            if "autocommit" in base_config:
                base_config["autocommit"] = base_config["autocommit"].lower() == "true"

            base_config.update({
                "cursorclass": DictCursor,
                "autocommit": True
            })

            logger.success("[OK] 数据库配置加载成功")
            return base_config

        except Exception as e:
            logger.exception("[ERROR] 配置文件读取发生崩溃")
            return {}

    def connect(self):
        if not self.config:
            logger.error("[ERROR] 拒绝连接：数据库配置为空，请检查 .env 文件")
            return False
        try:
            self.connection = pymysql.connect(**self.config,ssl={})
            self.cursor = self.connection.cursor()
            logger.info(f"[OK] 数据库连接已建立: {self.config.get('host')}/{self.config.get('database')}")
            return True
        except Exception as e:
            logger.error(f"[ERROR] 数据库连接失败! 错误信息: {e}")
            return False

    def query_user(self, username):
        if not self.cursor:
            logger.warning("[WARN] 尝试执行查询，但数据库游标(cursor)未初始化")
            return None
        try:
            sql = "SELECT * FROM user_login WHERE username = %s"
            logger.debug(f"[SQL] 执行查询: {sql} | 参数: {username}")
            self.cursor.execute(sql, (username,))
            return self.cursor.fetchone()
        except Exception as e:
            logger.error(f"[ERROR] 查询用户 [{username}] 失败: {e}")
            return None

    def close(self):
        try:
            if self.cursor: self.cursor.close()
            if self.connection: self.connection.close()
            logger.debug("[OK] 数据库连接已安全关闭")
        except Exception as e:
            logger.error(f"[ERROR] 关闭数据库连接时出错: {e}")

# 实例化
db = MySQLConnector()

# 保留原全局数组
unactivated_macs = []
activation_codes = []
