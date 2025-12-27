from fastapi import APIRouter, HTTPException, Header, Depends
from app.database import db

router = APIRouter()

# 这里的接口直接在参数里声明了 Header，所以 FastAPI 会强制检查 x-username
@router.get("/user/config")
async def get_user_config(
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    """
    原始版本：从 Header 直接读取用户名和 Token
    """
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 原始逻辑：校验数据库中的 session_token
        # 注意：这里需要先查用户，拿到数据库里的 token 进行对比
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()

        if not user or user.get('session_token') != authorization:
            raise HTTPException(status_code=401, detail="身份验证失败")

        # 验证通过后，再查人设数据
        db.cursor.execute(
            "SELECT content, memory FROM user_personas WHERE username = %s", 
            (x_username,)
        )
        config = db.cursor.fetchone()
        
        # 构造返回结构
        data = {
            "persona": config.get('content', "") if config else "",
            "memory": config.get('memory', "") if config else "",
            "voice_status": "已就绪",
            "kb_status": "已同步"
        }
        
        return {"success": True, "data": data}
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
        # 1. 身份校验
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()
        if not user or user.get('session_token') != authorization:
            raise HTTPException(status_code=401, detail="身份验证失败")

        persona = payload.get('persona', '')
        memory = payload.get('memory', '')

        # 2. 执行更新/插入
        sql = """
            INSERT INTO user_personas (username, content, memory) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE content = VALUES(content), memory = VALUES(memory)
        """
        # 因为你的 MySQLConnector 设置了 autocommit: True
        # 执行完下面这一行，数据就已经安全存入数据库了
        db.cursor.execute(sql, (x_username, persona, memory))
        
        # --- 删掉了引起报错的 db.conn.commit() ---
        
        return {"success": True, "message": "同步成功"}
    except Exception as e:
        print(f"同步失败报错: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()