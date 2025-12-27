from fastapi import APIRouter, HTTPException, Header
from app.database import db
import json

router = APIRouter()

@router.get("/user/config")
async def get_user_config(
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 1. 身份校验
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()
        if not user or user.get('session_token') != authorization:
            raise HTTPException(status_code=401, detail="身份验证失败")

        # 2. 查询数据
        db.cursor.execute(
            "SELECT content, memory FROM user_personas WHERE username = %s", 
            (x_username,)
        )
        config = db.cursor.fetchone()
        
        # 调试日志
        print(f"--- [GET] User: {x_username} ---")
        persona_data = config.get('content', "[]") if config else "[]"
        memory_data = config.get('memory', "") if config else ""
        print(f"DB Persona: {persona_data[:30]}...")
        print(f"DB Memory: {memory_data}")

        return {
            "success": True, 
            "data": {
                "persona": persona_data,
                "memory": memory_data,
                "voice_status": "已就绪",
                "kb_status": "已同步"
            }
        }
    finally:
        db.close()

@router.post("/user/sync-config")
async def sync_config(
    payload: dict, 
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    if not db.connect():
        raise HTTPException(status_code=500)
        
    try:
        # 身份校验
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()
        if not user or user.get('session_token') != authorization:
            raise HTTPException(status_code=401)

        # 获取前端数据
        persona_json = payload.get('persona', '[]')
        memory = payload.get('memory', '')

        # 调试日志：核对发送过来的数据
        print(f"--- [SYNC] User: {x_username} ---")
        print(f"Target Memory: {memory}")

        # 核心修复：确保 (username, content, memory) 的顺序与 SQL 对应
        sql = """
            INSERT INTO user_personas (username, content, memory) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                content = VALUES(content), 
                memory = VALUES(memory)
        """
        # 参数元组顺序必须严格匹配: 1.username, 2.persona_json, 3.memory
        db.cursor.execute(sql, (x_username, persona_json, memory))
        
        return {"success": True, "message": "全量数据同步成功"}
    except Exception as e:
        print(f"Sync Error: {str(e)}")
        raise HTTPException(status_code=500, detail="服务器内部错误")
    finally:
        db.close()