#!/bin/bash

# 在终端运行该指令以启动脚本：sh /var/local/restart.sh

# 重启前后端服务脚本

# 设置颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}开始重启前后端服务...${NC}"

# 获取脚本所在目录的绝对路径
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# 根据脚本位置计算项目根目录
PROJECT_ROOT=$SCRIPT_DIR

# 停止之前运行的进程
echo -e "${YELLOW}停止正在运行的服务...${NC}"

# 停止后端进程 (端口 8007)
if lsof -i :8007 -t >/dev/null 2>&1; then
    echo -e "${YELLOW}停止后端服务 (端口 8007)...${NC}"
    lsof -ti:8007 | xargs kill -9 > /dev/null 2>&1
fi

# 停止前端进程 (端口 8006)
if lsof -i :8006 -t >/dev/null 2>&1; then
    echo -e "${YELLOW}停止前端服务 (端口 8006)...${NC}"
    lsof -ti:8006 | xargs kill -9 > /dev/null 2>&1
fi

# 停止可能在5000端口的后端进程
if lsof -i :5000 -t >/dev/null 2>&1; then
    echo -e "${YELLOW}停止后端服务 (端口 5000)...${NC}"
    lsof -ti:5000 | xargs kill -9 > /dev/null 2>&1
fi

sleep 2

# 进入后端目录并重启后端服务
echo -e "${GREEN}启动后端服务...${NC}"
cd "$PROJECT_ROOT/jobobo-backend"

# 确保数据库运行
echo -e "${YELLOW}启动数据库服务...${NC}"
docker restart jabobo_final_mysql || docker start jabobo_final_mysql || echo "警告: 数据库容器可能不存在，请检查Docker环境"


# 启动后端服务 (在后台运行)
nohup uvicorn app.main:app --host 0.0.0.0 --port 8007 --reload > backend.log 2>&1 &

# 等待后端启动
sleep 5

# 进入前端目录并重启前端服务
echo -e "${GREEN}启动前端服务...${NC}"
cd "$PROJECT_ROOT/jobobo-manager"

# 安装依赖（如果需要）
npm install > /dev/null 2>&1

# 启动前端服务 (在后台运行)
nohup npm run dev > frontend.log 2>&1 &

echo -e "${GREEN}前后端服务已重启完成！${NC}"
echo -e "${GREEN}后端服务地址: http://localhost:8007${NC}"
echo -e "${GREEN}前端服务地址: http://localhost:8006${NC}"

# 显示正在运行的进程
echo -e "${YELLOW}当前运行的服务:${NC}"
if lsof -i :8007 -t >/dev/null 2>&1; then
    echo -e "${GREEN}后端服务正在运行 (端口 8007)${NC}"
else
    echo -e "${RED}后端服务启动失败 (端口 8007)${NC}"
fi

# 增加更可靠的前端服务检查机制
sleep 3
if lsof -i :8006 -t >/dev/null 2>&1; then
    echo -e "${GREEN}前端服务正在运行 (端口 8006)${NC}"
else
    # 再次等待并检查
    sleep 5
    if lsof -i :8006 -t >/dev/null 2>&1; then
        echo -e "${GREEN}前端服务正在运行 (端口 8006)${NC}"
    else
        echo -e "${RED}前端服务启动失败 (端口 8006)${NC}"
        echo -e "${YELLOW}请检查 /var/local/jobobo-manager/frontend.log 文件获取详细信息${NC}"
    fi
fi