#!/bin/bash

# --- 配置区 ---
DB_CONTAINER="jabobo_final_mysql"
DB_USER="root"
DB_PASS="123456"
DB_NAME="jabobo"
DB_HOST="127.0.0.1"
DB_PORT="3307"

# 基础命令前缀
MYSQL_CMD="docker exec -i $DB_CONTAINER mysql -h $DB_HOST -P $DB_PORT -u $DB_USER -p$DB_PASS $DB_NAME"

# 如果没有输入参数，进入交互模式
if [ -z "$1" ]; then
    echo "💡 提示: 进入交互模式 (输入 quit 退出)"
    docker exec -it $DB_CONTAINER mysql -h $DB_HOST -P $DB_PORT -u $DB_USER -p$DB_PASS $DB_NAME
    exit 0
fi

# 快捷指令映射
case "$1" in
    "list")
        echo "📋 正在查看所有设备绑定情况..."
        $MYSQL_CMD -e "SELECT username, jabobo_id, memory FROM user_personas;"
        ;;
    "index")
        echo "🔍 正在检查表索引..."
        $MYSQL_CMD -e "SHOW INDEX FROM user_personas;"
        ;;
    "users")
        echo "👤 正在查看所有用户账号..."
        $MYSQL_CMD -e "SELECT id, username, role FROM user_login;"
        ;;
    *)
        # 如果不是快捷指令，则直接执行传入的 SQL 语句
        $MYSQL_CMD -e "$1"
        ;;
esac