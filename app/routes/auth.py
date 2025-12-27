import uuid
from fastapi import APIRouter, HTTPException
from app.models.user import LoginRequest
from app.database import db
from app.utils.security import verify_password

router = APIRouter()

@router.post("/login")
async def login(req: LoginRequest):
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        user = db.query_user(req.username)
        if user:
            # 使用 verify_password 校验哈希
            if verify_password(req.password, user['password']):
                # 生成唯一会话令牌
                token = str(uuid.uuid4())
                # 存入数据库
                db.cursor.execute(
                    "UPDATE user_login SET session_token = %s WHERE username = %s",
                    (token, user['username'])
                )
                return {
                    "success": True, 
                    "username": user['username'], 
                    "role": user['role'],
                    "token": token  # 必须返回给前端
                }
        
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    finally:
        db.close()