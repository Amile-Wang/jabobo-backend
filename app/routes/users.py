from fastapi import APIRouter, HTTPException, Header, Depends
from app.models.user import UserCreateRequest, PasswordUpdateRequest
from app.database import db
from passlib.context import CryptContext  # 引入加密库

router = APIRouter()

# 1. 初始化加密上下文：强制使用 bcrypt 算法
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 内部依赖：校验管理员权限
def verify_admin(x_username: str = Header(...)):
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        user = db.query_user(x_username)
        if not user or user.get('role') != "Admin":
            raise HTTPException(status_code=403, detail="权限不足")
        return x_username
    finally:
        db.close()

@router.get("/users")
async def list_users(admin_user: str = Depends(verify_admin)):
    if not db.connect():
        raise HTTPException(status_code=500)
    try:
        db.cursor.execute("SELECT id, username, role, create_time FROM user_login")
        users = db.cursor.fetchall()
        for u in users:
            if u['create_time']:
                u['create_time'] = u['create_time'].strftime("%Y-%m-%d %H:%M:%S")
        return {"success": True, "data": users}
    finally:
        db.close()

@router.post("/users")
async def create_user(req: UserCreateRequest, admin_user: str = Depends(verify_admin)):
    if not db.connect():
        raise HTTPException(status_code=500)
    try:
        # --- 核心修改：对新用户密码进行哈希处理 ---
        hashed_password = pwd_context.hash(req.password)
        
        sql = "INSERT INTO user_login (username, password, role) VALUES (%s, %s, %s)"
        db.cursor.execute(sql, (req.username, hashed_password, req.role))
        return {"success": True, "message": "创建成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()

@router.delete("/users/{target_username}")
async def delete_user(target_username: str, admin_user: str = Depends(verify_admin)):
    if not db.connect():
        raise HTTPException(status_code=500)
    try:
        sql = "DELETE FROM user_login WHERE username = %s"
        db.cursor.execute(sql, (target_username,))
        return {"success": True, "message": "已删除"}
    finally:
        db.close()

@router.put("/users/password")
async def update_password(req: PasswordUpdateRequest, x_username: str = Header(...)):
    if not db.connect():
        raise HTTPException(status_code=500)
    try:
        # 权限检查：管理员可以改所有人，普通用户只能改自己
        current_user = db.query_user(x_username)
        if not current_user:
            raise HTTPException(status_code=401)
        
        if current_user['role'] != "Admin" and x_username != req.username:
            raise HTTPException(status_code=403, detail="无权修改他人密码")

        # --- 核心修改：对新修改的密码进行哈希处理 ---
        hashed_password = pwd_context.hash(req.new_password)

        sql = "UPDATE user_login SET password = %s WHERE username = %s"
        db.cursor.execute(sql, (hashed_password, req.username))
        return {"success": True, "message": "修改成功"}
    finally:
        db.close()