from fastapi import APIRouter, HTTPException
from app.models.user import LoginRequest
from app.database import db

# 必须使用 APIRouter
router = APIRouter()

@router.post("/login")
async def login(req: LoginRequest):
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        user = db.query_user(req.username)
        # 强制转换为字符串并去空格进行比对，防止 401 错误
        if user and str(user['password']).strip() == str(req.password).strip():
            return {
                "success": True, 
                "username": user['username'], 
                "role": user['role']
            }
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    finally:
        db.close()
