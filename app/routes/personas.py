from fastapi import APIRouter, HTTPException, Header, Depends
from app.database import db

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

        # 2. 查询数据 (content 字段现在存放的是 JSON 字符串)
        db.cursor.execute(
            "SELECT content, memory FROM user_personas WHERE username = %s", 
            (x_username,)
        )
        config = db.cursor.fetchone()
        
        return {
            "success": True, 
            "data": {
                "persona": config.get('content', "[]") if config else "[]",
                "memory": config.get('memory', "") if config else "",
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

        # 获取前端传来的 JSON 字符串化的数组
        persona_json = payload.get('persona', '[]')
        memory = payload.get('memory', '')

        sql = """
            INSERT INTO user_personas (username, content, memory) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE content = VALUES(content), memory = VALUES(memory)
        """
        db.cursor.execute(sql, (x_username, persona_json, memory))
        # 因为数据库配置了 autocommit: True，这里不需要手动 commit
        
        return {"success": True, "message": "全量人设同步成功"}
    finally:
        db.close()