from fastapi import APIRouter, HTTPException, Header, Query, Body
from app.database import db, unactivated_macs, activation_codes
import json
from app.utils.security import verify_user
from loguru import logger  # 引入 loguru

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
        logger.info(f"===== [收到jabobo_ids请求] =====")
        logger.debug(f"接收的x_username: {x_username}")
        logger.debug(f"接收的Authorization（前10位）: {authorization[:10]}...")
        
        verify_user(x_username, authorization)
        logger.success(f"✅ 身份验证通过：用户名={x_username}")
        
        sql = "SELECT jabobo_id FROM user_personas WHERE username = %s"
        logger.debug(f"🔍 执行SQL：{sql} | 参数：({x_username})")
        
        db.cursor.execute(sql, (x_username,))
        rows = db.cursor.fetchall()
        
        logger.debug(f"📊 查询到的行数：{len(rows)}")
        
        ids = [row['jabobo_id'] for row in rows]
        
        logger.info(f"📋 [LIST] User: {x_username} | Devices: {ids}")
        logger.debug(f"📤 返回结果：success=True, jabobo_ids={ids}")
        
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
    
    is_activation_code = jabobo_id in activation_codes
    is_valid_mac = len(jabobo_id.strip()) == 17 and jabobo_id.count(':') == 5 and all(c in '0123456789abcdefABCDEF:' for c in jabobo_id.strip())
    
    if is_activation_code:
        activation_code_index = activation_codes.index(jabobo_id)
        jabobo_id = unactivated_macs[activation_code_index]
        logger.info(f"🔑 [ACTIVATION] Pairing code {payload.get('jabobo_id')} matched MAC address {jabobo_id}")
    elif not is_valid_mac:
        logger.warning(f"❌ [BIND] Invalid device ID: {jabobo_id}")
        raise HTTPException(status_code=400, detail="无效的设备ID！请输入正确的配对码或MAC地址")

    if not db.connect(): 
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        verify_user(x_username, authorization)

        db.cursor.execute(
            "SELECT jabobo_id FROM user_personas WHERE username = %s AND jabobo_id = %s",
            (x_username, jabobo_id)
        )
        if db.cursor.fetchone():
            return {"success": False, "message": "该设备已在您的列表中"}

        default_persona = json.dumps([{"id": "p1", "name": "默认人设", "content": "hello，i am your jabobo."}])
        sql = "INSERT INTO user_personas (username, jabobo_id, personas, memory) VALUES (%s, %s, %s, %s)"
        db.cursor.execute(sql, (x_username, jabobo_id, default_persona, "no memory now"))
        db.cursor.connection.commit()
        
        logger.success(f"✨ [BIND] User: {x_username} | New Device: {jabobo_id}")
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
        db.cursor.connection.commit()
        
        if db.cursor.rowcount == 0:
            logger.warning(f"⚠️ [UNBIND] Attempt failed - Device not found: {jabobo_id} for user {x_username}")
            return {"success": False, "message": "未找到该设备或无权操作"}

        logger.success(f"🗑️ [UNBIND] User: {x_username} | Removed Device: {jabobo_id}")
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

        sql = "SELECT personas, memory, current_version, expected_version FROM user_personas WHERE username = %s AND jabobo_id = %s"
        db.cursor.execute(sql, (x_username, jabobo_id))
        config = db.cursor.fetchone()
        
        raw_persona = config.get('personas', "[]") if config else "[]"
        memory_data = config.get('memory', "") if config else ""
        current_version = config.get('current_version', "") if config else ""  
        expected_version = config.get('expected_version', "") if config else ""  

        logger.info(f"🔍 [GET] User: {x_username} | Device: {jabobo_id} | Persona length: {len(raw_persona)}")
        return {
            "success": True, 
            "data": {
                "persona": raw_persona,
                "memory": memory_data,
                "voice_status": "已就绪",
                "kb_status": "已同步",
                "current_version": current_version,
                "expected_version": expected_version
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

        db.cursor.execute(
            "SELECT username FROM user_personas WHERE jabobo_id = %s", 
            (new_id,)
        )
        existing = db.cursor.fetchone()
        if existing:
            logger.warning(f"🛑 [REBIND] Target ID {new_id} already bound by {existing.get('username')}")
            raise HTTPException(status_code=400, detail="新设备 ID 已被绑定")

        sql = """
            UPDATE user_personas 
            SET jabobo_id = %s 
            WHERE username = %s AND jabobo_id = %s
        """
        db.cursor.execute(sql, (new_id, x_username, old_id))
        db.cursor.connection.commit()
        
        if db.cursor.rowcount == 0:
            logger.error(f"❌ [REBIND] Original device {old_id} not found for user {x_username}")
            return {"success": False, "message": "原设备不存在或无权操作"}

        logger.success(f"🔄 [REBIND] User: {x_username} | {old_id} -> {new_id}")
        return {"success": True, "message": "设备换绑成功，人设已迁移"}
    finally:
        db.close()