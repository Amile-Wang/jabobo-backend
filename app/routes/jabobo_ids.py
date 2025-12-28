from fastapi import APIRouter, HTTPException, Header, Query
from app.database import db
import json

router = APIRouter()

# 1. 获取 ID 列表接口
@router.get("/user/jabobo_ids")
async def get_user_jabobo_ids(
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    try:
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()
        if not user or user.get('session_token') != authorization:
            raise HTTPException(status_code=401, detail="身份验证失败")

        db.cursor.execute("SELECT jabobo_id FROM user_personas WHERE username = %s", (x_username,))
        rows = db.cursor.fetchall()
        ids = [row['jabobo_id'] for row in rows]
        
        print(f"📋 [LIST DEVICES] User: {x_username} | Found IDs: {ids}")
        return {"success": True, "jabobo_ids": ids}
    finally:
        db.close()