from fastapi import APIRouter, HTTPException, Header, Query, Body
from app.database import db, unactivated_macs, activation_codes
import json
from app.utils.security import verify_user
router = APIRouter()

# 核心映射：客户端类型 → 对应token字段（默认取web）
CLIENT_TOKEN_MAP = {
    "web": "web_token",
    "android": "android_token",
    "ios": "ios_token"
}


# 1. 获取 ID 列表接口
@router.get("/user/jabobo_ids")
async def get_user_jabobo_ids(
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    if not db.connect(): 
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        verify_user(x_username, authorization)
        # 查询该用户绑定的所有设备
        db.cursor.execute("SELECT jabobo_id FROM user_personas WHERE username = %s", (x_username,))
        rows = db.cursor.fetchall()
        ids = [row['jabobo_id'] for row in rows]
        print(f"📋 [LIST] User: {x_username} | Devices: {ids}")
        return {"success": True, "jabobo_ids": ids}
    finally:
        db.close()

# 2. 绑定新设备 (Create)
@router.post("/user/bind")
async def bind_jabobo(
    payload: dict = Body(...),
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    jabobo_id = payload.get("jabobo_id")
    if not jabobo_id: 
        raise HTTPException(status_code=400, detail="缺少设备 ID")
    
    # 优化绑定流程：检查是否为配对码，如果是则使用对应的MAC地址
    if jabobo_id in activation_codes:
        # 根据配对码找到对应的MAC地址
        activation_code_index = activation_codes.index(jabobo_id)
        jabobo_id = unactivated_macs[activation_code_index]
        print(f"🔑 [ACTIVATION] Pairing code {jabobo_id} matched MAC address {jabobo_id}")

    if not db.connect(): 
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        verify_user(x_username, authorization)

        # 检查设备是否已绑定
        db.cursor.execute(
            "SELECT jabobo_id FROM user_personas WHERE username = %s AND jabobo_id = %s",
            (x_username, jabobo_id)
        )
        if db.cursor.fetchone():
            return {"success": False, "message": "该设备已在您的列表中"}

        # 插入新设备，赋予初始 JSON 结构
        default_persona = json.dumps([{"id": "p1", "name": "默认人设", "content": "你好，我是新绑定的捷宝宝。"}])
        sql = "INSERT INTO user_personas (username, jabobo_id, personas, memory) VALUES (%s, %s, %s, %s)"
        db.cursor.execute(sql, (x_username, jabobo_id, default_persona, "尚无记忆"))
        # 提交事务（新增：确保数据写入）
        db.cursor.connection.commit()
        
        print(f"✨ [BIND] User: {x_username} | New Device: {jabobo_id}")
        return {"success": True, "message": "绑定成功"}
    finally:
        db.close()

# 3. 解绑设备 (Delete)
@router.delete("/user/unbind")
async def unbind_jabobo(
    jabobo_id: str = Query(...),
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    if not db.connect(): 
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        verify_user(x_username, authorization)
        
        sql = "DELETE FROM user_personas WHERE username = %s AND jabobo_id = %s"
        db.cursor.execute(sql, (x_username, jabobo_id))
        # 提交事务（新增）
        db.cursor.connection.commit()
        
        if db.cursor.rowcount == 0:
            return {"success": False, "message": "未找到该设备或无权操作"}

        print(f"🗑️ [UNBIND] User: {x_username} | Removed Device: {jabobo_id}")
        return {"success": True, "message": "解绑成功"}
    finally:
        db.close()

# 4. 获取特定设备配置 (Read)
@router.get("/user/config")
async def get_user_config(
    jabobo_id: str = Query(...), 
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    if not jabobo_id:
        return {"success": True, "data": {"persona": "[]", "memory": ""}}

    if not db.connect(): 
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        verify_user(x_username, authorization)

        sql = "SELECT personas, memory FROM user_personas WHERE username = %s AND jabobo_id = %s"
        db.cursor.execute(sql, (x_username, jabobo_id))
        config = db.cursor.fetchone()
        
        raw_persona = config.get('personas', "[]") if config else "[]"
        memory_data = config.get('memory', "") if config else ""

        print(f"🔍 [GET] User: {x_username} | Device: {jabobo_id} | Persona length: {len(raw_persona)}")
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

# 5. 设备换绑接口
@router.put("/user/rebind")
async def rebind_jabobo(
    payload: dict = Body(...),
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    old_id = payload.get("old_jabobo_id")
    new_id = payload.get("new_jabobo_id")

    if not old_id or not new_id:
        raise HTTPException(status_code=400, detail="缺少旧设备或新设备 ID")

    if not db.connect(): 
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        verify_user(x_username, authorization)

        # 检查新 ID 是否已被占用
        db.cursor.execute(
            "SELECT username FROM user_personas WHERE jabobo_id = %s", 
            (new_id,)
        )
        existing = db.cursor.fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="新设备 ID 已被绑定")

        # 执行换绑：更新 jabobo_id 字段
        sql = """
            UPDATE user_personas 
            SET jabobo_id = %s 
            WHERE username = %s AND jabobo_id = %s
        """
        db.cursor.execute(sql, (new_id, x_username, old_id))
        # 提交事务（新增）
        db.cursor.connection.commit()
        
        if db.cursor.rowcount == 0:
            return {"success": False, "message": "原设备不存在或无权操作"}

        print(f"🔄 [REBIND] User: {x_username} | {old_id} -> {new_id}")
        return {"success": True, "message": "设备换绑成功，人设已迁移"}
    finally:
        db.close()