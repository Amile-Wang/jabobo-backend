from fastapi import APIRouter, HTTPException, Query, Header, Response
from fastapi.responses import FileResponse, StreamingResponse
from app.database import db, unactivated_macs, activation_codes  # 复用你已有的数据库实例和全局数组
import json
from datetime import datetime, timezone
import time
import hashlib
import os
from fastapi.requests import Request  # 添加这一行

router = APIRouter()
#这个接口后面可以用来做OTA
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
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 3. 查询设备全量数据
        sql = "SELECT * FROM user_personas WHERE jabobo_id = %s"
        db.cursor.execute(sql, (jabobo_id,))
        device_data = db.cursor.fetchone()
        
        # 4. 无数据处理
        if not device_data:
            return {
                "success": False,
                "message": f"未找到ID为 {jabobo_id} 的设备数据",
                "data": None
            }
        
        # 5. 日志打印（保持和你原有接口一致的风格）
        print(f"📄 [FULL_DATA_NO_AUTH] Device: {jabobo_id} | Data: {device_data}")
        
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
    # 1. 设备ID非空校验（和原有接口保持一致）
    if not jabobo_id.strip():
        raise HTTPException(status_code=400, detail="设备ID不能为空")
    
    # 2. 版本号参数校验：至少传入一个版本号字段用于更新
    if current_version is None and expected_version is None:
        raise HTTPException(status_code=400, detail="至少需要传入current_version或expected_version其中一个字段")
    
    # 3. 数据库连接校验（和原有接口保持一致）
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 4. 构造动态更新SQL（只更新传入的非空版本号字段）
        update_fields = []
        update_params = []
        
        if current_version is not None:
            update_fields.append("current_version = %s")
            update_params.append(current_version.strip())
        
        if expected_version is not None:
            update_fields.append("expected_version = %s")
            update_params.append(expected_version.strip())
        
        # 拼接SQL语句
        sql = f"UPDATE user_personas SET {', '.join(update_fields)} WHERE jabobo_id = %s"
        # 补充设备ID参数
        update_params.append(jabobo_id)
        
        # 5. 执行更新操作
        db.cursor.execute(sql, tuple(update_params))
        # 核心修复1：将 db.conn 改为 db.connection（MySQLConnector 类的正确连接属性名）
        db.connection.commit()
        
        # 6. 处理更新结果
        affected_rows = db.cursor.rowcount
        if affected_rows == 0:
            return {
                "success": False,
                "message": f"未找到ID为 {jabobo_id} 的设备数据，更新失败",
                "data": None
            }
        
        # 7. 日志打印（保持和原有接口一致的风格）
        print(f"🔄 [UPDATE_VERSION] Device: {jabobo_id} | CurrentVersion: {current_version or '1.0.0'} | ExpectedVersion: {expected_version or '1.0.0'} | AffectedRows: {affected_rows}")
        
        # 8. 返回成功结果
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
        # 核心修复2：将 db.conn 改为 db.connection
        try:
            # 增加容错：如果连接已关闭，跳过回滚
            if db.connection and not db.connection.closed:
                db.connection.rollback()
        except:
            pass
        
        print(f"❌ [UPDATE_VERSION_ERROR] Device: {jabobo_id} | Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"版本号更新失败：{str(e)}")
    
    finally:
        # 9. 确保关闭数据库连接（和原有接口保持一致）
        db.close()
        
# 添加固件下载路由

@router.get("/xiaozhi/otaMag/download/{filename}")
@router.head("/xiaozhi/otaMag/download/{filename}")  # ✅ 添加 HEAD 支持
async def download_firmware(filename: str):
    """
    固件下载接口 - 用于OTA升级
    """
    print(f"📥 [FIRMWARE_DOWNLOAD] Firmware download requested: {filename}")

    # 允许两种文件名：旧的 Jabob.bin 或新的 Jabobo_<version>.bin
    allowed = False
    if filename == "Jabob.bin":
        allowed = True
    elif filename.startswith("Jabobo_") and filename.endswith(".bin"):
        allowed = True

    if not allowed:
        print(f"❌ [FIRMWARE_DOWNLOAD] Invalid firmware filename: {filename}")
        raise HTTPException(status_code=404, detail="Firmware file not found")

    # 优先在 OTA 目录中查找与请求名称匹配的文件
    ota_dir = "/var/local/jobobo-backend/OTA"
    firmware_path = os.path.join(ota_dir, filename)

    # 如果版本化文件不存在，回退到通用 Jabob.bin（保持向后兼容）
    if not os.path.exists(firmware_path):
        fallback = os.path.join(ota_dir, "Jabob.bin")
        if os.path.exists(fallback):
            firmware_path = fallback
            print(f"⚠️ [FIRMWARE_DOWNLOAD] Requested {filename} not found, falling back to {fallback}")
        else:
            print(f"❌ [FIRMWARE_DOWNLOAD] Firmware file not found at path: {firmware_path}")
            raise HTTPException(status_code=404, detail="Firmware file not found")

    file_size = os.path.getsize(firmware_path)
    print(f"✅ [FIRMWARE_DOWNLOAD] Found firmware file: {firmware_path}, size: {file_size} bytes")

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
    print(f"OTA request received - Device-Id: {device_id}, Client-Id: {client_id}")
    print(f"User-Agent: {user_agent}, Activation-Version: {activation_version}")
    print(f"Device Info: {json.dumps(device_info, indent=2, ensure_ascii=False)}")
    
    # 获取当前时间戳（毫秒）
    now = datetime.now(timezone.utc)
    timestamp = int(time.mktime(now.timetuple()) * 1000 + now.microsecond / 1000)
    
    # 检查数据库中是否存在与设备ID匹配的jabobo_id
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        print(f"🔍 [OTA CHECK] Checking if device {device_id} is already registered...")
        
        # 查询数据库中是否存在该设备ID
        sql = "SELECT username FROM user_personas WHERE jabobo_id = %s"
        db.cursor.execute(sql, (device_id,))
        existing_device = db.cursor.fetchone()
        
        # 根据设备ID是否存在来决定是否需要激活
        if existing_device:
            # 如果设备ID已存在，不返回激活对象
            print(f"✅ [OTA CHECK] Device {device_id} is already registered to user: {existing_device.get('username', 'unknown')}")
            activation_obj = None
            activation_code = None
        else:
            # 如果设备ID不存在，生成激活码并返回激活对象
            print(f"❌ [OTA CHECK] Device {device_id} is not registered, generating activation code...")
            mac_address = device_info.get("mac_address", "00:00:00:00:00:00")
            activation_code =generate_activation_code_from_mac(mac_address)
            if mac_address not in unactivated_macs:
                unactivated_macs.append(mac_address)
                activation_codes.append(activation_code)
                
            print(f"➕ [OTA ACTIVATION] 当前未激活的MAC地址和激活码：{unactivated_macs} {activation_codes}" )
            # activation_obj = None
            
            activation_obj = { 
                "code": activation_code,
                "message": f"http://xiaozhi.server.com\n{activation_code}",
                "challenge": mac_address  # 使用MAC地址作为挑战码
            }
    finally:
        db.close()
    
    # 优先使用设备上报的 application.version 作为固件版本；依次回退到其他可能的字段或默认值
    app_version = (
        (device_info.get("application") or {}).get("version")
        or "2.0.9"
    )

    # 优先从数据库读取该设备对应的 expected_version（若存在且非空则覆盖 app_version）
    firmware_version = app_version
    try:
        if db.connect():
            try:
                sql = "SELECT expected_version FROM user_personas WHERE jabobo_id = %s"
                db.cursor.execute(sql, (device_id,))
                row = db.cursor.fetchone()
                if row:
                    # row 预期为 dict-like
                    ev = None
                    try:
                        ev = row.get("expected_version")
                    except Exception:
                        # 如果是 tuple/list，也尝试取第一个元素
                        try:
                            ev = row[0]
                        except Exception:
                            ev = None
                    if ev:
                        firmware_version = ev
            finally:
                db.close()
    except Exception as e:
        print(f"⚠️ [OTA] Failed to read expected_version for {device_id}: {str(e)}")

    # 构造响应，按照设备期望的格式
    # 生成带版本的固件文件名，例如 Jabobo_2.0.3.bin
    # 首先将 firmware_version 清理为 safe_ver，然后确认 OTA 目录中确实存在该版本文件；
    # 如果不存在则回退到设备上报的 app_version（仍会尝试查找对应文件，若找不到下载路由会回退到通用 Jabob.bin）
    ota_dir = "/var/local/jobobo-backend/OTA"
    safe_ver = str(firmware_version).replace(' ', '_')
    versioned_filename = f"Jabobo_{safe_ver}.bin"
    # 如果版本化文件在 OTA 目录中不存在，则回退到 app_version
    if not os.path.exists(os.path.join(ota_dir, versioned_filename)):
        safe_ver = str(app_version).replace(' ', '_')
        # versioned_filename = f"Jabobo_{safe_ver}.bin"
        versioned_filename = f"Jabobo.bin"
        # 如果回退后的 app_version 文件仍不存在，则保持使用回退后的 safe_ver，
        # 下载路由会在找不到该文件时回退到通用 Jabob.bin，确保向后兼容

    download_filename = versioned_filename
    download_url = f"http://121.41.168.85:8007/api/xiaozhi/otaMag/download/{download_filename}"

    response_data = {
        "server_time": {
            "timestamp": timestamp,
            "timeZone": "Asia/Shanghai",
            "timezone_offset": 480  # 时区偏移分钟数（GMT+8 = 480分钟）
        },
        "firmware": {
            "version": safe_ver,
            "url": download_url,
            "force": 0
        },
        "websocket": {
            "url": "ws://121.41.168.85:8000/xiaozhi/v1/"
        }
    }
    
    # 只有在设备未注册时才添加激活对象
    if activation_obj:
        response_data["activation"] = activation_obj
        print(f"🔐 [OTA ACTIVATION] Activation code {activation_code} generated for unregistered device {device_id}")
    else:
        
        print(f"🔓 [OTA ACTIVATION] No activation needed for registered device {device_id}")
    
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
    相同的MAC地址总是生成相同的激活码
    """
    # 清除MAC地址中的分隔符（冒号、破折号、空格等）
    clean_mac = ''.join(c for c in mac_address if c.isalnum()).lower()
    
    # 使用MD5哈希确保相同MAC地址在不同运行时始终生成相同的激活码
    hash_object = hashlib.md5(clean_mac.encode())
    hex_dig = hash_object.hexdigest()
    
    # 取哈希值的前8位并转换为整数，然后取模确保是6位数字
    # 将十六进制转换为十进制，并限制在6位数字范围内
    hex_part = hex_dig[:8]  # 取前8位十六进制字符
    int_value = int(hex_part, 16)  # 转换为整数
    activation_code = str(int_value % 1000000).zfill(6)  # zfill确保是6位，不足前面补0
    
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
    激活设备端点：通过激活码激活设备
    激活成功返回200状态码，激活失败返回203状态码
    """
    print(f"Activation request received - Device-Id: {device_id}")
    
    # 检查数据库连接
    if not db.connect():
        return {"success": False, "message": "数据库连接失败", "status": "failed"}, 500
    try:
        print(f"🔍 [OTA CHECK] Checking if device {device_id} is already registered...")
        
        # 查询数据库中是否存在该设备ID
        sql = "SELECT username FROM user_personas WHERE jabobo_id = %s"
        db.cursor.execute(sql, (device_id,))
        existing_device = db.cursor.fetchone()
        
        activation_index = unactivated_macs.index(device_id)
        
        
        # 根据设备ID是否存在来检查是否激活成功
        if existing_device:
            # 如果设备ID已存在，返回200状态码
            print(f"✅ [OTA CHECK] Device {device_id} is already registered to user: {existing_device.get('username', 'unknown')}")
            unactivated_macs.pop(activation_index)
            activation_codes.pop(activation_index)
            # 返回200状态码表示激活成功
            return 200

        else:
            # 如果设备ID不存在，返回203状态码
            print(f"❌ [OTA CHECK] Device {device_id} is not registered, activation failed.")
            # 延迟5秒
            time.sleep(5)
            return  203
    except Exception as e:
        print(f"❌ [ACTIVATION] Activation failed with error: {str(e)}")
        # 延迟5秒
        time.sleep(5)
        # 返回203状态码表示激活失败
        return 203
    finally:
        db.close()