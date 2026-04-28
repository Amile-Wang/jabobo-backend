from fastapi import APIRouter, HTTPException, Header, Query, Body
from app.database import db
import json
from datetime import datetime
from loguru import logger  # 导入 loguru
# 已导入的核心函数
from app.utils.security import get_valid_cursor, verify_user

router = APIRouter()

# 2. 获取【特定设备】的配置
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
            logger.error("❌ [GET CONFIG] 数据库连接失败")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 2. 用户token校验
        verify_user(x_username, authorization)
        
        # 3. 获取有效游标
        cursor = get_valid_cursor()

        # SQL查询添加版本号字段
        sql = """
            SELECT personas, memory, current_version, expected_version, websocket_url
            FROM user_personas
            WHERE username = %s AND jabobo_id = %s
        """
        cursor.execute(sql, (x_username, jabobo_id))
        config = cursor.fetchone()

        # 分层读取+兜底
        if config is None:
            raw_persona = "[]"
            memory_data = ""
            current_version = "1.0.0"
            expected_version = "1.0.0"
            websocket_url = ""
            logger.info(f"ℹ️ [GET CONFIG] 未找到记录，为用户 {x_username} 使用默认配置")
        else:
            raw_persona = config.get('personas') or "[]"
            memory_data = config.get('memory') or ""
            current_version = config.get('current_version') or "1.0.0"
            expected_version = config.get('expected_version') or "1.0.0"
            websocket_url = config.get('websocket_url') or ""
        
        # 数据类型统一+安全处理
        raw_persona = str(raw_persona).strip() if raw_persona else "[]"
        memory_str = str(memory_data).strip() if memory_data else ""
        current_version = str(current_version).strip() or "1.0.0"
        expected_version = str(expected_version).strip() or "1.0.0"

        final_persona = raw_persona if raw_persona else "[]"

        # 使用 loguru 结构化打印日志
        logger.info(f"🔍 [GET CONFIG] User: {x_username} | Device: {jabobo_id}")
        logger.debug(f"📊 Data Stats: Persona: {len(final_persona)} chars | Memory: {len(memory_str)} chars")
        logger.info(f"📌 Version: Current={current_version} | Expected={expected_version}")

        return {
            "success": True,
            "data": {
                "persona": final_persona,
                "memory": memory_str,
                "voice_status": "已就绪",
                "kb_status": "已同步",
                "current_version": current_version,
                "expected_version": expected_version,
                "websocket_url": websocket_url
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🔥 [GET CONFIG 未知错误] User: {x_username} | Error: {str(e)}")
        raise HTTPException(status_code=500, detail="获取配置失败，请重试")
    finally:
        if db_connected and hasattr(db, 'connection') and db.connection:
            try:
                db.close()
            except:
                pass

# 3. 同步【特定设备】的配置
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
            logger.error("❌ [SYNC CONFIG] 数据库连接失败")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 多端token校验
        verify_user(x_username, authorization)
        
        # 2. 获取有效游标
        cursor = get_valid_cursor()

        # 3. 参数解析 + 严格校验
        jabobo_id = payload.get('jabobo_id', '').strip()
        persona_json = payload.get('persona', '[]') if payload.get('persona') is not None else '[]'
        memory = payload.get('memory', '') if payload.get('memory') is not None else ''
        ws_url_raw = payload.get('websocket_url', '')
        websocket_url = ws_url_raw.strip() if isinstance(ws_url_raw, str) and ws_url_raw.strip() else None

        if not jabobo_id:
            logger.warning(f"⚠️ [SYNC CONFIG] User {x_username} 提交的 payload 缺少 jabobo_id")
            raise HTTPException(status_code=400, detail="缺少 jabobo_id")
        
        # 支持MAC格式和6位纯数字格式校验
        is_mac_format = len(jabobo_id) == 17 and jabobo_id.count(':') == 5
        is_6digit_format = len(jabobo_id) == 6 and jabobo_id.isdigit()
        
        if not (is_mac_format or is_6digit_format):
            logger.warning(f"⚠️ [SYNC CONFIG] 非法设备ID格式: {jabobo_id} (User: {x_username})")
            raise HTTPException(
                status_code=400,
                detail="设备ID格式非法（应为xx:xx:xx:xx:xx:xx或6位纯数字）"
            )

        # 校验JSON
        try:
            json.loads(persona_json)
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ [SYNC CONFIG] Persona JSON格式错误: {str(e)}")
            raise HTTPException(status_code=400, detail="persona 不是合法的JSON字符串")

        logger.info(f"🚀 [SYNC CONFIG] Request from User: {x_username} for Device: {jabobo_id}")

        # 写入数据库
        sql = """
            INSERT INTO user_personas (username, jabobo_id, personas, memory, websocket_url)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                personas = VALUES(personas),
                memory = VALUES(memory),
                websocket_url = VALUES(websocket_url)
        """
        cursor.execute(sql, (x_username, jabobo_id, persona_json, memory, websocket_url))
        db.connection.commit()
        
        logger.success(f"✅ [SYNC CONFIG] Database updated for User: {x_username} / Device: {jabobo_id}")
        
        return {"success": True, "message": f"设备 {jabobo_id} 数据同步成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🔥 [SYNC CONFIG CRITICAL] User: {x_username} | Error: {str(e)}")
        raise HTTPException(status_code=500, detail="配置同步失败，请联系管理员")
    finally:
        if db_connected and hasattr(db, 'connection') and db.connection:
            try:
                db.close()
            except:
                pass