from fastapi import APIRouter, HTTPException, Header, Query, Body
from app.database import db
import json
from datetime import datetime
# 已导入的核心函数
from app.utils.security import get_valid_cursor, verify_user

router = APIRouter()

# 2. 获取【特定设备】的配置（核心修改：调用verify_user替换旧校验）
@router.get("/user/config")
async def get_user_config(
    jabobo_id: str = Query(...), 
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    db_connected = False
    try:
        # 1. 数据库连接
        db_connected = db.connect()
        if not db_connected:
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 2. 用户token校验
        verify_user(x_username, authorization)
        
        # 3. 获取有效游标
        cursor = get_valid_cursor()

        # ========== 核心修改1：SQL查询添加版本号字段 ==========
        # 原问题：未查询 current_version/expected_version，导致后续读取不到
        sql = """
            SELECT personas, memory, current_version, expected_version 
            FROM user_personas 
            WHERE username = %s AND jabobo_id = %s
        """
        cursor.execute(sql, (x_username, jabobo_id))
        config = cursor.fetchone()  # 返回字典格式（依赖get_valid_cursor配置）

        # ========== 核心修改2：分层读取+兜底，确保版本号读取正确 ==========
        # 第一层：配置不存在 → 版本号设为默认值（如1.0.0）
        if config is None:
            raw_persona = "[]"
            memory_data = ""
            current_version = "1.0.0"  # 版本号默认值
            expected_version = "1.0.0"
        else:
            # 第二层：配置存在，读取各字段（空值兜底）
            raw_persona = config.get('personas') or "[]"
            memory_data = config.get('memory') or ""
            # 版本号读取：数据库值 → 空值 → 默认值
            current_version = config.get('current_version') or "1.0.0"
            expected_version = config.get('expected_version') or "1.0.0"
        
        # ========== 数据类型统一+安全处理 ==========
        # 强制转为字符串，避免非字符串类型（如None/int）
        raw_persona = str(raw_persona).strip() if raw_persona else "[]"
        memory_str = str(memory_data).strip() if memory_data else ""
        # 版本号强制转字符串+去空格（防止数据库存为数字/空格）
        current_version = str(current_version).strip() or "1.0.0"
        expected_version = str(expected_version).strip() or "1.0.0"

        # 最终数据兜底
        final_persona = raw_persona if raw_persona else "[]"

        # 日志增强：添加版本号日志
        persona_len = len(final_persona)
        memory_len = len(memory_str)
        print("-" * 50)
        print(f"🔍 [GET CONFIG] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   👤 User: {x_username}")
        print(f"   🆔 Target Device: {jabobo_id}")
        print(f"   📦 Data Found: {persona_len} chars of persona, {memory_len} chars of memory")
        print(f"   📌 Version: Current={current_version} | Expected={expected_version}")  # 新增版本号日志
        print(f"   📄 Persona Type: {type(final_persona)} | Preview: {final_persona[:50]}...")
        print("-" * 50)

        # ========== 核心修改3：返回正确的版本号 ==========
        return {
            "success": True, 
            "data": {
                "persona": final_persona,  
                "memory": memory_str,
                "voice_status": "已就绪",
                "kb_status": "已同步",
                "current_version": current_version,  # 确保有值且为字符串
                "expected_version": expected_version  # 确保有值且为字符串
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"🔥 [GET CONFIG 未知错误] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail="获取配置失败，请重试")
    finally:
        # 安全关闭连接
        if db_connected and hasattr(db, 'connection') and db.connection:
            try:
                db.close()
            except:
                pass

# 3. 同步【特定设备】的配置（同样替换为verify_user校验）
@router.post("/user/sync-config")
async def sync_config(
    payload: dict = Body(...), 
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    db_connected = False
    try:
        # 1. 数据库连接
        db_connected = db.connect()
        if not db_connected:
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # ========== 核心修改：调用verify_user进行多端token校验 ==========
        verify_user(x_username, authorization)
        
        # 2. 获取有效游标
        cursor = get_valid_cursor()

        # 3. 参数解析 + 严格校验（业务逻辑保持不变）
        jabobo_id = payload.get('jabobo_id', '').strip()
        persona_json = payload.get('persona', '[]') if payload.get('persona') is not None else '[]'
        memory = payload.get('memory', '') if payload.get('memory') is not None else ''

        # 校验jabobo_id
        if not jabobo_id:
            print(f"❌ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Missing jabobo_id in payload!")
            raise HTTPException(status_code=400, detail="缺少 jabobo_id")
        
        # ========== 核心修改：支持MAC格式和6位纯数字格式 ==========
        # 定义两种合法格式的校验条件
        is_mac_format = len(jabobo_id) == 17 and jabobo_id.count(':') == 5
        is_6digit_format = len(jabobo_id) == 6 and jabobo_id.isdigit()
        
        # 既不是MAC格式也不是6位纯数字，判定为非法
        if not (is_mac_format or is_6digit_format):
            print(f"⚠️ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 非法设备ID：{jabobo_id}")
            raise HTTPException(
                status_code=400,
                detail="设备ID格式非法（应为xx:xx:xx:xx:xx:xx或6位纯数字）"
            )

        # 校验JSON（确保前端传入的是合法JSON字符串）
        try:
            json.loads(persona_json)
        except json.JSONDecodeError as e:
            print(f"❌ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Persona JSON非法：{str(e)}")
            raise HTTPException(status_code=400, detail="persona 不是合法的JSON字符串")

        # 日志
        print("=" * 50)
        print(f"🚀 [SYNC CONFIG] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   👤 User: {x_username}")
        print(f"   🆔 Device ID from payload: {jabobo_id}")
        print(f"   📝 Persona Content: {persona_json[:100]}...")
        print(f"   🧠 Memory Content: {memory[:100]}...")
        print("=" * 50)

        # 写入数据库
        sql = """
            INSERT INTO user_personas (username, jabobo_id, personas, memory) 
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE personas = VALUES(personas), memory = VALUES(memory)
        """
        cursor.execute(sql, (x_username, jabobo_id, persona_json, memory))
        # 提交事务（确保数据写入）
        db.connection.commit()
        
        print(f"✅ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - [DATABASE UPDATED] Target: {x_username} / {jabobo_id}")
        
        return {"success": True, "message": f"设备 {jabobo_id} 数据同步成功"}
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"🔥 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Sync Critical Error: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail="配置同步失败，请联系管理员")
    finally:
        # 安全关闭连接
        if db_connected and hasattr(db, 'connection') and db.connection:
            try:
                db.close()
            except:
                pass