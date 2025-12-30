from fastapi import APIRouter, Form, File, UploadFile, Header, HTTPException
from app.database import db
import json

router = APIRouter()

# --- 辅助函数：统一身份验证 ---
def verify_user(x_username, authorization):
    db.cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
    user = db.cursor.fetchone()
    if not user or user.get('session_token') != authorization:
        raise HTTPException(status_code=401, detail="身份验证失败")
    return user

import os
import json
import shutil


router = APIRouter()

# 配置常量（若已在其他文件定义，可删除此处）
ALLOWED_EXTENSIONS = {".pdf", ".txt"}
MAX_FILE_SIZE = 30 * 1024 * 1024  # 30MB
BASE_DATA_DIR = "./data"  # 你的基础数据目录，按需修改

@router.post("/user/upload-kb")
async def upload_knowledge_base(
    jabobo_id: str = Form(...),
    file: UploadFile = File(...),
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    # 验证用户权限
    await verify_user(x_username, authorization)
    
    # 1. 校验文件后缀
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 PDF 和 TXT 格式")

    # 2. 校验文件大小
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)  # 重置文件指针，避免保存空白文件
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过 30MB 限制")

    # 3. 创建多层级目录: data/{username}/{jabobo_id}/
    target_dir = os.path.join(BASE_DATA_DIR, x_username, jabobo_id)
    os.makedirs(target_dir, exist_ok=True)
    
    # 4. 保存文件到本地磁盘（转绝对路径，避免相对路径问题）
    file_path = os.path.join(target_dir, file.filename)
    file_path = os.path.abspath(file_path)
    
    try:
        # 保存文件到本地
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 5. 数据库操作：读取现有路径列表，追加新路径
        # 第一步：确保数据库连接成功
        if not db.connect():
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 第二步：查询当前用户+设备的kb_status（JSON列表）
        query_sql = "SELECT kb_status FROM user_personas WHERE username = %s AND jabobo_id = %s"
        db.cursor.execute(query_sql, (x_username, jabobo_id))
        result = db.cursor.fetchone()  # DictCursor返回字典，而非元组
        
        # 第三步：处理现有路径列表（适配DictCursor和NULL）
        # result是字典，key为kb_status；若无数据则result为None
        if result and result.get("kb_status") is not None:
            # 解析JSON为Python列表
            try:
                kb_path_list = json.loads(result["kb_status"])
            except json.JSONDecodeError:
                # 若数据库中格式错误，重置为空列表
                kb_path_list = []
        else:
            kb_path_list = []
        
        # 第四步：追加新路径（去重）
        if file_path not in kb_path_list:
            kb_path_list.append(file_path)
        
        # 第五步：序列化为JSON字符串，插入/更新数据库
        kb_status_json = json.dumps(kb_path_list, ensure_ascii=False)
        upsert_sql = """
            INSERT INTO user_personas (username, jabobo_id, kb_status) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE kb_status = VALUES(kb_status)
        """
        db.cursor.execute(upsert_sql, (x_username, jabobo_id, kb_status_json))
        
        # 关键：因autocommit=True，无需手动commit；若要手动控制，可打开下面注释
        # if db.connection:
        #     db.connection.commit()
        
        print(f"📁 [FILE SAVED] Path: {file_path} | All Paths: {kb_path_list}")
        return {
            "success": True,
            "current_path": file_path,
            "all_kb_paths": kb_path_list,
            "message": "知识库同步成功"
        }
    
    except Exception as e:
        # 出错时回滚（仅当autocommit=False时需要，此处保留兼容）
        if db.connection:
            try:
                db.connection.rollback()
            except:
                pass  # 忽略回滚失败（比如连接已断开）
        raise HTTPException(status_code=500, detail=f"文件保存异常: {str(e)}")
    finally:
        # 确保数据库连接关闭
        db.close()