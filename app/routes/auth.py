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
        
        # --- 这里的打印非常重要 ---
        if user:
            print(f"DEBUG >> 找到用户: {user['username']}")
            print(f"DEBUG >> 数据库存的密码: [{user['password']}]")
            print(f"DEBUG >> 本地发送的明文: [{req.password}]")
            
            from app.utils.security import verify_password
            match = verify_password(req.password, user['password'])
            print(f"DEBUG >> 比对结果: {match}")
            
            if match:
                return {"success": True, "username": user['username'], "role": user['role']}
        else:
            print(f"DEBUG >> 数据库里根本没找到用户: {req.username}")
        # ------------------------

        raise HTTPException(status_code=401, detail="用户名或密码错误")
    finally:
        db.close()