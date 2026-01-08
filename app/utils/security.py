import datetime
import bcrypt
from app.database import db 
from fastapi import HTTPException


# 核心映射：客户端类型 → 对应token字段（默认取web）
CLIENT_TOKEN_MAP = {
    "web": "web_token",
    "android": "android_token",
    "ios": "ios_token"
}

def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        # 添加详细打印
        print(f"🔍 正在校验密码...")
        print(f"   - 输入的明文: {plain_password}")
        print(f"   - 数据库中的值: {hashed_password}")
        
        # 将输入和数据库的哈希都转回字节流进行比对
        result = bcrypt.checkpw(
            plain_password.encode('utf-8'), 
            hashed_password.encode('utf-8')
        )
        
        if result:
            print("✅ 密码校验通过！")
        else:
            print("❌ 密码不匹配（哈希值不符合）")
        return result
        
    except Exception as e:
        # 如果数据库存的是明文，这里会报 "Invalid salt" 之类的错误
        print(f"⚠️ 校验过程触发异常: {e}")
        print("💡 提示：请检查数据库里存的是否为 bcrypt 哈希值而非明文。")
        return False


# --- 重构verify_user：自带游标校验，避免Cursor closed ---
def verify_user(x_username, authorization):
    # 前置：确保数据库连接和游标可用（核心修复）
    try:
        # 1. 强制重建数据库连接（避免连接断开）
        if not db.connect():
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 2. 检查游标是否关闭，若关闭则重新创建
        if hasattr(db.cursor, 'closed') and db.cursor.closed:
            db.cursor = db.connection.cursor(db.connection.cursor.DictCursor)
            print(f"⚠️ [verify_user] 游标已关闭，已重新创建")
    except Exception as e:
        print(f"❌ [verify_user] 游标初始化失败：{str(e)}")
        raise HTTPException(status_code=500, detail="身份验证初始化失败")

    # 1. 打印调试日志
    print(f"\n===== [身份验证日志] =====")
    print(f"接收的x-username: {x_username}")
    print(f"接收的Authorization原始值: {authorization}")
    
    # 2. 清洗token（兼容Bearer前缀）
    token = authorization.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    print(f"清洗后的token: {token}")
    
    try:
        # 3. 查询用户的所有端token（此时游标已确保可用）
        db.cursor.execute("""
            SELECT username, web_token, android_token, ios_token 
            FROM user_login 
            WHERE username = %s
        """, (x_username,))
        user = db.cursor.fetchone()
        print(f"数据库查询结果: {user}")
        
        # 4. 校验用户是否存在
        if not user:
            print(f"❌ 401原因：用户{x_username}不存在")
            raise HTTPException(status_code=401, detail="身份验证失败：用户不存在")
        
        # 5. 校验多端token
        token_is_valid = False
        # 遍历所有端的token字段匹配
        for token_field in CLIENT_TOKEN_MAP.values():
            db_token = user.get(token_field)
            print(f"比对{token_field}: 数据库值={db_token} | 请求值={token}")
            if db_token == token:
                token_is_valid = True
                break
        # 兜底校验web_token
        if not token_is_valid:
            db_web_token = user.get("web_token")
            print(f"兜底校验web_token: 数据库值={db_web_token} | 请求值={token}")
            token_is_valid = (db_web_token == token)
        
        # 6. token无效则返回401
        if not token_is_valid:
            print(f"❌ 401原因：token不匹配")
            raise HTTPException(status_code=401, detail="身份验证失败：登录已过期或token无效")
        
        print(f"✅ 身份验证通过")
        return user
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [verify_user] SQL执行失败：{str(e)}")
        raise HTTPException(status_code=500, detail="身份验证执行失败")

# --- 修复get_valid_cursor：和verify_user逻辑对齐 ---
def get_valid_cursor():
    """确保游标可用，若已关闭则重新创建"""
    try:
        print(f"\n[数据库游标检查] 开始检查游标状态 - 时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        # 1. 确保数据库连接已建立
        if not db.connect():
            print("[数据库游标检查] 数据库连接失败！")
            raise HTTPException(status_code=500, detail="数据库连接失败")
        
        # 2. 检查游标是否关闭，若关闭则重新创建
        cursor_closed = hasattr(db.cursor, 'closed') and db.cursor.closed
        print(f"[数据库游标检查] 游标当前状态：{'已关闭' if cursor_closed else '正常'}")
        if cursor_closed:
            # 重新创建DictCursor
            db.cursor = db.connection.cursor(db.connection.cursor.DictCursor)
            print("[数据库游标检查] 已重新创建游标")
        
        print(f"[数据库游标检查] 游标检查完成 - 时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return db.cursor
    except Exception as e:
        print(f"[数据库游标检查] 异常：{str(e)}")
        raise HTTPException(status_code=500, detail=f"游标初始化失败：{str(e)}")