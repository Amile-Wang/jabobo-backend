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