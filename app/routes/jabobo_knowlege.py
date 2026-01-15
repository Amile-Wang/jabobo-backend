from fastapi import APIRouter, Form, File, UploadFile, Header, HTTPException, Query, Request
from app.database import db
import json
import os
import shutil
from typing import List, Optional
from datetime import datetime  # 处理时间戳
from app.utils.rag import generate_vector_from_txt_folder, build_rag_prompt_from_vector_file
# 全局Router（仅定义一次）
router = APIRouter()
from app.utils.security import verify_user, get_valid_cursor

# 配置常量
ALLOWED_EXTENSIONS = {".pdf", ".txt"}
MAX_FILE_SIZE = 30 * 1024 * 1024  # 30MB
BASE_DATA_DIR = "./data"

# --- 上传接口（修复游标+事务提交）---
@router.post("/user/upload-kb")
async def upload_knowledge_base(
    jabobo_id: str = Form(...),
    file: UploadFile = File(...),
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    print(f"\n===== 开始处理文件上传请求 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[请求信息] 用户名：{x_username} | 设备ID：{jabobo_id} | 文件名：{file.filename}")
    
    # 验证用户权限（内部已处理游标）
    verify_user(x_username, authorization)
    
    # 1. 校验文件后缀
    print(f"\n[文件校验] 开始校验文件后缀 - 文件名：{file.filename}")
    file_ext = os.path.splitext(file.filename)[1].lower()
    print(f"[文件校验] 文件后缀：{file_ext} | 允许的后缀：{ALLOWED_EXTENSIONS}")
    if file_ext not in ALLOWED_EXTENSIONS:
        print(f"[文件校验] 失败 - 不支持的文件格式：{file_ext}")
        raise HTTPException(status_code=400, detail="仅支持 PDF 和 TXT 格式")
    print(f"[文件校验] 后缀校验通过")

    # 2. 校验文件大小
    print(f"\n[文件校验] 开始校验文件大小 - 文件名：{file.filename}")
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)  # 重置文件指针
    file_size_mb = round(file_size / 1024 / 1024, 2)
    print(f"[文件校验] 文件大小：{file_size} 字节 ({file_size_mb} MB) | 最大允许：{MAX_FILE_SIZE / 1024 / 1024} MB")
    if file_size > MAX_FILE_SIZE:
        print(f"[文件校验] 失败 - 文件大小超过限制")
        raise HTTPException(status_code=400, detail="文件大小超过 30MB 限制")
    print(f"[文件校验] 大小校验通过")

    # 3. 创建目录
    print(f"\n[目录创建] 开始创建存储目录")
    target_dir = os.path.join(BASE_DATA_DIR, x_username, jabobo_id,"kb_files")
    pkl_target_dir = os.path.join(BASE_DATA_DIR, x_username, jabobo_id,"pkl_file")

    print(f"[目录创建] 目标目录：{target_dir}")
    os.makedirs(target_dir, exist_ok=True)
    os.makedirs(pkl_target_dir, exist_ok=True)

    print(f"[目录创建] 目录创建完成（已存在则跳过）")
    
    # 4. 构建文件路径
    file_path = os.path.join(target_dir, file.filename)
    file_path = os.path.abspath(file_path)
    print(f"\n[文件存储] 目标文件路径：{file_path}")
    
    db_connected = False
    try:
        # 保存文件到本地
        print(f"[文件存储] 开始写入文件 - 文件名：{file.filename} | 路径：{file_path}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print(f"[文件存储] 文件写入完成 - 实际文件大小：{os.path.getsize(file_path)} 字节")
        generate_vector_from_txt_folder(target_dir,os.path.join(pkl_target_dir,"kb.pkl"))
        
        # 5. 数据库操作
        print(f"\n[数据库操作] 开始处理数据库逻辑")
        db_connected = db.connect()
        if not db_connected:
            print(f"[数据库操作] 失败 - 数据库连接失败")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 获取有效游标
        cursor = get_valid_cursor()
        
        # 查询现有记录
        query_sql = "SELECT kb_status FROM user_personas WHERE username = %s AND jabobo_id = %s"
        print(f"[数据库操作] 执行查询SQL：{query_sql} | 参数：({x_username}, {jabobo_id})")
        cursor.execute(query_sql, (x_username, jabobo_id))
        result = cursor.fetchone()
        print(f"[数据库操作] 查询结果：{result}")
        
        # 解析现有路径列表
        if result and result.get("kb_status") is not None:
            try:
                kb_path_list = json.loads(result["kb_status"])
                print(f"[数据库操作] 解析现有知识库列表成功 - 列表长度：{len(kb_path_list)}")
            except json.JSONDecodeError:
                print(f"[数据库操作] 解析现有知识库列表失败 - 重置为空列表")
                kb_path_list = []
        else:
            print(f"[数据库操作] 无现有知识库记录 - 初始化空列表")
            kb_path_list = []
        
        # 构建文件信息（含时间戳+文件大小）
        file_info = {
            "file_path": file_path,
            "file_name": file.filename,
            "file_size_bytes": file_size,
            "file_size_mb": file_size_mb,
            "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "upload_timestamp": datetime.now().timestamp()
        }
        print(f"[数据库操作] 构建文件信息：{file_info}")
        
        # 去重检查
        duplicate = any(item.get("file_path") == file_path for item in kb_path_list)
        if duplicate:
            print(f"[数据库操作] 文件已存在，跳过追加 - 路径：{file_path}")
        else:
            kb_path_list.append(file_info)
            print(f"[数据库操作] 文件信息追加完成 - 新列表长度：{len(kb_path_list)}")
        
        # 插入/更新数据库
        kb_status_json = json.dumps(kb_path_list, ensure_ascii=False)
        upsert_sql = """
            INSERT INTO user_personas (username, jabobo_id, kb_status) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE kb_status = VALUES(kb_status)
        """
        print(f"[数据库操作] 执行更新SQL：{upsert_sql} | 参数：({x_username}, {jabobo_id}, {kb_status_json[:100]}...)")
        cursor.execute(upsert_sql, (x_username, jabobo_id, kb_status_json))
        
        # 核心修复：提交事务
        db.connection.commit()
        print(f"[数据库操作] 事务提交成功")
        
        print(f"\n[上传完成] 成功 - 文件路径：{file_path} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"===== 上传请求处理完成 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        return {
            "success": True,
            "current_file_info": file_info,
            "all_kb_paths": kb_path_list,
            "message": "知识库同步成功"
        }
    
    except Exception as e:
        print(f"\n[上传异常] 失败 - 异常信息：{str(e)} | 堆栈：{e.__traceback__} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if db_connected and db.connection:
            try:
                print(f"[数据库回滚] 开始回滚事务")
                db.connection.rollback()
                print(f"[数据库回滚] 回滚完成")
            except Exception as rollback_e:
                print(f"[数据库回滚] 失败 - 异常：{str(rollback_e)}")
        raise HTTPException(status_code=500, detail=f"文件保存异常: {str(e)}")
    finally:
        print(f"\n[资源释放] 关闭数据库连接 - 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if db_connected and db.connection:
            try:
                # 先关闭游标再关闭连接
                if hasattr(db, 'cursor') and db.cursor:
                    db.cursor.close()
                db.close()
            except Exception as close_e:
                print(f"[资源释放] 关闭连接失败：{str(close_e)}")
        print(f"[资源释放] 数据库连接已关闭\n")

# --- 查询列表接口（修复游标+连接管理）---
@router.get("/user/list-kb")
async def list_knowledge_base(
    jabobo_id: str = Query(..., description="设备ID"),
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    print(f"\n===== 开始处理知识库查询请求 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[请求信息] 用户名：{x_username} | 设备ID：{jabobo_id}")
    
    # 身份验证（内部已处理游标）
    verify_user(x_username, authorization)
    
    db_connected = False
    try:
        print(f"\n[数据库操作] 开始查询知识库列表")
        db_connected = db.connect()
        if not db_connected:
            print(f"[数据库操作] 失败 - 数据库连接失败")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 获取有效游标
        cursor = get_valid_cursor()
        
        # 执行查询
        query_sql = "SELECT kb_status FROM user_personas WHERE username = %s AND jabobo_id = %s"
        print(f"[数据库操作] 执行查询SQL：{query_sql} | 参数：({x_username}, {jabobo_id})")
        cursor.execute(query_sql, (x_username, jabobo_id))
        result = cursor.fetchone()
        print(f"[数据库操作] 查询结果：{result}")
        
        # 处理查询结果
        kb_detail_list = []
        if result and result.get("kb_status") is not None:
            try:
                kb_path_list = json.loads(result["kb_status"])
                print(f"[数据解析] 解析JSON成功 - 列表长度：{len(kb_path_list)}")
                
                for idx, item in enumerate(kb_path_list):
                    print(f"[数据处理] 处理第 {idx+1} 条记录：{item}")
                    if isinstance(item, dict):
                        file_path = item.get("file_path")
                        print(f"[文件检查] 检查文件是否存在：{file_path}")
                        if os.path.exists(file_path):
                            file_stat = os.stat(file_path)
                            item.update({
                                "current_modify_time": datetime.fromtimestamp(file_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                                "status": "valid"
                            })
                            print(f"[文件检查] 存在 - 文件大小：{os.path.getsize(file_path)} 字节")
                        else:
                            item["status"] = "invalid (file not exists)"
                            print(f"[文件检查] 不存在")
                        kb_detail_list.append(item)
                    else:
                        # 兼容旧格式
                        file_path = item
                        print(f"[数据兼容] 旧格式路径：{file_path}")
                        if os.path.exists(file_path):
                            file_stat = os.stat(file_path)
                            kb_detail_list.append({
                                "file_path": file_path,
                                "file_name": os.path.basename(file_path),
                                "file_size_mb": round(file_stat.st_size / 1024 / 1024, 2),
                                "modify_time": f"{file_stat.st_mtime}",
                                "status": "valid (old format)"
                            })
                        else:
                            kb_detail_list.append({
                                "file_path": file_path,
                                "file_name": os.path.basename(file_path),
                                "status": "invalid (file not exists, old format)"
                            })
            except json.JSONDecodeError as e:
                print(f"[数据解析] 失败 - JSON解析异常：{str(e)}")
                kb_detail_list = []
        else:
            print(f"[数据处理] 无知识库记录")
            kb_detail_list = []
        
        print(f"\n[查询完成] 成功 - 共查询到 {len(kb_detail_list)} 条记录 | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"===== 查询请求处理完成 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        return {
            "success": True,
            "total_count": len(kb_detail_list),
            "kb_list": kb_detail_list,
            "message": "知识库列表查询成功"
        }
    except Exception as e:
        print(f"\n[查询异常] 失败 - 异常信息：{str(e)} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if db_connected and db.connection:
            try:
                db.connection.rollback()
            except:
                pass
        raise HTTPException(status_code=500, detail=f"查询知识库列表失败：{str(e)}")
    finally:
        print(f"\n[资源释放] 关闭数据库连接 - 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if db_connected and db.connection:
            try:
                if hasattr(db, 'cursor') and db.cursor:
                    db.cursor.close()
                db.close()
            except Exception as close_e:
                print(f"[资源释放] 关闭连接失败：{str(close_e)}")
        print(f"[资源释放] 数据库连接已关闭\n")

# --- 删除接口（修复游标+事务提交）---
@router.delete("/user/delete-kb")
async def delete_knowledge_base(
    jabobo_id: str = Query(..., description="设备ID"),
    file_path: str = Query(..., description="要删除的文件绝对路径"),
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    # 打印删除请求开始日志，包含时间戳，便于排查问题
    print(f"\n===== 开始处理文件删除请求 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[请求信息] 用户名：{x_username} | 设备ID：{jabobo_id} | 要删除的文件路径：{file_path}")
    
    # 1. 身份验证：校验用户token/权限合法性
    verify_user(x_username, authorization)
    
    # 2. 安全校验：防止越权删除，检查文件路径是否归属当前用户
    print(f"\n[权限校验] 检查文件是否属于当前用户")
    if x_username not in file_path:
        print(f"[权限校验] 失败 - 文件路径不含用户名 {x_username}")
        raise HTTPException(status_code=403, detail="无权删除该文件（路径不属于当前用户）")
    print(f"[权限校验] 通过")
    
    db_connected = False
    try:
        # 3. 数据库操作：查询用户知识库记录，确认文件是否在用户的知识库列表中
        print(f"\n[数据库操作] 开始查询知识库记录")
        # 检查数据库连接状态
        db_connected = db.connect()
        if not db_connected:
            print(f"[数据库操作] 失败 - 数据库连接失败")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 获取有效数据库游标（用于执行SQL）
        cursor = get_valid_cursor()
        
        # 执行查询：获取用户对应设备的知识库状态（kb_status存储文件路径列表）
        query_sql = "SELECT kb_status FROM user_personas WHERE username = %s AND jabobo_id = %s"
        print(f"[数据库操作] 执行查询SQL：{query_sql} | 参数：({x_username}, {jabobo_id})")
        cursor.execute(query_sql, (x_username, jabobo_id))
        result = cursor.fetchone()
        print(f"[数据库操作] 查询结果：{result}")
        
        # 解析知识库路径列表：兼容JSON格式存储的路径列表
        if result and result.get("kb_status") is not None:
            try:
                kb_path_list = json.loads(result["kb_status"])
                print(f"[数据解析] 解析现有知识库列表成功 - 列表长度：{len(kb_path_list)}")
            except json.JSONDecodeError:
                # 解析失败时重置为空列表，避免程序崩溃
                print(f"[数据解析] 失败 - 重置为空列表")
                kb_path_list = []
        else:
            print(f"[数据处理] 无现有知识库记录")
            kb_path_list = []
        
        # 4. 存在性检查：确认要删除的文件路径是否在用户的知识库列表中
        print(f"[存在性检查] 检查文件路径是否在列表中：{file_path}")
        # 兼容两种存储格式：旧格式（纯路径字符串列表）、新格式（字典列表，包含file_path字段）
        file_exists = False
        if isinstance(kb_path_list[0], dict) if kb_path_list else False:
            file_exists = any(item.get("file_path") == file_path for item in kb_path_list)
        else:
            file_exists = file_path in kb_path_list
        
        if not file_exists:
            print(f"[存在性检查] 失败 - 文件路径不在知识库列表中")
            raise HTTPException(status_code=404, detail="文件路径不存在于知识库列表中")
        print(f"[存在性检查] 通过")
        
        # 5. 本地文件删除：删除物理文件
        print(f"\n[文件删除] 开始删除本地文件：{file_path}")
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[文件删除] 成功 - 本地文件已删除")
        else:
            print(f"[文件删除] 跳过 - 本地文件不存在")
        
        # 6. 数据更新：从知识库列表中移除已删除的文件路径
        print(f"\n[数据更新] 从知识库列表移除文件路径")
        if isinstance(kb_path_list[0], dict) if kb_path_list else False:
            # 新格式：过滤掉匹配的字典项
            kb_path_list = [item for item in kb_path_list if item.get("file_path") != file_path]
        else:
            # 旧格式：直接移除路径字符串
            kb_path_list.remove(file_path)
        print(f"[数据更新] 移除完成 - 新列表长度：{len(kb_path_list)}")
        
        # 7. 数据库更新：将更新后的知识库列表写回数据库（存在则更新，不存在则插入）
        kb_status_json = json.dumps(kb_path_list, ensure_ascii=False)
        upsert_sql = """
            INSERT INTO user_personas (username, jabobo_id, kb_status) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE kb_status = VALUES(kb_status)
        """
        print(f"[数据库操作] 执行更新SQL：{upsert_sql} | 参数：({x_username}, {jabobo_id}, {kb_status_json[:100]}...)")
        cursor.execute(upsert_sql, (x_username, jabobo_id, kb_status_json))
        
        # 核心修复：提交事务
        db.connection.commit()
        print(f"[数据库操作] 事务提交成功")
        
        # 8. 向量文件处理：删除文件后检查知识库目录是否为空，更新向量文件
        # 构建知识库目录和向量文件目录路径
        target_dir = os.path.join(BASE_DATA_DIR, x_username, jabobo_id,"kb_files")
        pkl_target_dir = os.path.join(BASE_DATA_DIR, x_username, jabobo_id,"pkl_file")
        pkl_path = os.path.join(pkl_target_dir,"kb.pkl")

        # 核心逻辑：检查知识库目录是否有文件（极简版）
        # 生成器表达式遍历目录，判断是否存在文件；若目录不存在则视为无文件
        has_files = any(os.path.isfile(os.path.join(target_dir, f)) for f in os.listdir(target_dir)) if os.path.isdir(target_dir) else False

        if not has_files:
            # 知识库目录为空：清空向量文件目录下的所有文件
            if os.path.isdir(pkl_target_dir):
                [os.remove(os.path.join(pkl_target_dir, f)) for f in os.listdir(pkl_target_dir) if os.path.isfile(os.path.join(pkl_target_dir, f))]
        else:
            # 知识库目录有文件：重新生成向量文件
            generate_vector_from_txt_folder(target_dir, pkl_path)
                
        # 打印删除完成日志
        print(f"\n[删除完成] 成功 - 删除文件路径：{file_path} | 剩余记录数：{len(kb_path_list)} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"===== 删除请求处理完成 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # 返回删除成功结果
        return {
            "success": True,
            "deleted_path": file_path,
            "remaining_kb_paths": kb_path_list,
            "message": "知识库文件删除成功"
        }
    except HTTPException:
        # 捕获业务异常（如403/404），直接抛出不处理
        raise
    except Exception as e:
        print(f"\n[删除异常] 失败 - 异常信息：{str(e)} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if db_connected and db.connection:
            try:
                print(f"[数据库回滚] 开始回滚事务")
                db.connection.rollback()
                print(f"[数据库回滚] 回滚完成")
            except Exception as rollback_e:
                print(f"[数据库回滚] 失败 - 异常：{str(rollback_e)}")
        # 抛出500异常，告知前端删除失败
        raise HTTPException(status_code=500, detail=f"删除知识库文件失败：{str(e)}")
    finally:
        # 最终操作：无论成功/失败，都关闭数据库连接释放资源
        print(f"\n[资源释放] 关闭数据库连接 - 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if db_connected and db.connection:
            try:
                if hasattr(db, 'cursor') and db.cursor:
                    db.cursor.close()
                db.close()
            except Exception as close_e:
                print(f"[资源释放] 关闭连接失败：{str(close_e)}")
        print(f"[资源释放] 数据库连接已关闭\n")


def get_username_by_jabobo_id(jabobo_id: str):
    """根据设备ID查询对应的用户名，适配联合主键"""
    print(f"\n[用户查询] 开始通过设备ID查询用户名 - jabobo_id：{jabobo_id} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 先确保数据库连接
    if not db.connect():
        raise HTTPException(status_code=500, detail="数据库连接失败")
    
    # 获取有效游标
    cursor = get_valid_cursor()
    
    try:
        # 执行查询（核心：通过jabobo_id查username）
        query_sql = "SELECT username FROM user_personas WHERE jabobo_id = %s LIMIT 1"
        print(f"[用户查询] 执行SQL：{query_sql} | 参数：({jabobo_id})")
        cursor.execute(query_sql, (jabobo_id,))
        result = cursor.fetchone()
        
        # 校验查询结果
        if not result or not result.get("username"):
            print(f"[用户查询] 失败 - 未找到设备ID {jabobo_id} 对应的用户 | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            raise HTTPException(status_code=404, detail=f"未找到设备ID {jabobo_id} 对应的用户记录")
        
        username = result.get("username")
        print(f"[用户查询] 成功 - 设备ID {jabobo_id} 对应用户名：{username} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return username
    finally:
        # 关闭游标（不关闭连接，留给外层处理）
        if cursor:
            cursor.close()


# localhost/8007/api/user/generate-rag-prompt
@router.post("/user/generate-rag-prompt")
async def generate_rag_prompt(
    request: Request,
    jabobo_id: Optional[str] = Query(None, description="设备ID（捷宝宝ID）"),
    question: Optional[str] = Query(None, description="用户问题")
):
    """根据设备ID和用户问题，调用build_rag_prompt_from_vector_file生成RAG提示词（无需身份验证）"""
    print(f"\n===== 开始处理RAG提示词生成请求 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    # 如果 query 未提供，则尝试从 POST JSON 体中读取（兼容客户端使用 body 发送的情况）
    if not jabobo_id or not question:
        try:
            body = await request.json()
            if isinstance(body, dict):
                jabobo_id = jabobo_id or body.get("jabobo_id")
                question = question or body.get("question")
        except Exception:
            pass

    if not jabobo_id or not question:
        raise HTTPException(status_code=422, detail="Missing jabobo_id or question")

    print(f"[请求信息] 设备ID：{jabobo_id} | 用户问题：{question[:50]}...")
    
    db_connected = False
    try:
        # 1. 确保数据库连接
        db_connected = db.connect()
        if not db_connected:
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 2. 根据设备ID查询对应的用户名（捕获用户不存在异常并自定义提示）
        try:
            username = get_username_by_jabobo_id(jabobo_id)
        except HTTPException as e:
            if e.status_code == 404:
                print(f"[用户查询] 失败 - 设备ID {jabobo_id} 对应的用户不存在")
                raise HTTPException(status_code=404, detail="用户不存在")
            raise  # 其他HTTP异常正常抛出
        
        # 3. 构建向量文件路径（使用查询到的真实用户名）
        pkl_target_dir = os.path.join(BASE_DATA_DIR, username, jabobo_id,"pkl_file")
        pkl_path = os.path.join(pkl_target_dir,"kb.pkl")
        print(f"\n[路径构建] 向量文件路径：{pkl_path}")
        
        # 4. 检查向量文件是否存在（自定义提示语：未构建知识库）
        if not os.path.exists(pkl_path):
            print(f"[文件检查] 失败 - 向量文件不存在：{pkl_path}")
            raise HTTPException(status_code=404, detail="未构建知识库")
        print(f"[文件检查] 通过 - 向量文件存在")
        
        # 5. 调用函数生成RAG提示词
        print(f"\n[提示词生成] 开始调用build_rag_prompt_from_vector_file")
        rag_prompt = build_rag_prompt_from_vector_file(question, pkl_path)  # 适配函数参数
        print(f"[提示词生成] 成功 - 生成的提示词长度：{len(rag_prompt)} 字符")
        
        print(f"\n[生成完成] 成功 - 设备ID：{jabobo_id} | 用户名：{username} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"===== RAG提示词生成请求处理完成 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # 返回生成结果
        return {
            "success": True,
            "jabobo_id": jabobo_id,
            "username": username,
            "question": question,
            "rag_prompt": rag_prompt,
            "message": "RAG提示词生成成功"
        }
    
    except HTTPException:
        # 捕获业务异常（如404用户不存在/未构建知识库）直接抛出
        raise
    except Exception as e:
        # 捕获系统异常，打印日志并返回500
        print(f"\n[生成异常] 失败 - 异常信息：{str(e)} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        raise HTTPException(status_code=500, detail=f"生成RAG提示词失败：{str(e)}")
    finally:
        # 释放数据库连接（查询用户名时占用的连接）
        print(f"\n[资源释放] 关闭数据库连接 - 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if db_connected and db.connection:
            try:
                if hasattr(db, 'cursor') and db.cursor:
                    db.cursor.close()
                db.close()
                print(f"[资源释放] 数据库连接已关闭\n")
            except Exception as close_e:
                print(f"[资源释放] 关闭连接失败：{str(close_e)}\n")