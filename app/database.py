import pymysql
import json
import os
from pymysql.cursors import DictCursor

class MySQLConnector:
    def __init__(self):
        # 1. 定义配置文件路径 (假设在项目根目录)
        self.config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
        self.config = self._load_config()
        self.connection = None
        self.cursor = None

    def _load_config(self):
        """从本地 JSON 文件读取配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                base_config = json.load(f)
            
            # 2. 合并必要参数 (如 DictCursor)
            base_config.update({
                "cursorclass": DictCursor,
                "autocommit": True
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
            # 3. 解包配置字典
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