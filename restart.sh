#!/bin/bash

# --- 1. 基础配置 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_ROOT="/var/local/jobobo-backend" # 后端代码绝对路径
SYS_LOG="/var/local/backend_sys.log"     # 仅记录 Uvicorn 启动/崩溃信息
ERROR_LOG="/var/local/service_error.log" # 记录脚本执行错误
PORT=8007

# 初始化/清理旧日志
> "${ERROR_LOG}"
echo -e "${GREEN}开始重启后端服务...${NC}"

# --- 2. 停止旧进程函数 ---
stop_backend() {
    local pid=$(lsof -t -i:"${PORT}")
    if [ -n "$pid" ]; then
        echo -e "${YELLOW}检测到端口 ${PORT} 已被占用 (PID: $pid)，正在停止...${NC}"
        kill -9 "$pid" >/dev/null 2>&1
        sleep 1
        echo -e "${GREEN}旧进程已清理${NC}"
    else
        echo -e "${YELLOW}端口 ${PORT} 当前未被占用${NC}"
    fi
}

# --- 3. 执行重启流程 ---

# A. 停止服务
stop_backend

# B. 启动数据库容器 (确保环境就绪)
echo -e "${YELLOW}检查并启动数据库服务...${NC}"
docker restart jabobo_final_mysql >/dev/null 2>&1 || {
    docker start jabobo_final_mysql >/dev/null 2>&1 || {
        echo -e "${RED}警告: 数据库容器启动失败，请检查 Docker 环境${NC}" >> "${ERROR_LOG}"
    }
}

# C. 启动后端
echo -e "${GREEN}正在通过 Uvicorn 启动后端...${NC}"
if [ -d "$PROJECT_ROOT" ]; then
    cd "$PROJECT_ROOT" || exit
    
    # 核心启动命令：
    # 1. 使用 --no-access-log 减少 Uvicorn 对日志的干扰，让 Loguru 专注记录业务
    # 2. 重定向到 SYS_LOG 仅为了捕捉环境/启动错误
    nohup setsid uvicorn app.main:app \
        --host 0.0.0.0 \
        --port ${PORT} \
        --no-access-log \
        > "${SYS_LOG}" 2>&1 &
    
    BACKEND_PID=$!
    echo -e "${YELLOW}后端服务已在后台运行，PID: ${BACKEND_PID}${NC}"
else
    echo -e "${RED}致命错误: 后端目录 ${PROJECT_ROOT} 不存在！${NC}" >> "${ERROR_LOG}"
    exit 1
fi

# --- 4. 状态验证 ---
echo -e "${YELLOW}等待服务初始化 (5s)...${NC}"
sleep 5

if lsof -i :${PORT} -t >/dev/null 2>&1; then
    echo -e "${GREEN}✅ 后端服务启动成功！${NC}"
    echo -e "${GREEN}服务地址: http://0.0.0.0:${PORT}${NC}"
    echo -e "\n${YELLOW}日志查看指南:${NC}"
    echo -e " 1. [业务日志] (Loguru): tail -f ${PROJECT_ROOT}/logs/server.log"
    echo -e " 2. [系统日志] (启动/崩溃): tail -f ${SYS_LOG}"
else
    echo -e "${RED}❌ 后端服务启动失败！${NC}"
    echo -e "${RED}请立即检查系统日志: tail -n 20 ${SYS_LOG}${NC}"
    exit 1
fi

# 如果有脚本错误，最后提醒
if [ -s "${ERROR_LOG}" ]; then
    echo -e "\n${RED}注意: 脚本运行期间有警告信息，请查看 ${ERROR_LOG}${NC}"
fi