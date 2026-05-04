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

OTA_DIR = os.getenv("OTA_DIR", "/home/azureuser/tianhao/my_code/Jabobo/jabobo-backend/OTA")
OTA_DOWNLOAD_BASE_URL = os.getenv(
    "OTA_DOWNLOAD_BASE_URL",
    "http://51.107.185.69/api/xiaozhi/otaMag/download",
).rstrip("/")

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
        
@router.put("/user/device/update_version", description="更新设备的版本号（current_version/expected_version/force_install）")
async def update_device_version(
    jabobo_id: str = Query(..., description="要更新的设备ID"),
    current_version: str = Query(None, description="要设置的当前版本号（如1.0）"),
    expected_version: str = Query(None, description="要设置的预期版本号（如1.1）"),
    force_install: int = Query(None, description="是否强制安装目标版本（1=强制，绕过版本号大于比较，可用于回退；0=不强制）")
):
    # 1. 设备ID非空校验
    if not jabobo_id.strip():
        raise HTTPException(status_code=400, detail="设备ID不能为空")

    # 2. 版本号参数校验
    if current_version is None and expected_version is None and force_install is None:
        raise HTTPException(status_code=400, detail="至少需要传入current_version/expected_version/force_install其中一个字段")

    if force_install is not None and force_install not in (0, 1):
        raise HTTPException(status_code=400, detail="force_install 仅接受 0 或 1")

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

        if force_install is not None:
            update_fields.append("force_install = %s")
            update_params.append(int(force_install))

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
        logger.success(f"🔄 [UPDATE_VERSION] Device: {jabobo_id} | Current: {current_version} | Expected: {expected_version} | Force: {force_install} | Affected: {affected_rows}")

        return {
            "success": True,
            "message": "设备版本号更新成功",
            "data": {
                "jabobo_id": jabobo_id,
                "current_version": current_version,
                "expected_version": expected_version,
                "force_install": force_install,
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

# 列出 OTA 目录下所有可下发的固件（供前端选择目标版本）
@router.get("/xiaozhi/otaMag/list")
async def list_firmwares():
    items = []
    if os.path.isdir(OTA_DIR):
        for name in sorted(os.listdir(OTA_DIR)):
            if not name.endswith(".bin"):
                continue
            path = os.path.join(OTA_DIR, name)
            if not os.path.isfile(path):
                continue
            version = None
            if name.startswith("Jabobo_") and name.endswith(".bin"):
                version = name[len("Jabobo_"):-len(".bin")]
            elif name == "Jabobo.bin":
                version = ""  # 通用版本，不绑定具体版本号
            items.append({
                "filename": name,
                "version": version,
                "size": os.path.getsize(path),
            })
    return {"success": True, "data": items}

# 添加固件下载路由
@router.get("/xiaozhi/otaMag/download/{filename}")
@router.head("/xiaozhi/otaMag/download/{filename}")
async def download_firmware(filename: str):
    """
    固件下载接口 - 用于OTA升级
    """
    print(f"📥 [FIRMWARE_DOWNLOAD] Firmware download requested: {filename}")

    # 允许两种文件名：旧的 Jabobo.bin 或新的 Jabobo_<version>.bin
    allowed = False
    if filename == "Jabobo.bin":
        allowed = True
    elif filename.startswith("Jabobo_") and filename.endswith(".bin"):
        allowed = True

    if not allowed:
        print(f"❌ [FIRMWARE_DOWNLOAD] Invalid firmware filename: {filename}")
        raise HTTPException(status_code=404, detail="Firmware file not found")

    # 优先在 OTA 目录中查找与请求名称匹配的文件
    ota_dir = OTA_DIR
    firmware_path = os.path.join(ota_dir, filename)

    # 如果版本化文件不存在，回退到通用 Jabobo.bin（保持向后兼容）
    if not os.path.exists(firmware_path):
        fallback = os.path.join(ota_dir, "Jabobo.bin")
        if os.path.exists(fallback):
            firmware_path = fallback
            print(f"⚠️ [FIRMWARE_DOWNLOAD] Requested {filename} not found, falling back to {fallback}")
        else:
            print(f"❌ [FIRMWARE_DOWNLOAD] Firmware file not found at path: {firmware_path}")
            raise HTTPException(status_code=404, detail="Firmware file not found")

    file_size = os.path.getsize(firmware_path)
    logger.success(f"✅ [FIRMWARE_DOWNLOAD] Serving firmware: {filename}, size: {file_size} bytes")

    # 返回文件，Content-Disposition 名称使用请求的文件名
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
        
        sql = "SELECT username, websocket_url FROM user_personas WHERE jabobo_id = %s"
        db.cursor.execute(sql, (device_id,))
        existing_device = db.cursor.fetchone()

        activation_obj = None
        activation_code = None
        device_ws_url = existing_device.get("websocket_url") if existing_device else None

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
    
    # 设备当前版本（用于响应 firmware.version 字段，不代表要升级）
    app_version = (
        (device_info.get("application") or {}).get("version")
        or "0.0.0"
    )

    # 从数据库读取 expected_version + force_install；前者为空则默认不下发升级 url
    expected_version = None
    force_install = 0
    if db.connect():
        try:
            sql = "SELECT expected_version, force_install FROM user_personas WHERE jabobo_id = %s"
            db.cursor.execute(sql, (device_id,))
            row = db.cursor.fetchone()
            if row:
                if isinstance(row, dict):
                    ev = row.get("expected_version")
                    fi = row.get("force_install")
                else:
                    ev, fi = row[0], row[1]
                if ev and str(ev).strip():
                    expected_version = str(ev).strip()
                try:
                    force_install = int(fi or 0)
                except (TypeError, ValueError):
                    force_install = 0
        except Exception as e:
            logger.warning(f"⚠️ [OTA] Failed to read expected_version/force_install for {device_id}: {e}")
        finally:
            db.close()

    # 默认 firmware 块：不带 url，固件端见不到 url 就不会触发升级
    firmware_block = {
        "version": app_version,
        "force": 0,
    }

    if expected_version:
        safe_ver = expected_version.replace(' ', '_')
        versioned_filename = f"Jabobo_{safe_ver}.bin"
        firmware_path = os.path.join(OTA_DIR, versioned_filename)
        if os.path.exists(firmware_path):
            firmware_block["version"] = safe_ver
            firmware_block["url"] = f"{OTA_DOWNLOAD_BASE_URL}/{versioned_filename}"
            # force_install=1 时让固件绕过 IsNewVersionAvailable 的"严格大于"比较，
            # 用于手动回退或同版本重刷（esp_https_ota 仍会拦截 image header version 完全相同的情况）
            if force_install == 1:
                firmware_block["force"] = 1
            logger.info(
                f"📦 [OTA FIRMWARE] device={device_id} current={app_version} "
                f"target={safe_ver} force={firmware_block['force']} url={firmware_block['url']}"
            )
        else:
            logger.warning(
                f"⚠️ [OTA FIRMWARE] device={device_id} expected_version={expected_version} "
                f"but {versioned_filename} not found in {OTA_DIR}, skipping upgrade"
            )
    else:
        logger.info(f"🔕 [OTA FIRMWARE] device={device_id} expected_version is empty, no upgrade")

    response_data = {
        "server_time": {
            "timestamp": timestamp,
            "timeZone": "Asia/Shanghai",
            "timezone_offset": 480
        },
        "firmware": firmware_block,
        "websocket": {
            "url": device_ws_url or os.getenv("WEBSOCKET_URL", "ws://51.107.185.69/ws/")
        }
    }
    
    # 输出响应日志response_data
    logger.info(f"📤 [OTA RESPONSE] To Device {device_id}: {response_data}")
    
    if activation_obj:
        response_data["activation"] = activation_obj
        logger.success(f"🔐 [OTA ACTIVATION] Code {activation_code} assigned to {device_id}")
    else:
        logger.info(f"🔓 [OTA ACTIVATION] No activation needed for {device_id}")
    
    # 在返回响应前，更新数据库中的设备版本号
    # 获取设备上报的当前版本号（如果有的话）
    current_version = app_version
    # 如果存在当前版本号，则更新数据库
    if current_version and device_id:
        if not db.connect():
            print(f"❌ [VERSION UPDATE ERROR] Database connection failed when updating version for device {device_id}")
        else:
            try:
                # 更新设备的当前版本号
                update_sql = "UPDATE user_personas SET current_version = %s WHERE jabobo_id = %s"
                db.cursor.execute(update_sql, (current_version, device_id))
                db.connection.commit()
                
                affected_rows = db.cursor.rowcount
                if affected_rows > 0:
                    print(f"🔄 [VERSION UPDATE] Successfully updated device {device_id} current version to {current_version}")
                else:
                    print(f"⚠️ [VERSION UPDATE] No device found with ID {device_id} for version update")
                    
            except Exception as e:
                print(f"❌ [VERSION UPDATE ERROR] Failed to update device {device_id} version: {str(e)}")
                try:
                    db.connection.rollback()
                except:
                    pass
            finally:
                db.close()
    
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