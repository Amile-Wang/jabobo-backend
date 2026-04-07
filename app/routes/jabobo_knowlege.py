from fastapi import APIRouter, Form, File, UploadFile, Header, HTTPException, Query, Request
from app.database import db
import json
import os
import shutil
from typing import List, Optional
from datetime import datetime
from app.utils.rag import generate_vector_from_txt_folder, build_rag_prompt_from_vector_file
from app.utils.security import verify_user, get_valid_cursor
from loguru import logger  # 引入 loguru

router = APIRouter()

# 配置常量
ALLOWED_EXTENSIONS = {".pdf", ".txt"}
MAX_FILE_SIZE = 30 * 1024 * 1024  # 30MB
BASE_DATA_DIR = "./data"

# --- 上传接口 ---
@router.post("/user/upload-kb")
async def upload_knowledge_base(
    jabobo_id: str = Form(...),
    file: UploadFile = File(...),
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    logger.info(f"===== 开始处理文件上传请求 ===== | 用户名：{x_username} | 设备ID：{jabobo_id} | 文件名：{file.filename}")
    
    verify_user(x_username, authorization)
    
    # 1. 校验文件后缀
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        logger.error(f"[文件校验] 失败 - 不支持的文件格式：{file_ext}")
        raise HTTPException(status_code=400, detail="仅支持 PDF 和 TXT 格式")
    logger.debug(f"[文件校验] 后缀 {file_ext} 校验通过")

    # 2. 校验文件大小
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)
    file_size_mb = round(file_size / 1024 / 1024, 2)
    if file_size > MAX_FILE_SIZE:
        logger.error(f"[文件校验] 失败 - 文件大小({file_size_mb} MB)超过限制")
        raise HTTPException(status_code=400, detail="文件大小超过 30MB 限制")
    logger.debug(f"[文件校验] 大小校验通过")

    # 3. 创建目录
    target_dir = os.path.join(BASE_DATA_DIR, x_username, jabobo_id,"kb_files")
    pkl_target_dir = os.path.join(BASE_DATA_DIR, x_username, jabobo_id,"pkl_file")
    os.makedirs(target_dir, exist_ok=True)
    os.makedirs(pkl_target_dir, exist_ok=True)
    logger.debug(f"[目录创建] 目标目录：{target_dir}")
    
    # 4. 构建文件路径
    file_path = os.path.abspath(os.path.join(target_dir, file.filename))
    
    db_connected = False
    try:
        logger.info(f"[文件存储] 开始写入文件：{file_path}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        generate_vector_from_txt_folder(target_dir, os.path.join(pkl_target_dir,"kb.pkl"))
        
        # 5. 数据库操作
        db_connected = db.connect()
        if not db_connected:
            logger.error("[数据库操作] 失败 - 数据库连接失败")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        cursor = get_valid_cursor()
        query_sql = "SELECT kb_status FROM user_personas WHERE username = %s AND jabobo_id = %s"
        cursor.execute(query_sql, (x_username, jabobo_id))
        result = cursor.fetchone()
        
        kb_path_list = []
        if result and result.get("kb_status") is not None:
            try:
                kb_path_list = json.loads(result["kb_status"])
            except json.JSONDecodeError:
                logger.warning("[数据库操作] 解析现有列表失败 - 重置为空")
        
        file_info = {
            "file_path": file_path,
            "file_name": file.filename,
            "file_size_bytes": file_size,
            "file_size_mb": file_size_mb,
            "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "upload_timestamp": datetime.now().timestamp()
        }
        
        duplicate = any(item.get("file_path") == file_path for item in kb_path_list)
        if duplicate:
            logger.info(f"[数据库操作] 文件已存在，跳过追加")
        else:
            kb_path_list.append(file_info)
        
        kb_status_json = json.dumps(kb_path_list, ensure_ascii=False)
        upsert_sql = """
            INSERT INTO user_personas (username, jabobo_id, kb_status) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE kb_status = VALUES(kb_status)
        """
        cursor.execute(upsert_sql, (x_username, jabobo_id, kb_status_json))
        db.connection.commit()
        logger.success(f"✅ [上传完成] 成功存储并同步知识库：{file.filename}")
        
        return {
            "success": True,
            "current_file_info": file_info,
            "all_kb_paths": kb_path_list,
            "message": "知识库同步成功"
        }
    
    except Exception as e:
        logger.exception(f"🔥 [上传异常] 失败：{str(e)}")
        if db_connected and db.connection:
            db.connection.rollback()
            logger.info("[数据库回滚] 已执行回滚")
        raise HTTPException(status_code=500, detail=f"文件保存异常: {str(e)}")
    finally:
        if db_connected and db.connection:
            if hasattr(db, 'cursor') and db.cursor: db.cursor.close()
            db.close()
            logger.debug("[资源释放] 数据库连接已关闭")

# --- 查询列表接口 ---
@router.get("/user/list-kb")
async def list_knowledge_base(
    jabobo_id: str = Query(..., description="设备ID"),
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    logger.info(f"===== 开始知识库查询 ===== | 用户：{x_username} | 设备：{jabobo_id}")
    verify_user(x_username, authorization)
    
    db_connected = False
    try:
        db_connected = db.connect()
        if not db_connected:
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        cursor = get_valid_cursor()
        query_sql = "SELECT kb_status FROM user_personas WHERE username = %s AND jabobo_id = %s"
        cursor.execute(query_sql, (x_username, jabobo_id))
        result = cursor.fetchone()
        
        kb_detail_list = []
        if result and result.get("kb_status"):
            kb_path_list = json.loads(result["kb_status"])
            for item in kb_path_list:
                file_path = item.get("file_path") if isinstance(item, dict) else item
                if os.path.exists(file_path):
                    file_stat = os.stat(file_path)
                    if isinstance(item, dict):
                        item.update({
                            "current_modify_time": datetime.fromtimestamp(file_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "valid"
                        })
                        kb_detail_list.append(item)
                    else:
                        kb_detail_list.append({
                            "file_path": file_path,
                            "file_name": os.path.basename(file_path),
                            "file_size_mb": round(file_stat.st_size / 1024 / 1024, 2),
                            "status": "valid (old format)"
                        })
                else:
                    logger.warning(f"[文件检查] 记录存在但物理文件丢失：{file_path}")
        
        logger.success(f"✅ [查询完成] 共找到 {len(kb_detail_list)} 条有效记录")
        return {"success": True, "total_count": len(kb_detail_list), "kb_list": kb_detail_list}
    except Exception as e:
        logger.error(f"❌ [查询异常] {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败：{str(e)}")
    finally:
        if db_connected and db.connection:
            if hasattr(db, 'cursor') and db.cursor: db.cursor.close()
            db.close()

# --- 删除接口 ---
@router.post("/user/delete-kb")
async def delete_knowledge_base(
    jabobo_id: str = Query(..., description="设备ID"),
    file_path: str = Query(..., description="要删除的文件绝对路径"),
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    logger.info(f"===== 开始删除请求 ===== | 用户：{x_username} | 路径：{file_path}")
    verify_user(x_username, authorization)
    
    if x_username not in file_path:
        logger.warning(f"🛑 [权限校验] 越权删除尝试 - 用户 {x_username} 试图删除 {file_path}")
        raise HTTPException(status_code=403, detail="无权删除该文件")
    
    db_connected = False
    try:
        db_connected = db.connect()
        cursor = get_valid_cursor()
        cursor.execute("SELECT kb_status FROM user_personas WHERE username = %s AND jabobo_id = %s", (x_username, jabobo_id))
        result = cursor.fetchone()
        
        kb_path_list = json.loads(result["kb_status"]) if result and result.get("kb_status") else []
        
        # 物理删除
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"[文件删除] 物理文件已删除：{file_path}")
        
        # 更新列表
        if kb_path_list and isinstance(kb_path_list[0], dict):
            kb_path_list = [item for item in kb_path_list if item.get("file_path") != file_path]
        else:
            if file_path in kb_path_list: kb_path_list.remove(file_path)
            
        kb_status_json = json.dumps(kb_path_list, ensure_ascii=False)
        cursor.execute("UPDATE user_personas SET kb_status = %s WHERE username = %s AND jabobo_id = %s", (kb_status_json, x_username, jabobo_id))
        db.connection.commit()
        
        # 向量更新
        target_dir = os.path.join(BASE_DATA_DIR, x_username, jabobo_id,"kb_files")
        pkl_target_dir = os.path.join(BASE_DATA_DIR, x_username, jabobo_id,"pkl_file")
        has_files = any(os.path.isfile(os.path.join(target_dir, f)) for f in os.listdir(target_dir)) if os.path.isdir(target_dir) else False
        
        if not has_files:
            if os.path.isdir(pkl_target_dir):
                for f in os.listdir(pkl_target_dir): os.remove(os.path.join(pkl_target_dir, f))
            logger.info("[向量处理] 目录已空，清理向量文件")
        else:
            generate_vector_from_txt_folder(target_dir, os.path.join(pkl_target_dir,"kb.pkl"))
            logger.info("[向量处理] 重新生成向量索引")

        logger.success(f"✅ [删除完成] 文件 {file_path} 处理成功")
        return {"success": True, "message": "删除成功"}
    except Exception as e:
        logger.exception(f"🔥 [删除异常] {str(e)}")
        if db_connected and db.connection: db.connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if db_connected and db.connection:
            if hasattr(db, 'cursor') and db.cursor: db.cursor.close()
            db.close()

def get_username_by_jabobo_id(jabobo_id: str):
    logger.debug(f"🔍 [用户查询] jabobo_id: {jabobo_id}")
    if not db.connect(): raise HTTPException(status_code=500, detail="数据库连接失败")
    cursor = get_valid_cursor()
    try:
        cursor.execute("SELECT username FROM user_personas WHERE jabobo_id = %s LIMIT 1", (jabobo_id,))
        result = cursor.fetchone()
        if not result or not result.get("username"):
            logger.error(f"❌ [用户查询] 未找到 ID: {jabobo_id}")
            raise HTTPException(status_code=404, detail="未找到用户记录")
        return result.get("username")
    finally:
        if cursor: cursor.close()

@router.post("/user/generate-rag-prompt")
async def generate_rag_prompt(
    request: Request,
    jabobo_id: Optional[str] = Query(None),
    question: Optional[str] = Query(None)
):
    logger.info(f"===== 开始 RAG 提示词生成 =====")
    if not jabobo_id or not question:
        try:
            body = await request.json()
            jabobo_id = jabobo_id or body.get("jabobo_id")
            question = question or body.get("question")
        except: pass

    if not jabobo_id or not question: raise HTTPException(status_code=422, detail="Missing params")

    db_connected = False
    try:
        db_connected = db.connect()
        username = get_username_by_jabobo_id(jabobo_id)
        pkl_path = os.path.join(BASE_DATA_DIR, username, jabobo_id, "pkl_file", "kb.pkl")
        
        if not os.path.exists(pkl_path):
            logger.warning(f"⚠️ [RAG] 向量文件不存在: {pkl_path}")
            raise HTTPException(status_code=404, detail="未构建知识库")
            
        rag_prompt = build_rag_prompt_from_vector_file(question, pkl_path)
        logger.success(f"✅ [RAG生成成功] 用户：{username} | 长度：{len(rag_prompt)}")
        return {"success": True, "rag_prompt": rag_prompt}
    except Exception as e:
        logger.error(f"🔥 [RAG异常] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if db_connected and db.connection:
            if hasattr(db, 'cursor') and db.cursor: db.cursor.close()
            db.close()