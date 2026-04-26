import uuid
from fastapi import APIRouter, HTTPException, Depends, Header
from app.models.user import LoginRequest  # 已包含client_type字段
from app.database import db
from app.utils.security import verify_password
from app.routes.users import get_current_user
from loguru import logger  # 导入 loguru

router = APIRouter()

# 核心映射：客户端类型 → 对应token字段
CLIENT_TOKEN_MAP = {
    "web": "web_token",
    "android": "android_token",
    "ios": "ios_token"
}

@router.post("/login")
async def login(req: LoginRequest):
    # ====================== 第一步：记录请求全量信息 ======================
    logger.info("📲 登录请求接收开始")
    logger.debug(f"请求体原始数据：{req.dict()}")
    logger.debug(f"用户名：{req.username}")
    logger.debug(f"密码（密文校验前）：{req.password[:6]}****")  # 隐藏密码大部分字符
    logger.debug(f"前端传的client_type：{getattr(req, 'client_type', '未传')}")
    logger.debug(f"client_type类型：{type(getattr(req, 'client_type', None))}")

    # 1. 数据库连接校验
    db_connected = db.connect()
    logger.info(f"🔌 数据库连接结果：{db_connected}")
    if not db_connected:
        logger.error("❌ 数据库连接失败")
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 2. 查询用户是否存在
        logger.info("👤 查询用户信息")
        user = db.query_user(req.username)
        if not user:
            logger.warning(f"❌ 用户名不存在：{req.username}，抛出401")
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        
        # 3. 校验密码
        logger.info("🔐 密码校验")
        password_valid = verify_password(req.password, user['password'])
        if not password_valid:
            logger.warning(f"❌ 密码错误：{req.username}，抛出401")
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        
        # ========== 核心：客户端类型处理（带详细日志） ==========
        logger.info("📱 客户端类型处理")
        raw_client_type = getattr(req, "client_type", "web")
        logger.debug(f"原始client_type：{raw_client_type}")
        
        client_type_lower = raw_client_type.lower() if raw_client_type and raw_client_type != "" else "web"
        logger.debug(f"转小写后client_type：{client_type_lower}")
        
        token_field = CLIENT_TOKEN_MAP.get(client_type_lower, "web_token")
        logger.debug(f"匹配的token字段：{token_field}（映射表：{CLIENT_TOKEN_MAP}）")
        
        # 4. 生成当前客户端专属token
        logger.info("🔑 生成专属token")
        token = str(uuid.uuid4())
        logger.debug(f"生成的token：{token}")
        
        # 5. 数据库更新操作（带SQL日志）
        logger.info("🗄️ 数据库更新操作")
        update_sql = f"UPDATE user_login SET {token_field} = %s WHERE username = %s"
        logger.debug(f"更新SQL：{update_sql}")
        logger.debug(f"SQL参数：token={token}, username={user['username']}")
        
        db.cursor.execute(update_sql, (token, user['username']))
        affected_rows = db.cursor.rowcount
        logger.debug(f"SQL执行影响行数：{affected_rows}")
        
        # 6. 提交事务（带验证）
        logger.info("✅ 提交数据库事务")
        try:
            db.cursor.connection.commit()
            logger.success("事务提交成功")
        except Exception as e:
            logger.error(f"❌ 事务提交失败：{str(e)}")
            raise
        
        # 7. 验证更新结果（关键：查询数据库确认）
        logger.info("🔍 验证数据库更新结果")
        db.cursor.execute(f"SELECT username, web_token, android_token, ios_token FROM user_login WHERE username = %s", (user['username'],))
        updated_user = db.cursor.fetchone()
        logger.debug(f"更新后用户token信息：{updated_user}")
        
        # 8. 返回结果
        logger.success("📤 登录成功，准备返回结果")
        return {
            "success": True,
            "username": user['username'],
            "role": user['role'],
            "token": token,
            "client_type": client_type_lower,
            "token_field_updated": token_field,
            "database_updated_verify": {
                "web_token": updated_user.get("web_token"),
                "android_token": updated_user.get("android_token"),
                "ios_token": updated_user.get("ios_token")
            }
        }
    
    except HTTPException as he:
        logger.warning(f"❌ 业务异常：{he.status_code} - {he.detail}")
        raise
    except Exception as e:
        logger.exception(f"🔥 系统异常：{str(e)}") # 使用exception可以记录堆栈信息
        raise HTTPException(status_code=500, detail=f"登录处理失败：{str(e)}")
    finally:
        logger.info("🔌 关闭数据库连接")
        db.close()
        logger.info("📲 登录请求处理结束")

@router.get("/auth/whoami")
async def whoami(current_user: dict = Depends(get_current_user)):
    return {"username": current_user["username"], "role": current_user["role"]}

@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """
    登出：仅清空当前客户端的token，不影响其他端
    """
    if not db.connect():
        logger.error("❌ 数据库连接失败")
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        client_type = current_user.get('client_type', '')
        if not client_type:
            logger.warning("❌ 客户端类型未知")
            raise HTTPException(status_code=400, detail="客户端类型未知")
        
        token_field = CLIENT_TOKEN_MAP.get(client_type, "web_token")
        
        update_sql = f"UPDATE user_login SET {token_field} = NULL WHERE username = %s"
        db.cursor.execute(update_sql, (current_user['username'],))
        db.cursor.connection.commit()
        
        logger.success(f"👋 {client_type}端退出成功，其他端不受影响")
        return {"success": True, "message": f"{client_type}端退出成功，其他端不受影响"}
    
    except Exception as e:
        logger.exception(f"🔥 退出处理失败：{str(e)}")
        raise HTTPException(status_code=500, detail=f"退出处理失败：{str(e)}")
    finally:
        db.close()

@router.post("/logout/all")
async def logout_all(current_user: dict = Depends(get_current_user)):
    """登出所有端，清空所有token"""
    if not db.connect():
        logger.error("❌ 数据库连接失败")
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        db.cursor.execute(
            """
            UPDATE user_login 
            SET web_token = NULL, android_token = NULL, ios_token = NULL 
            WHERE username = %s
            """,
            (current_user['username'],)
        )
        db.cursor.connection.commit()
        logger.success(f"🚫 用户 {current_user['username']} 所有端已退出登录")
        return {"success": True, "message": "所有端已退出登录"}
    
    except Exception as e:
        logger.exception(f"🔥 批量退出失败：{str(e)}")
        raise HTTPException(status_code=500, detail=f"批量退出失败：{str(e)}")
    finally:
        db.close()