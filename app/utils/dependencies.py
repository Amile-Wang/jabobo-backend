# app/dependencies.py
from fastapi import Header, HTTPException
from app.database import db

async def get_current_user(x_username: str = Header(...), authorization: str = Header(...)):
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        user = db.query_user(x_username)
        if not user or user.get('session_token') != authorization:
            raise HTTPException(status_code=401, detail="身份验证失败")
        return user
    finally:
        db.close()