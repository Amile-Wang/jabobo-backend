from fastapi import APIRouter, HTTPException, Query, Header, Response
from fastapi.responses import FileResponse, StreamingResponse
from app.database import db, unactivated_macs, activation_codes  # 复用已有的数据库实例和全局数组
import json
from datetime import datetime, timezone
import time
import hashlib
import os
from fastapi.requests import Request
from loguru import logger  # 导入 loguru

router = APIRouter()

# 无需鉴权：通过jabobo_id读取设备所有数据
@router.get("/user/device/full_data")
async def get_device_full_data(
    jabobo_id: str = Query(..., description="要查询的设备ID")
):
    # 1. 设备ID非空校验
    if not jabobo_id.strip():
        raise HTTPException(status_code=400, detail="设备ID不能为空")
    
    # 2. 数据库连接校验
    if not db.connect():
        logger.error("❌ [FULL_DATA] 数据库连接失败")
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 3. 查询设备全量数据
        sql = "SELECT * FROM user_personas WHERE jabobo_id = %s"
        db.cursor.execute(sql, (jabobo_id,))
        device_data = db.cursor.fetchone()
        
        # 4. 无数据处理
        if not device_data:
            logger.warning(f"⚠️ [FULL_DATA] 未找到ID为 {jabobo_id} 的设备数据")
            return {
                "success": False,
                "message": f"未找到ID为 {jabobo_id} 的设备数据",
                "data": None
            }
        
        # 5. 日志打印
        logger.info(f"📄 [FULL_DATA_NO_AUTH] Device: {jabobo_id} | Data: {device_data}")
        
        # 6. 返回全量数据
        return {
            "success": True,
            "message": "设备全量数据查询成功",
            "data": device_data
        }
    
    finally:
        # 7. 确保关闭数据库连接
        db.close()
        
@router.put("/user/device/update_version", description="更新设备的版本号（current_version/expected_version）")
async def update_device_version(
    jabobo_id: str = Query(..., description="要更新的设备ID"),
    current_version: str = Query(None, description="要设置的当前版本号（如1.0）"),
    expected_version: str = Query(None, description="要设置的预期版本号（如1.1）")
):
    # 1. 设备ID非空校验
    if not jabobo_id.strip():
        raise HTTPException(status_code=400, detail="设备ID不能为空")
    
    # 2. 版本号参数校验
    if current_version is None and expected_version is None:
        raise HTTPException(status_code=400, detail="至少需要传入current_version或expected_version其中一个字段")
    
    # 3. 数据库连接校验
    if not db.connect():
        logger.error("❌ [UPDATE_VERSION] 数据库连接失败")
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 4. 构造动态更新SQL
        update_fields = []
        update_params = []
        
        if current_version is not None:
            update_fields.append("current_version = %s")
            update_params.append(current_version.strip())
        
        if expected_version is not None:
            update_fields.append("expected_version = %s")
            update_params.append(expected_version.strip())
        
        sql = f"UPDATE user_personas SET {', '.join(update_fields)} WHERE jabobo_id = %s"
        update_params.append(jabobo_id)
        
        # 5. 执行更新操作
        db.cursor.execute(sql, tuple(update_params))
        db.connection.commit()
        
        # 6. 处理更新结果
        affected_rows = db.cursor.rowcount
        if affected_rows == 0:
            logger.warning(f"⚠️ [UPDATE_VERSION] 更新失败，未找到设备: {jabobo_id}")
            return {
                "success": False,
                "message": f"未找到ID为 {jabobo_id} 的设备数据，更新失败",
                "data": None
            }
        
        # 7. 日志打印
        logger.success(f"🔄 [UPDATE_VERSION] Device: {jabobo_id} | Current: {current_version} | Expected: {expected_version} | Affected: {affected_rows}")
        
        return {
            "success": True,
            "message": "设备版本号更新成功",
            "data": {
                "jabobo_id": jabobo_id,
                "current_version": current_version,
                "expected_version": expected_version
            }
        }
    
    except Exception as e:
        try:
            if db.connection and not db.connection.closed:
                db.connection.rollback()
        except:
            pass
        
        logger.error(f"❌ [UPDATE_VERSION_ERROR] Device: {jabobo_id} | Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"版本号更新失败：{str(e)}")
    
    finally:
        db.close()

# 添加固件下载路由
@router.get("/xiaozhi/otaMag/download/{filename}")
@router.head("/xiaozhi/otaMag/download/{filename}")
async def download_firmware(filename: str):
    """
    固件下载接口 - 用于OTA升级
    """
    logger.info(f"📥 [FIRMWARE_DOWNLOAD] Firmware requested: {filename}")
    
    if filename != "Jabob.bin":
        logger.warning(f"❌ [FIRMWARE_DOWNLOAD] Invalid filename: {filename}")
        raise HTTPException(status_code=404, detail="Firmware file not found")
    
    firmware_path = "/var/local/jobobo-backend/OTA/Jabob.bin"
    
    if not os.path.exists(firmware_path):
        logger.error(f"❌ [FIRMWARE_DOWNLOAD] File not found at: {firmware_path}")
        raise HTTPException(status_code=404, detail="Firmware file not found")
    
    file_size = os.path.getsize(firmware_path)
    logger.success(f"✅ [FIRMWARE_DOWNLOAD] Serving firmware: {filename}, size: {file_size} bytes")

    return FileResponse(
        path=firmware_path,
        filename=filename,
        media_type='application/octet-stream',
        headers={
            "Cache-Control": "no-cache",
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        }
    )

# OTA接口：接收设备发送的OTA请求
@router.post("/user/device/ota")
async def handle_ota_request(
    device_info: dict,
    device_id: str = Header(None, alias="Device-Id"),
    client_id: str = Header(None, alias="Client-Id"),
    user_agent: str = Header(None, alias="User-Agent"),
    activation_version: str = Header(None, alias="Activation-Version")
):
    """
    处理设备发送的OTA请求
    """
    logger.info(f"🚀 [OTA_REQUEST] Device-Id: {device_id} | Client-Id: {client_id}")
    logger.debug(f"OTA Context: UA={user_agent}, Version={activation_version}")
    
    now = datetime.now(timezone.utc)
    timestamp = int(time.mktime(now.timetuple()) * 1000 + now.microsecond / 1000)
    
    if not db.connect():
        logger.error("❌ [OTA_REQUEST] 数据库连接失败")
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        logger.debug(f"🔍 [OTA CHECK] Checking registration for {device_id}")
        
        sql = "SELECT username FROM user_personas WHERE jabobo_id = %s"
        db.cursor.execute(sql, (device_id,))
        existing_device = db.cursor.fetchone()
        
        activation_obj = None
        activation_code = None
        
        if existing_device:
            logger.info(f"✅ [OTA CHECK] Device {device_id} is registered to: {existing_device.get('username')}")
        else:
            logger.warning(f"❌ [OTA CHECK] Device {device_id} not registered, generating activation...")
            mac_address = device_info.get("mac_address", "00:00:00:00:00:00")
            activation_code = generate_activation_code_from_mac(mac_address)
            
            if mac_address not in unactivated_macs:
                unactivated_macs.append(mac_address)
                activation_codes.append(activation_code)
            
            logger.debug(f"➕ [OTA ACTIVATION] Unactivated Pool: {len(unactivated_macs)} items")
            
            activation_obj = { 
                "code": activation_code,
                "message": f"http://xiaozhi.server.com\n{activation_code}",
                "challenge": mac_address
            }
    finally:
        db.close()
    
    response_data = {
        "server_time": {
            "timestamp": timestamp,
            "timeZone": "Asia/Shanghai",
            "timezone_offset": 480
        },
        "firmware": {
            "version": "2.0.3",
            "url": "https://jabobo.com/api/xiaozhi/otaMag/download/Jabob.bin",
            "force": 0
        },
        "websocket": {
            "url": "ws://121.41.168.85:8000/xiaozhi/v1/"
        }
    }
    
    if activation_obj:
        response_data["activation"] = activation_obj
        logger.success(f"🔐 [OTA ACTIVATION] Code {activation_code} assigned to {device_id}")
    else:
        logger.info(f"🔓 [OTA ACTIVATION] No activation needed for {device_id}")
    
    return response_data

def generate_activation_code_from_mac(mac_address: str) -> str:
    """
    从MAC地址生成固定的6位数字激活码
    """
    clean_mac = ''.join(c for c in mac_address if c.isalnum()).lower()
    hash_object = hashlib.md5(clean_mac.encode())
    hex_dig = hash_object.hexdigest()
    
    hex_part = hex_dig[:8]
    int_value = int(hex_part, 16)
    activation_code = str(int_value % 1000000).zfill(6)
    
    return activation_code

@router.post("/user/device/ota/activate")
async def activate_device(
    device_info: dict,
    device_id: str = Header(None, alias="Device-Id"),
    client_id: str = Header(None, alias="Client-Id"),
    user_agent: str = Header(None, alias="User-Agent"),
    activation_version: str = Header(None, alias="Activation-Version")
):
    """
    激活设备端点
    """
    logger.info(f"🔑 [ACTIVATION_TRY] Received for Device-Id: {device_id}")
    
    if not db.connect():
        logger.error("❌ [ACTIVATION] 数据库连接失败")
        return {"success": False, "message": "数据库连接失败", "status": "failed"}, 500

    try:
        sql = "SELECT username FROM user_personas WHERE jabobo_id = %s"
        db.cursor.execute(sql, (device_id,))
        existing_device = db.cursor.fetchone()
        
        if existing_device:
            logger.success(f"✅ [ACTIVATION_SUCCESS] Device {device_id} verified")
            try:
                activation_index = unactivated_macs.index(device_id)
                unactivated_macs.pop(activation_index)
                activation_codes.pop(activation_index)
            except ValueError:
                pass # 已从待激活列表移除
            return 200
        else:
            logger.warning(f"❌ [ACTIVATION_FAILED] Device {device_id} not in DB")
            time.sleep(5)
            return 203
    except Exception as e:
        logger.error(f"❌ [ACTIVATION_ERROR] {str(e)}")
        time.sleep(5)
        return 203
    finally:
        db.close()