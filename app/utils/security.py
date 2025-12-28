import bcrypt

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