import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from app.database import db
from app.utils.security import get_valid_cursor

# 导入 loguru
from loguru import logger

router = APIRouter()

# APP 文件存放的物理路径
APK_DIRECTORY = "/var/local/jobobo-backend/app/app_packages"
APK_NAME = "jabobo.apk"

# 1. 获取最新版本信息
@router.get("/app/latest-version")
async def get_latest_version():
    db_connected = False
    try:
        db_connected = db.connect()
        if not db_connected:
            # 使用 logger.error 记录数据库失败
            logger.error("❌ [VERSION CHECK] 数据库连接失败")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        cursor = get_valid_cursor()
        
        sql = """
            SELECT version_name, version_code, update_log, download_url 
            FROM app_versions 
            ORDER BY version_code DESC LIMIT 1
        """
        cursor.execute(sql)
        version_info = cursor.fetchone()

        if not version_info:
            logger.warning("⚠️ [VERSION CHECK] 数据库中未发现版本记录，返回硬编码默认值")
            return {
                "success": True,
                "data": {
                    "version_name": "1.0.0",
                    "version_code": 1,
                    "update_log": "初始版本发布",
                    "download_url": "https://jabobo.com/api/app/download"
                }
            }

        # 替换 print 为 logger.info，Loguru 会自动带上时间戳
        logger.info(f"🔍 [APP VERSION] Checked | Latest Version: {version_info.get('version_name')}")
        
        return {
            "success": True,
            "data": version_info
        }
    except Exception as e:
        # 使用 logger.exception 会自动捕获详细的报错堆栈信息
        logger.exception(f"🔥 [VERSION ERROR] 获取版本信息时发生异常: {str(e)}")
        raise HTTPException(status_code=500, detail="获取版本信息失败")
    finally:
        if db_connected and hasattr(db, 'connection') and db.connection:
            db.close()

# 2. APP 下载接口
@router.get("/app/download")
async def download_app():
    file_path = os.path.join(APK_DIRECTORY, APK_NAME)
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        logger.error(f"❌ [DOWNLOAD ERROR] 文件不存在: {file_path}")
        raise HTTPException(status_code=404, detail="安装包文件不存在，请联系管理员")

    # 替换 print 为 logger.success
    logger.success(f"🚀 [APP DOWNLOAD] Serving APK: {APK_NAME}")
    
    return FileResponse(
        path=file_path,
        filename="Jabobo_Latest.apk", 
        media_type="application/vnd.android.package-archive"
    )