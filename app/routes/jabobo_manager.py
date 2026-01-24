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
        # 新增print：打印请求基础信息（脱敏token，避免泄露）
        print(f"===== [收到jabobo_ids请求] =====")
        print(f"接收的x_username: {x_username}")
        print(f"接收的Authorization（前10位）: {authorization[:10]}...")
        
        # 验证用户后打印（确认验证通过）
        verify_user(x_username, authorization)
        print(f"✅ 身份验证通过：用户名={x_username}")
        
        # 新增print：打印执行的SQL语句（便于排查查询条件）
        sql = "SELECT jabobo_id FROM user_personas WHERE username = %s"
        print(f"🔍 执行SQL：{sql} | 参数：({x_username})")
        
        # 原有查询逻辑
        db.cursor.execute(sql, (x_username,))
        rows = db.cursor.fetchall()
        
        # 新增print：打印查询到的行数（确认是否有数据）
        print(f"📊 查询到的行数：{len(rows)}")
        
        # 原有数据处理逻辑
        ids = [row['jabobo_id'] for row in rows]
        
        # 原有print保留，补充完整上下文
        print(f"📋 [LIST] User: {x_username} | Devices: {ids}")
        print(f"📤 返回结果：success=True, jabobo_ids={ids}")
        
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
    
    # 新增：定义合法设备ID的判断逻辑（MAC地址格式/激活码）
    is_activation_code = jabobo_id in activation_codes
    # 假设MAC地址是12位十六进制字符串（可根据实际格式调整）
    is_valid_mac = len(jabobo_id.strip()) == 17 and jabobo_id.count(':') == 5 and all(c in '0123456789abcdefABCDEF:' for c in jabobo_id.strip())
    
    # 场景1：是激活码 → 转换为MAC地址
    if is_activation_code:
        activation_code_index = activation_codes.index(jabobo_id)
        jabobo_id = unactivated_macs[activation_code_index]
        print(f"🔑 [ACTIVATION] Pairing code {payload.get('jabobo_id')} matched MAC address {jabobo_id}")
    # 场景2：既不是激活码也不是合法MAC → 直接返回错误
    elif not is_valid_mac:
        print(f"❌ [BIND] Invalid device ID: {jabobo_id}")
        raise HTTPException(status_code=400, detail="无效的设备ID！请输入正确的配对码或MAC地址")

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
        default_persona = json.dumps([{"id": "p1", "name": "默认人设", "content": "hello，i am your jabobo."}])
        sql = "INSERT INTO user_personas (username, jabobo_id, personas, memory) VALUES (%s, %s, %s, %s)"
        db.cursor.execute(sql, (x_username, jabobo_id, default_persona, "no memory now"))
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
        current_version = config.get('current_version', "") if config else ""  
        expected_version = config.get('expected_version', "") if config else ""  

        print(f"🔍 [GET] User: {x_username} | Device: {jabobo_id} | Persona length: {len(raw_persona)}")
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