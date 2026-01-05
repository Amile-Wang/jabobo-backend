from fastapi import APIRouter, Form, File, UploadFile, Header, HTTPException, Query
from app.database import db
import json
import os
import shutil
from typing import List, Optional
from datetime import datetime  # 处理时间戳

# 全局Router（仅定义一次）
router = APIRouter()

# --- 新增：游标修复辅助函数 ---
def get_valid_cursor():
    """确保游标可用，若已关闭则重新创建"""
    print(f"\n[数据库游标检查] 开始检查游标状态 - 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    # 1. 确保数据库连接已建立
    if not db.connect():
        print("[数据库游标检查] 数据库连接失败！")
        raise HTTPException(status_code=500, detail="数据库连接失败")
    print("[数据库游标检查] 数据库连接已建立")
    
    # 2. 检查游标是否关闭，若关闭则重新创建
    cursor_closed = hasattr(db.cursor, 'closed') and db.cursor.closed
    print(f"[数据库游标检查] 游标当前状态：{'已关闭' if cursor_closed else '正常'}")
    if cursor_closed:
        # 重新创建DictCursor
        db.cursor = db.connection.cursor(db.connection.cursor.DictCursor)
        print("[数据库游标检查] 已重新创建游标")
    
    print(f"[数据库游标检查] 游标检查完成 - 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return db.cursor

# --- 辅助函数：统一身份验证（保留，供查询/删除接口使用）---
def verify_user(x_username, authorization):
    print(f"\n[身份验证] 开始验证用户 - 用户名：{x_username} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    # 修复：先获取有效游标
    cursor = get_valid_cursor()
    
    # 执行查询
    print(f"[身份验证] 执行SQL：SELECT session_token FROM user_login WHERE username = '{x_username}'")
    cursor.execute("SELECT session_token FROM user_login WHERE username = %s", (x_username,))
    user = cursor.fetchone()
    print(f"[身份验证] 查询结果：{user}")
    
    # 验证逻辑
    if not user:
        print(f"[身份验证] 失败 - 用户 {x_username} 不存在 | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        raise HTTPException(status_code=401, detail="身份验证失败")
    if user.get('session_token') != authorization:
        print(f"[身份验证] 失败 - Token不匹配 | 数据库Token：{user.get('session_token')[:10]}... | 请求Token：{authorization[:10]}...")
        raise HTTPException(status_code=401, detail="身份验证失败")
    
    print(f"[身份验证] 成功 - 用户名：{x_username} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return user

def get_username_by_jabobo_id(jabobo_id: str):
    """根据设备ID查询对应的用户名，适配联合主键"""
    print(f"\n[用户查询] 开始通过设备ID查询用户名 - jabobo_id：{jabobo_id} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 获取有效游标
    cursor = get_valid_cursor()
    
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

# 配置常量 - 音频文件相关
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}  # 常见音频格式
MAX_FILE_SIZE = 100 * 1024 * 1024  # 增大到100MB（音频文件通常更大）
BASE_DATA_DIR = "./audio_data"  # 音频专用存储目录

# --- 上传音频接口（修改：先查用户再写入）---
@router.post("/user/upload-audio")
async def upload_audio_file(
    jabobo_id: str = Form(...),  # 仅保留设备ID作为标识
    file: UploadFile = File(...),
    audio_content: Optional[str] = Form(None),  # 新增音频文本内容字段
):
    print(f"\n===== 开始处理音频文件上传请求 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[请求信息] 设备ID：{jabobo_id} | 音频文件名：{file.filename}")
    if audio_content:
        print(f"[请求信息] 音频文本内容：{audio_content[:50]}..." if len(audio_content) > 50 else f"[请求信息] 音频文本内容：{audio_content}")
    
    # 第一步：通过设备ID查询对应的用户名（核心修改）
    username = get_username_by_jabobo_id(jabobo_id)
    
    # 1. 校验音频文件后缀
    print(f"\n[文件校验] 开始校验音频文件后缀 - 文件名：{file.filename}")
    file_ext = os.path.splitext(file.filename)[1].lower()
    print(f"[文件校验] 音频文件后缀：{file_ext} | 允许的后缀：{ALLOWED_EXTENSIONS}")
    if file_ext not in ALLOWED_EXTENSIONS:
        print(f"[文件校验] 失败 - 不支持的音频格式：{file_ext}")
        raise HTTPException(status_code=400, detail="仅支持 MP3、WAV、OGG、FLAC、M4A 音频格式")
    print(f"[文件校验] 音频后缀校验通过")

    # 2. 校验音频文件大小
    print(f"\n[文件校验] 开始校验音频文件大小 - 文件名：{file.filename}")
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)  # 重置文件指针
    file_size_mb = round(file_size / 1024 / 1024, 2)
    print(f"[文件校验] 音频文件大小：{file_size} 字节 ({file_size_mb} MB) | 最大允许：{MAX_FILE_SIZE / 1024 / 1024} MB")
    if file_size > MAX_FILE_SIZE:
        print(f"[文件校验] 失败 - 音频文件大小超过限制")
        raise HTTPException(status_code=400, detail="音频文件大小超过 100MB 限制")
    print(f"[文件校验] 大小校验通过")

    # 3. 创建音频文件存储目录（仅基于设备ID，移除用户名层级）
    print(f"\n[目录创建] 开始创建音频存储目录")
    target_dir = os.path.join(BASE_DATA_DIR, jabobo_id,"audio_files")  # 仅保留设备ID目录
    print(f"[目录创建] 音频目标目录：{target_dir}")
    os.makedirs(target_dir, exist_ok=True)
    print(f"[目录创建] 音频目录创建完成（已存在则跳过）")
    
    # 4. 构建音频文件路径
    file_path = os.path.join(target_dir, file.filename)
    file_path = os.path.abspath(file_path)
    print(f"\n[文件存储] 音频目标文件路径：{file_path}")
    
    try:
        # 保存音频文件到本地
        print(f"[文件存储] 开始写入音频文件 - 文件名：{file.filename} | 路径：{file_path}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print(f"[文件存储] 音频文件写入完成 - 实际文件大小：{os.path.getsize(file_path)} 字节")
        
        # 5. 数据库操作（存储音频文件信息，关联用户名+设备ID）
        print(f"\n[数据库操作] 开始处理音频文件数据库逻辑")
        if not db.connect():
            print(f"[数据库操作] 失败 - 数据库连接失败")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 获取有效游标
        cursor = get_valid_cursor()
        
        # 查询现有音频记录（按 用户名+设备ID 查询，适配联合主键）
        query_sql = "SELECT audio_status FROM user_personas WHERE username = %s AND jabobo_id = %s"
        print(f"[数据库操作] 执行查询SQL：{query_sql} | 参数：({username}, {jabobo_id})")
        cursor.execute(query_sql, (username, jabobo_id))
        result = cursor.fetchone()
        print(f"[数据库操作] 查询结果：{result}")
        
        # 解析现有音频路径列表
        if result and result.get("audio_status") is not None:
            try:
                audio_path_list = json.loads(result["audio_status"])
                print(f"[数据库操作] 解析现有音频列表成功 - 列表长度：{len(audio_path_list)}")
            except json.JSONDecodeError:
                print(f"[数据库操作] 解析现有音频列表失败 - 重置为空列表")
                audio_path_list = []
        else:
            print(f"[数据库操作] 无现有音频记录 - 初始化空列表")
            audio_path_list = []
        
        # 构建音频文件信息（新增 audio_content 字段）
        audio_info = {
            "file_path": file_path,
            "file_name": file.filename,
            "file_size_bytes": file_size,
            "file_size_mb": file_size_mb,
            "audio_format": file_ext[1:],  # 音频格式
            "audio_content": audio_content or "",  # 音频文本内容，为空则存空字符串
            "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "upload_timestamp": datetime.now().timestamp()
        }
        print(f"[数据库操作] 构建音频文件信息：{audio_info}")
        
        # 去重检查
        duplicate = any(item.get("file_path") == file_path for item in audio_path_list)
        if duplicate:
            print(f"[数据库操作] 音频文件已存在，跳过追加 - 路径：{file_path}")
        else:
            audio_path_list.append(audio_info)
            print(f"[数据库操作] 音频文件信息追加完成 - 新列表长度：{len(audio_path_list)}")
        
        # 插入/更新数据库（核心修改：补充username字段，适配联合主键）
        audio_status_json = json.dumps(audio_path_list, ensure_ascii=False)
        upsert_sql = """
            INSERT INTO user_personas (username, jabobo_id, audio_status)  -- 新增username字段
            VALUES (%s, %s, %s)  -- 三个参数：用户名、设备ID、音频信息
            ON DUPLICATE KEY UPDATE audio_status = VALUES(audio_status)
        """
        print(f"[数据库操作] 执行更新SQL：{upsert_sql} | 参数：({username}, {jabobo_id}, {audio_status_json[:100]}...)")
        cursor.execute(upsert_sql, (username, jabobo_id, audio_status_json))
        
        print(f"\n[上传完成] 成功 - 音频文件路径：{file_path} | 用户名：{username} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"===== 音频上传请求处理完成 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        return {
            "success": True,
            "current_audio_info": audio_info,
            "all_audio_paths": audio_path_list,
            "message": "音频文件上传成功"
        }
    
    except HTTPException:
        # 重新抛出已定义的HTTP异常（如用户未找到、文件格式错误等）
        raise
    except Exception as e:
        print(f"\n[上传异常] 失败 - 异常信息：{str(e)} | 堆栈：{e.__traceback__} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if db.connection:
            try:
                print(f"[数据库回滚] 开始回滚事务")
                db.connection.rollback()
                print(f"[数据库回滚] 回滚完成")
            except Exception as rollback_e:
                print(f"[数据库回滚] 失败 - 异常：{str(rollback_e)}")
        raise HTTPException(status_code=500, detail=f"音频文件保存异常: {str(e)}")
    finally:
        print(f"\n[资源释放] 关闭数据库连接 - 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        db.close()
        print(f"[资源释放] 数据库连接已关闭\n")

# --- 查询音频列表接口（仍保留用户验证，若需调整可说明）---
@router.get("/user/list-audio")
async def list_audio_files(
    jabobo_id: str = Query(..., description="设备ID"),
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    print(f"\n===== 开始处理音频文件查询请求 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[请求信息] 用户名：{x_username} | 设备ID：{jabobo_id}")
    
    # 身份验证
    verify_user(x_username, authorization)
    
    try:
        print(f"\n[数据库操作] 开始查询音频文件列表")
        if not db.connect():
            print(f"[数据库操作] 失败 - 数据库连接失败")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 获取有效游标
        cursor = get_valid_cursor()
        
        # 执行查询（仅按设备ID查询）
        query_sql = "SELECT audio_status FROM user_personas WHERE jabobo_id = %s"
        print(f"[数据库操作] 执行查询SQL：{query_sql} | 参数：({jabobo_id})")
        cursor.execute(query_sql, (jabobo_id,))
        result = cursor.fetchone()
        print(f"[数据库操作] 查询结果：{result}")
        
        # 处理查询结果
        audio_detail_list = []
        if result and result.get("audio_status") is not None:
            try:
                audio_path_list = json.loads(result["audio_status"])
                print(f"[数据解析] 解析音频JSON成功 - 列表长度：{len(audio_path_list)}")
                
                for idx, item in enumerate(audio_path_list):
                    print(f"[数据处理] 处理第 {idx+1} 条音频记录：{item}")
                    if isinstance(item, dict):
                        file_path = item.get("file_path")
                        print(f"[文件检查] 检查音频文件是否存在：{file_path}")
                        if os.path.exists(file_path):
                            file_stat = os.stat(file_path)
                            item.update({
                                "current_modify_time": datetime.fromtimestamp(file_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                                "status": "valid"
                            })
                            print(f"[文件检查] 存在 - 音频文件大小：{os.path.getsize(file_path)} 字节")
                        else:
                            item["status"] = "invalid (file not exists)"
                            print(f"[文件检查] 不存在")
                        audio_detail_list.append(item)
                    else:
                        # 兼容旧格式
                        file_path = item
                        print(f"[数据兼容] 旧格式音频路径：{file_path}")
                        if os.path.exists(file_path):
                            file_stat = os.stat(file_path)
                            audio_detail_list.append({
                                "file_path": file_path,
                                "file_name": os.path.basename(file_path),
                                "file_size_mb": round(file_stat.st_size / 1024 / 1024, 2),
                                "modify_time": f"{file_stat.st_mtime}",
                                "audio_format": os.path.splitext(file_path)[1][1:],
                                "audio_content": "",  # 旧格式无文本内容，置空
                                "status": "valid (old format)"
                            })
                        else:
                            audio_detail_list.append({
                                "file_path": file_path,
                                "file_name": os.path.basename(file_path),
                                "audio_format": os.path.splitext(file_path)[1][1:],
                                "audio_content": "",  # 旧格式无文本内容，置空
                                "status": "invalid (file not exists, old format)"
                            })
            except json.JSONDecodeError as e:
                print(f"[数据解析] 失败 - JSON解析异常：{str(e)}")
                audio_detail_list = []
        else:
            print(f"[数据处理] 无音频文件记录")
            audio_detail_list = []
        
        print(f"\n[查询完成] 成功 - 共查询到 {len(audio_detail_list)} 条音频记录 | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"===== 音频查询请求处理完成 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        return {
            "success": True,
            "total_count": len(audio_detail_list),
            "audio_list": audio_detail_list,
            "message": "音频文件列表查询成功"
        }
    except Exception as e:
        print(f"\n[查询异常] 失败 - 异常信息：{str(e)} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if db.connection:
            try:
                db.connection.rollback()
            except:
                pass
        raise HTTPException(status_code=500, detail=f"查询音频文件列表失败：{str(e)}")
    finally:
        print(f"\n[资源释放] 关闭数据库连接 - 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        db.close()
        print(f"[资源释放] 数据库连接已关闭\n")

# --- 删除音频接口（仍保留用户验证，若需调整可说明）---
@router.delete("/user/delete-audio")
async def delete_audio_file(
    jabobo_id: str = Query(..., description="设备ID"),
    file_path: str = Query(..., description="要删除的音频文件绝对路径"),
    x_username: str = Header(...), 
    authorization: str = Header(...)
):
    print(f"\n===== 开始处理音频文件删除请求 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[请求信息] 用户名：{x_username} | 设备ID：{jabobo_id} | 要删除的音频文件路径：{file_path}")
    
    # 身份验证
    verify_user(x_username, authorization)
    
    # 安全校验（调整为检查设备ID是否在路径中）
    print(f"\n[权限校验] 检查音频文件是否属于当前设备ID")
    if jabobo_id not in file_path:
        print(f"[权限校验] 失败 - 音频文件路径不含设备ID {jabobo_id}")
        raise HTTPException(status_code=403, detail="无权删除该音频文件（路径不属于当前设备）")
    print(f"[权限校验] 通过")
    
    try:
        print(f"\n[数据库操作] 开始查询音频文件记录")
        if not db.connect():
            print(f"[数据库操作] 失败 - 数据库连接失败")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 获取有效游标
        cursor = get_valid_cursor()
        
        # 执行查询（仅按设备ID查询）
        query_sql = "SELECT audio_status FROM user_personas WHERE jabobo_id = %s"
        print(f"[数据库操作] 执行查询SQL：{query_sql} | 参数：({jabobo_id})")
        cursor.execute(query_sql, (jabobo_id,))
        result = cursor.fetchone()
        print(f"[数据库操作] 查询结果：{result}")
        
        # 解析音频路径列表
        if result and result.get("audio_status") is not None:
            try:
                audio_path_list = json.loads(result["audio_status"])
                print(f"[数据解析] 解析现有音频列表成功 - 列表长度：{len(audio_path_list)}")
            except json.JSONDecodeError:
                print(f"[数据解析] 失败 - 重置为空列表")
                audio_path_list = []
        else:
            print(f"[数据处理] 无现有音频记录")
            audio_path_list = []
        
        # 检查音频文件是否存在于列表
        print(f"[存在性检查] 检查音频文件路径是否在列表中：{file_path}")
        # 兼容新/旧格式
        file_exists = False
        if isinstance(audio_path_list[0], dict) if audio_path_list else False:
            file_exists = any(item.get("file_path") == file_path for item in audio_path_list)
        else:
            file_exists = file_path in audio_path_list
        
        if not file_exists:
            print(f"[存在性检查] 失败 - 音频文件路径不在音频列表中")
            raise HTTPException(status_code=404, detail="音频文件路径不存在于音频列表中")
        print(f"[存在性检查] 通过")
        
        # 1. 删除本地音频文件
        print(f"\n[文件删除] 开始删除本地音频文件：{file_path}")
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[文件删除] 成功 - 本地音频文件已删除")
        else:
            print(f"[文件删除] 跳过 - 本地音频文件不存在")
        
        # 2. 从列表移除音频路径
        print(f"\n[数据更新] 从音频列表移除文件路径")
        if isinstance(audio_path_list[0], dict) if audio_path_list else False:
            audio_path_list = [item for item in audio_path_list if item.get("file_path") != file_path]
        else:
            audio_path_list.remove(file_path)
        print(f"[数据更新] 移除完成 - 新音频列表长度：{len(audio_path_list)}")
        
        # 3. 更新数据库（仅关联设备ID）
        audio_status_json = json.dumps(audio_path_list, ensure_ascii=False)
        upsert_sql = """
            INSERT INTO user_personas (jabobo_id, audio_status)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE audio_status = VALUES(audio_status)
        """
        print(f"[数据库操作] 执行更新SQL：{upsert_sql} | 参数：({jabobo_id}, {audio_status_json[:100]}...)")
        cursor.execute(upsert_sql, (jabobo_id, audio_status_json))
        
        print(f"\n[删除完成] 成功 - 删除音频文件路径：{file_path} | 剩余音频记录数：{len(audio_path_list)} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"===== 音频删除请求处理完成 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        return {
            "success": True,
            "deleted_path": file_path,
            "remaining_audio_paths": audio_path_list,
            "message": "音频文件删除成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"\n[删除异常] 失败 - 异常信息：{str(e)} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        cursor.execute(query_sql, (jabobo_id,))
        result = cursor.fetchone()
        print(f"[数据库操作] 查询结果：{result}")
        
        # 解析音频路径列表
        if result and result.get("audio_status") is not None:
            try:
                audio_path_list = json.loads(result["audio_status"])
                print(f"[数据解析] 解析现有音频列表成功 - 列表长度：{len(audio_path_list)}")
            except json.JSONDecodeError:
                print(f"[数据解析] 失败 - 重置为空列表")
                audio_path_list = []
        else:
            print(f"[数据处理] 无现有音频记录")
            audio_path_list = []
        
        # 检查音频文件是否存在于列表
        print(f"[存在性检查] 检查音频文件路径是否在列表中：{file_path}")
        # 兼容新/旧格式
        file_exists = False
        if isinstance(audio_path_list[0], dict) if audio_path_list else False:
            file_exists = any(item.get("file_path") == file_path for item in audio_path_list)
        else:
            file_exists = file_path in audio_path_list
        
        if not file_exists:
            print(f"[存在性检查] 失败 - 音频文件路径不在音频列表中")
            raise HTTPException(status_code=404, detail="音频文件路径不存在于音频列表中")
        print(f"[存在性检查] 通过")
        
        # 1. 删除本地音频文件
        print(f"\n[文件删除] 开始删除本地音频文件：{file_path}")
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[文件删除] 成功 - 本地音频文件已删除")
        else:
            print(f"[文件删除] 跳过 - 本地音频文件不存在")
        
        # 2. 从列表移除音频路径
        print(f"\n[数据更新] 从音频列表移除文件路径")
        if isinstance(audio_path_list[0], dict) if audio_path_list else False:
            audio_path_list = [item for item in audio_path_list if item.get("file_path") != file_path]
        else:
            audio_path_list.remove(file_path)
        print(f"[数据更新] 移除完成 - 新音频列表长度：{len(audio_path_list)}")
        
        # 3. 更新数据库（仅关联设备ID）
        audio_status_json = json.dumps(audio_path_list, ensure_ascii=False)
        upsert_sql = """
            INSERT INTO user_personas (jabobo_id, audio_status)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE audio_status = VALUES(audio_status)
        """
        print(f"[数据库操作] 执行更新SQL：{upsert_sql} | 参数：({jabobo_id}, {audio_status_json[:100]}...)")
        cursor.execute(upsert_sql, (jabobo_id, audio_status_json))
        
        print(f"\n[删除完成] 成功 - 删除音频文件路径：{file_path} | 剩余音频记录数：{len(audio_path_list)} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"===== 音频删除请求处理完成 ===== | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        return {
            "success": True,
            "deleted_path": file_path,
            "remaining_audio_paths": audio_path_list,
            "message": "音频文件删除成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"\n[删除异常] 失败 - 异常信息：{str(e)} | 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if db.connection:
            try:
                print(f"[数据库回滚] 开始回滚事务")
                db.connection.rollback()
                print(f"[数据库回滚] 回滚完成")
            except Exception as rollback_e:
                print(f"[数据库回滚] 失败 - 异常：{str(rollback_e)}")
        raise HTTPException(status_code=500, detail=f"删除音频文件失败：{str(e)}")
    finally:
        print(f"\n[资源释放] 关闭数据库连接 - 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        db.close()
        print(f"[资源释放] 数据库连接已关闭\n")