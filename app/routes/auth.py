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

import uuid
from fastapi import APIRouter, HTTPException, Depends, Header
from app.models.user import LoginRequest
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
    # ====================== 第一步：打印请求全量信息 ======================
    print("\n" + "="*50)
    print("📲 登录请求接收开始")
    print("="*50)
    print(f"请求体原始数据：{req.dict()}")
    print(f"用户名：{req.username}")
    print(f"密码（密文校验前）：{req.password[:6]}****")  # 隐藏密码大部分字符
    print(f"前端传的client_type：{getattr(req, 'client_type', '未传')}")
    print(f"client_type类型：{type(getattr(req, 'client_type', None))}")

    # 1. 数据库连接校验
    print("\n🔌 数据库连接校验")
    db_connected = db.connect()
    print(f"数据库连接结果：{db_connected}")
    if not db_connected:
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 2. 查询用户是否存在
        print("\n👤 查询用户信息")
        user = db.query_user(req.username)
        print(f"用户查询结果：{user if user else '用户不存在'}")
        if not user:
            print("❌ 用户名不存在，抛出401")
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        
        # 3. 校验密码
        print("\n🔐 密码校验")
        password_valid = verify_password(req.password, user['password'])
        print(f"密码校验结果：{password_valid}")
        if not password_valid:
            print("❌ 密码错误，抛出401")
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        
        # ========== 核心：客户端类型处理（带详细日志） ==========
        print("\n📱 客户端类型处理")
        # 获取client_type（兼容各种情况）
        raw_client_type = getattr(req, "client_type", "web")
        print(f"原始client_type：{raw_client_type}")
        
        # 转小写 + 处理可能的None/空值
        client_type_lower = raw_client_type.lower() if raw_client_type and raw_client_type != "" else "web"
        print(f"转小写后client_type：{client_type_lower}")
        
        # 匹配token字段
        token_field = CLIENT_TOKEN_MAP.get(client_type_lower, "web_token")
        print(f"匹配的token字段：{token_field}（映射表：{CLIENT_TOKEN_MAP}）")
        
        # 4. 生成当前客户端专属token
        print("\n🔑 生成专属token")
        token = str(uuid.uuid4())
        print(f"生成的token：{token}")
        
        # 5. 数据库更新操作（带SQL日志）
        print("\n🗄️ 数据库更新操作")
        update_sql = f"UPDATE user_login SET {token_field} = %s WHERE username = %s"
        print(f"更新SQL：{update_sql}")
        print(f"SQL参数：token={token}, username={user['username']}")
        
        # 执行更新
        db.cursor.execute(update_sql, (token, user['username']))
        affected_rows = db.cursor.rowcount
        print(f"SQL执行影响行数：{affected_rows}")
        
        # 6. 提交事务（带验证）
        print("\n✅ 提交数据库事务")
        try:
            db.cursor.connection.commit()
            print("事务提交成功")
        except Exception as e:
            print(f"❌ 事务提交失败：{str(e)}")
            raise
        
        # 7. 验证更新结果（关键：查询数据库确认）
        print("\n🔍 验证数据库更新结果")
        db.cursor.execute(f"SELECT username, web_token, android_token, ios_token FROM user_login WHERE username = %s", (user['username'],))
        updated_user = db.cursor.fetchone()
        print(f"更新后用户token信息：{updated_user}")
        
        # 8. 返回结果
        print("\n📤 登录成功，返回结果")
        return {
            "success": True,
            "username": user['username'],
            "role": user['role'],
            "token": token,
            "client_type": client_type_lower,
            "token_field_updated": token_field,
            "database_updated_verify": {  # 新增：返回数据库更新后的token值，便于前端验证
                "web_token": updated_user.get("web_token"),
                "android_token": updated_user.get("android_token"),
                "ios_token": updated_user.get("ios_token")
            }
        }
    
    except HTTPException as he:
        print(f"\n❌ 业务异常：{he.status_code} - {he.detail}")
        raise
    except Exception as e:
        print(f"\n🔥 系统异常：{str(e)}")
        raise HTTPException(status_code=500, detail=f"登录处理失败：{str(e)}")
    finally:
        print("\n🔌 关闭数据库连接")
        db.close()
        print("="*50)
        print("📲 登录请求处理结束")
        print("="*50 + "\n")

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