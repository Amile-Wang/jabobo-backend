from fastapi import APIRouter, HTTPException, Header, Depends
from app.models.user import UserCreateRequest, PasswordUpdateRequest
from app.database import db
from passlib.context import CryptContext

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 核心映射：客户端类型 → 对应token字段
CLIENT_TOKEN_MAP = {
    "web": "web_token",
    "android": "android_token",
    "ios": "ios_token"
}

# 核心依赖：重构后支持多端token，默认校验web_token
def get_current_user(x_username: str = Header(...), authorization: str = Header(...)):
    # 1. 数据库连接校验
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 2. 提取并清洗token（兼容Bearer前缀）
        token = authorization.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()  # 移除Bearer前缀
        
        # 3. 查询用户基础信息
        user = db.query_user(x_username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")
        
        # 4. 校验token：优先按多端匹配，匹配不到则默认校验web_token
        token_is_valid = False
        # 第一步：遍历所有端的token字段，尝试匹配
        for token_field in CLIENT_TOKEN_MAP.values():
            if user.get(token_field) == token:
                token_is_valid = True
                break
        # 第二步：如果都匹配不到，默认校验web_token（兜底逻辑）
        if not token_is_valid:
            token_is_valid = (user.get("web_token") == token)
        
        # 5. token无效则返回401
        if not token_is_valid:
            raise HTTPException(status_code=401, detail="登录已过期或身份无效")
        
        # 6. 返回完整用户信息
        return user
    finally:
        # 确保数据库连接关闭
        db.close()

# --- 1. 获取用户列表 ---
@router.get("/users")
async def list_users(current_user: dict = Depends(get_current_user)):
    if current_user['role'] != "Admin":
        raise HTTPException(status_code=403, detail="权限不足")
    
    if not db.connect(): 
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        db.cursor.execute("SELECT id, username, role, create_time FROM user_login")
        users = db.cursor.fetchall()
        # 格式化时间
        for u in users:
            if u.get('create_time'):
                u['create_time'] = u['create_time'].strftime("%Y-%m-%d %H:%M:%S")
        return {"success": True, "data": users}
    finally:
        db.close()

# --- 2. 删除用户逻辑 ---
@router.delete("/users/{username}")
async def delete_user(
    username: str, 
    current_user: dict = Depends(get_current_user)
):
    """
    删除用户逻辑：
    1. 必须是 Admin 权限。
    2. 禁止删除自己（防止管理员误锁死系统）。
    """
    print(f"\n🗑️ [DELETE USER] Attempt by {current_user['username']} to delete {username}")

    if current_user['role'] != "Admin":
        print(f"❌ [DELETE FAILED] Permission denied for {current_user['username']}")
        raise HTTPException(status_code=403, detail="权限不足，仅管理员可删除用户")

    if current_user['username'] == username:
        print(f"❌ [DELETE FAILED] User {username} tried to delete themselves")
        raise HTTPException(status_code=400, detail="禁止删除当前登录的管理员账号")

    if not db.connect(): 
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        # 先检查用户是否存在
        db.cursor.execute("SELECT id FROM user_login WHERE username = %s", (username,))
        target = db.cursor.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="用户不存在")

        # 核心删除逻辑：删除登录信息
        db.cursor.execute("DELETE FROM user_login WHERE username = %s", (username,))
        
        # 可选：同步清理该用户的设备配置数据
        db.cursor.execute("DELETE FROM user_personas WHERE username = %s", (username,))
        
        # 提交事务
        db.cursor.connection.commit()
        
        print(f"✅ [DELETE SUCCESS] User {username} and their configs have been removed")
        return {"success": True, "message": f"用户 {username} 已成功删除"}
    
    except Exception as e:
        print(f"🔥 [DELETE ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除失败：{str(e)}")
    finally:
        db.close()

# --- 3. 修改密码 ---
@router.put("/users/password")
async def update_password(req: PasswordUpdateRequest, current_user: dict = Depends(get_current_user)):
    if not db.connect(): 
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        is_admin = current_user['role'] == "Admin"
        is_modifying_self = current_user['username'] == req.username
        if not (is_admin or is_modifying_self):
            raise HTTPException(status_code=403, detail="无权修改他人密码")

        hashed_password = pwd_context.hash(req.new_password)
        db.cursor.execute("UPDATE user_login SET password = %s WHERE username = %s", (hashed_password, req.username))
        # 提交事务
        db.cursor.connection.commit()
        
        return {"success": True, "message": "密码修改成功"}
    finally:
        db.close()

# --- 4. 创建用户 ---
@router.post("/users")
async def create_user(req: UserCreateRequest, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != "Admin":
        raise HTTPException(status_code=403, detail="权限不足")
    
    print(f"➕ [CREATE USER] Admin {current_user['username']} is creating user: {req.username}")

    if not db.connect(): 
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        hashed_password = pwd_context.hash(req.password)
        sql = "INSERT INTO user_login (username, password, role) VALUES (%s, %s, %s)"
        db.cursor.execute(sql, (req.username, hashed_password, req.role))
        # 提交事务
        db.cursor.connection.commit()
        
        return {"success": True, "message": "创建成功"}
    except Exception as e:
        print(f"❌ [CREATE FAILED] {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()