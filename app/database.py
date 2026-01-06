import pymysql
import os
from pymysql.cursors import DictCursor
from dotenv import load_dotenv  # 需要安装：pip install python-dotenv

class MySQLConnector:
    def __init__(self):
        # 仅替换：从.env读取配置（替代原config.json）
        self.config = self._load_config()
        self.connection = None
        self.cursor = None

    def _load_config(self):
        """从.env文件读取配置（无默认值，仅读取环境变量）"""
        try:
            # 加载.env文件（路径和原config.json保持一致）
            env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
            load_dotenv(dotenv_path=env_path)
            
            # 纯读取环境变量，无任何默认值
            base_config = {
                "host": os.getenv("DB_HOST"),
                "port": os.getenv("DB_PORT"),
                "user": os.getenv("DB_USER"),
                "password": os.getenv("DB_PASSWORD"),
                "database": os.getenv("DB_DATABASE"),
                "charset": os.getenv("DB_CHARSET"),
                "autocommit": os.getenv("DB_AUTOCOMMIT")
            }
            
            # 过滤掉值为None的项（未配置的环境变量）
            base_config = {k: v for k, v in base_config.items() if v is not None}
            
            # 保留原逻辑：转换port为整数 + 合并必要参数
            if "port" in base_config:
                base_config["port"] = int(base_config["port"])
            if "autocommit" in base_config:
                base_config["autocommit"] = base_config["autocommit"].lower() == "true"
            
            base_config.update({
                "cursorclass": DictCursor,
                "autocommit": True  # 保留原代码的autocommit强制设置
            })
            return base_config
        except Exception as e:
            print(f"⚠️ 配置文件读取失败，将使用空配置: {e}")
            return {}

    def connect(self):
        if not self.config:
            print("❌ 错误：没有可用的数据库配置信息")
            return False
        try:
            # 保留原逻辑：解包配置字典
            self.connection = pymysql.connect(**self.config)
            self.cursor = self.connection.cursor()
            return True
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            return False

    def query_user(self, username):
        if not self.cursor:
            return None
        sql = "SELECT * FROM user_login WHERE username = %s"
        self.cursor.execute(sql, (username,))
        return self.cursor.fetchone()

    def close(self):
        if self.cursor: self.cursor.close()
        if self.connection: self.connection.close()

# 实例化
db = MySQLConnector()

# 保留原全局数组（完全不变）
unactivated_macs = []  # 存储未激活的MAC地址
activation_codes = []  # 存储对应的激活码