from fastapi import APIRouter, HTTPException, Header, Depends
from app.models.user import UserCreateRequest, PasswordUpdateRequest
from app.database import db
from passlib.context import CryptContext

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 核心依赖：验证登录状态与身份
def get_current_user(x_username: str = Header(...), authorization: str = Header(...)):
    if not db.connect():
        raise HTTPException(status_code=500)
    try:
        user = db.query_user(x_username)
        # 校验：数据库中的 token 必须与 Header 传来的 authorization 令牌一致
        if not user or user.get('session_token') != authorization:
            raise HTTPException(status_code=401, detail="登录已过期或身份无效")
        return user
    finally:
        db.close()

@router.get("/users")
async def list_users(current_user: dict = Depends(get_current_user)):
    # 仅限管理员查看
    if current_user['role'] != "Admin":
        raise HTTPException(status_code=403, detail="权限不足")
    
    if not db.connect(): raise HTTPException(status_code=500)
    try:
        db.cursor.execute("SELECT id, username, role, create_time FROM user_login")
        users = db.cursor.fetchall()
        for u in users:
            if u['create_time']:
                u['create_time'] = u['create_time'].strftime("%Y-%m-%d %H:%M:%S")
        return {"success": True, "data": users}
    finally:
        db.close()

@router.put("/users/password")
async def update_password(
    req: PasswordUpdateRequest, 
    current_user: dict = Depends(get_current_user)
):
    """
    修改密码安全逻辑：
    1. 必须提供有效的 Token（已登录）
    2. 管理员可改任何账号
    3. 普通用户仅能将 req.username 设置为自己的名字
    """
    if not db.connect(): raise HTTPException(status_code=500)
    try:
        is_admin = current_user['role'] == "Admin"
        is_modifying_self = current_user['username'] == req.username

        if not (is_admin or is_modifying_self):
            raise HTTPException(status_code=403, detail="无权修改他人密码")

        hashed_password = pwd_context.hash(req.new_password)
        db.cursor.execute(
            "UPDATE user_login SET password = %s WHERE username = %s",
            (hashed_password, req.username)
        )
        return {"success": True, "message": "密码修改成功"}
    finally:
        db.close()

@router.post("/users")
async def create_user(req: UserCreateRequest, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != "Admin":
        raise HTTPException(status_code=403, detail="权限不足")
    
    if not db.connect(): raise HTTPException(status_code=500)
    try:
        hashed_password = pwd_context.hash(req.password)
        sql = "INSERT INTO user_login (username, password, role) VALUES (%s, %s, %s)"
        db.cursor.execute(sql, (req.username, hashed_password, req.role))
        return {"success": True, "message": "创建成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()