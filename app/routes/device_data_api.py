from fastapi import APIRouter, HTTPException, Query
from app.database import db  # 复用你已有的数据库实例

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
    # 转换为上海时区的时间戳（秒），然后乘以1000得到毫秒
    # 上海时区是UTC+8，所以需要加上8*3600秒
    timestamp = int(time.mktime(now.timetuple()) * 1000 + now.microsecond / 1000)
    
    # 生成激活码 - 这里使用设备MAC地址的后6位作为激活码（模拟）
    mac_address = device_info.get("mac_address", "00:00:00:00:00:00")
    activation_code = mac_address.replace(":", "")[-6:].upper()
    
    # 构造响应，按照设备期望的格式
    response_data = {
        "server_time": {
            "timestamp": timestamp,
            "timeZone": "Asia/Shanghai",
            "timezone_offset": 480  # 时区偏移分钟数（GMT+8 = 480分钟）
        },
        "activation": {
            "code": activation_code,
            "message": f"http://xiaozhi.server.com\n{activation_code}",
            "challenge": mac_address  # 使用MAC地址作为挑战码
        },
        "firmware": {
            "version": device_info.get("version", "2.0.2"),  # 使用设备当前版本
            "url": "http://xiaozhi.server.com:8002/xiaozhi/otaMag/download/NOT_ACTIVATED_FIRMWARE_THIS_IS_A_INVALID_URL"
        },
        "websocket": {
            "url": "ws://121.41.168.85:8000/xiaozhi/v1/"
        }
    }
    
    return response_data