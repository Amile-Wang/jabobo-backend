from fastapi import APIRouter, HTTPException, Header, Query
from app.database import db
import json

router = APIRouter()

# 1. 获取 ID 列表接口
@router.get("/user/jabobo_ids")
async def get_user_jabobo_ids(
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()
        if not user or user.get('session_token') != authorization:
            raise HTTPException(status_code=401, detail="身份验证失败")

        db.cursor.execute("SELECT jabobo_id FROM user_personas WHERE username = %s", (x_username,))
        rows = db.cursor.fetchall()
        ids = [row['jabobo_id'] for row in rows]
        
        print(f"📋 [LIST DEVICES] User: {x_username} | Found IDs: {ids}")
        return {"success": True, "jabobo_ids": ids}
    finally:
        db.close()

# 2. 获取【特定设备】的配置
@router.get("/user/config")
async def get_user_config(
    jabobo_id: str = Query(...), 
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    if not db.connect(): raise HTTPException(status_code=500)
    try:
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()
        if not user or user.get('session_token') != authorization:
            raise HTTPException(status_code=401)

        sql = "SELECT personas, memory FROM user_personas WHERE username = %s AND jabobo_id = %s"
        db.cursor.execute(sql, (x_username, jabobo_id))
        config = db.cursor.fetchone()
        
        raw_persona = config.get('personas', "[]") if config else "[]"
        memory_data = config.get('memory', "") if config else ""

        # --- 详细日志 ---
        print("-" * 50)
        print(f"🔍 [GET CONFIG] Request Received")
        print(f"   👤 User: {x_username}")
        print(f"   🆔 Target Device: {jabobo_id}")
        print(f"   📦 Data Found: {len(raw_persona)} chars of persona, {len(memory_data)} chars of memory")
        print("-" * 50)

        return {
            "success": True, 
            "data": {
                "persona": raw_persona,
                "memory": memory_data,
                "voice_status": "已就绪",
                "kb_status": "已同步"
            }
        }
    finally:
        db.close()

# 3. 同步【特定设备】的配置
@router.post("/user/sync-config")
async def sync_config(
    payload: dict, 
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    if not db.connect(): raise HTTPException(status_code=500)
    try:
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()
        if not user or user.get('session_token') != authorization:
            raise HTTPException(status_code=401)

        # 核心参数解析
        jabobo_id = payload.get('jabobo_id') 
        persona_json = payload.get('persona', '[]')
        memory = payload.get('memory', '')

        # --- 增强型同步日志 ---
        print("=" * 50)
        print(f"🚀 [SYNC CONFIG] Inbound Payload Analysis")
        print(f"   👤 User: {x_username}")
        print(f"   🆔 Device ID from payload: {jabobo_id}")
        print(f"   📝 Persona Content: {persona_json[:100]}...") # 只打印前100个字符防止刷屏
        print(f"   🧠 Memory Content: {memory[:100]}...")
        print("=" * 50)

        if not jabobo_id:
            print("❌ Error: Missing jabobo_id in payload!")
            raise HTTPException(status_code=400, detail="缺少 jabobo_id")

        sql = """
            INSERT INTO user_personas (username, jabobo_id, personas, memory) 
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE personas = VALUES(personas), memory = VALUES(memory)
        """
        db.cursor.execute(sql, (x_username, jabobo_id, persona_json, memory))
        
        print(f"✅ [DATABASE UPDATED] Target: {x_username} / {jabobo_id}")
        
        return {"success": True, "message": f"设备 {jabobo_id} 数据同步成功"}
    except Exception as e:
        print(f"🔥 Sync Critical Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()