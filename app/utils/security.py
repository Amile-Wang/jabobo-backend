import bcrypt

def get_password_hash(password: str) -> str:
    # 将字符串转为字节流
    pwd_bytes = password.encode('utf-8')
    # 生成盐值并加密
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    # 返回字符串格式存入数据库
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        # 将输入和数据库的哈希都转回字节流进行比对
        return bcrypt.checkpw(
            plain_password.encode('utf-8'), 
            hashed_password.encode('utf-8')
        )
    except Exception as e:
        print(f"❌ 校验异常: {e}")
        return False