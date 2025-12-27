from fastapi import APIRouter, HTTPException, Header
from app.database import db
import json

router = APIRouter()

@router.get("/user/config")
async def get_user_config(
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    try:
        # 1. 身份校验
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()
        if not user or user.get('session_token') != authorization:
            raise HTTPException(status_code=401, detail="身份验证失败")

        # 2. 查询数据
        db.cursor.execute(
            "SELECT content, memory FROM user_personas WHERE username = %s", 
            (x_username,)
        )
        config = db.cursor.fetchone()
        
        # --- [GET] 拆分打印逻辑 ---
        print(f"\n>>>>>> [GET CONFIG] User: {x_username} <<<<<<")
        raw_persona = config.get('content', "[]") if config else "[]"
        memory_data = config.get('memory', "") if config else ""
        
        try:
            personas = json.loads(raw_persona)
            print(f"Total Personas Found: {len(personas)}")
            for i, p in enumerate(personas):
                print(f"  Persona #{i+1} | Name: {p.get('name')} | Content: {p.get('content')[:50]}...")
        except:
            print(f"  Persona Raw Data: {raw_persona}")
            
        print(f"Memory Data: {memory_data}")
        print(f">>>>>> [GET END] <<<<<<\n")

        return {
            "success": True, 
            "data": {
                "persona": raw_persona,
                "memory": memory_data,
                "voice_status": "已就绪",
                "kb_status": "已同步"
            }
        }
    finally:
        db.close()

@router.post("/user/sync-config")
async def sync_config(
    payload: dict, 
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    if not db.connect():
        raise HTTPException(status_code=500)
        
    try:
        # 身份校验
        db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
        user = db.cursor.fetchone()
        if not user or user.get('session_token') != authorization:
            raise HTTPException(status_code=401)

        persona_json = payload.get('persona', '[]')
        memory = payload.get('memory', '')

        # --- [SYNC] 拆分打印逻辑 ---
        print(f"\n====== [SYNC CONFIG] User: {x_username} ======")
        print(f"Received Memory: {memory}")
        
        try:
            personas_list = json.loads(persona_json)
            print(f"Received {len(personas_list)} Personas to Sync:")
            for idx, p in enumerate(personas_list):
                # 每一个 Persona 独立打印一行
                p_name = p.get('name', '未命名')
                p_content = p.get('content', '')
                print(f"  -> Persona {idx+1} | Name: {p_name} | Content: {p_content}")
        except Exception as e:
            print(f"  Error parsing persona_json: {e}")
            print(f"  Raw persona_json: {persona_json}")
            
        print(f"====== [SYNC END] ======\n")

        # 插入或更新数据库
        sql = """
            INSERT INTO user_personas (username, content, memory) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE content = VALUES(content), memory = VALUES(memory)
        """
        db.cursor.execute(sql, (x_username, persona_json, memory))
        
        return {"success": True, "message": "全量数据同步成功"}
    except Exception as e:
        print(f"Sync Error: {str(e)}")
        raise HTTPException(status_code=500, detail="服务器内部错误")
    finally:
        db.close()