import bcrypt

# 数据库中的加密密码（复制日志里的完整串）
hashed_pwd = b"$2b$12$6Nl89pXYv5I1rN56/k5VhuO.h9U6lVl5vY09oO.59F59F59F59F5"
# 明文密码
plain_pwd = "123456"

# 核心验证逻辑（bcrypt必须用bytes类型）
is_match = bcrypt.checkpw(plain_pwd.encode("utf-8"), hashed_pwd)
print(f"明文密码: {plain_pwd}")
print(f"加密串是否匹配: {is_match}")

# 额外测试：用123456生成加密串，对比数据库中的值
new_hashed = bcrypt.hashpw(plain_pwd.encode("utf-8"), bcrypt.gensalt(12))
print(f"123456的新加密串: {new_hashed.decode('utf-8')}")
print(f"数据库中的加密串: {hashed_pwd.decode('utf-8')}")