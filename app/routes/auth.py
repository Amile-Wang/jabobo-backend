import uuid
from fastapi import APIRouter, HTTPException, Depends, Header
from app.models.user import LoginRequest  # 已包含client_type字段
from app.database import db
from app.utils.security import verify_password
from app.routes.users import get_current_user

router = APIRouter()

# 核心映射：客户端类型 → 对应token字段
CLIENT_TOKEN_MAP = {
    "web": "web_token",
    "android": "android_token",
    "ios": "ios_token"
}

@router.post("/login")
async def login(req: LoginRequest):
    # 1. 数据库连接校验
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 2. 查询用户是否存在
        user = db.query_user(req.username)
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        
        # 3. 校验密码
        if not verify_password(req.password, user['password']):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        
        # 4. 生成当前客户端专属token（不同端生成不同token）
        token = str(uuid.uuid4())
        # 获取当前客户端对应的token字段（默认web）
        token_field = CLIENT_TOKEN_MAP.get(req.client_type.value, "web_token")
        
        # 5. 更新数据库：仅更新当前端的token，不覆盖其他端
        update_sql = f"UPDATE user_login SET {token_field} = %s, client_type = %s WHERE username = %s"
        db.cursor.execute(update_sql, (token, req.client_type.value, user['username']))
        
        # 6. 提交事务（关键：确保数据写入）
        db.cursor.connection.commit()
        
        # 7. 返回结果（包含客户端类型）
        return {
            "success": True,
            "username": user['username'],
            "role": user['role'],
            "token": token,
            "client_type": req.client_type.value
        }
    
    except HTTPException:
        # 放行已定义的401/500异常
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"登录处理失败：{str(e)}")
    finally:
        # 确保数据库连接最终关闭
        db.close()

@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """
    登出：仅清空当前客户端的token，不影响其他端
    current_user需包含username和client_type（从token解析）
    """
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 1. 获取当前登录的客户端类型
        client_type = current_user.get('client_type', '')
        if not client_type:
            raise HTTPException(status_code=400, detail="客户端类型未知")
        
        # 2. 获取对应token字段
        token_field = CLIENT_TOKEN_MAP.get(client_type, "web_token")
        
        # 3. 仅清空当前端的token，其他端token保留
        update_sql = f"UPDATE user_login SET {token_field} = NULL WHERE username = %s"
        db.cursor.execute(update_sql, (current_user['username'],))
        
        # 4. 提交事务
        db.cursor.connection.commit()
        
        return {"success": True, "message": f"{client_type}端退出成功，其他端不受影响"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"退出处理失败：{str(e)}")
    finally:
        db.close()

# 可选：批量登出所有端接口（按需使用）
@router.post("/logout/all")
async def logout_all(current_user: dict = Depends(get_current_user)):
    """登出所有端，清空所有token"""
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 清空所有端的token
        db.cursor.execute(
            """
            UPDATE user_login 
            SET web_token = NULL, android_token = NULL, ios_token = NULL 
            WHERE username = %s
            """,
            (current_user['username'],)
        )
        db.cursor.connection.commit()
        return {"success": True, "message": "所有端已退出登录"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量退出失败：{str(e)}")
    finally:
        db.close()