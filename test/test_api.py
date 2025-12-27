import requests
import json

BASE_URL = "http://127.0.0.1:5000/api"
ADMIN_USER = "admin"
ADMIN_PASS = "123456"  # 请确保这与你数据库中的密码一致
NEW_USER = "tester_001"
NEW_PASS = "pass123"

def print_res(msg, response):
    status = "✅" if response.status_code == 200 else "❌"
    print(f"{status} {msg} | Status: {response.status_code}")
    if response.status_code != 200:
        print(f"   反馈详情: {response.text}")

def run_suite():
    print("=== 开始后端模块化接口全流程测试 ===\n")

    # 1. 登录测试
    print("[1] 测试管理员登录...")
    login_res = requests.post(f"{BASE_URL}/login", json={
        "username": ADMIN_USER,
        "password": ADMIN_PASS
    })
    print_res("管理员登录", login_res)
    if login_res.status_code != 200: return

    # 准备后续请求需要的 Header
    headers = {"x-username": ADMIN_USER, "Content-Type": "application/json"}

    # 2. 获取用户列表
    print("\n[2] 测试获取用户列表...")
    list_res = requests.get(f"{BASE_URL}/users", headers=headers)
    print_res("获取用户列表", list_res)

    # 3. 创建新用户
    print(f"\n[3] 测试创建新用户: {NEW_USER}...")
    create_res = requests.post(f"{BASE_URL}/users", headers=headers, json={
        "username": NEW_USER,
        "password": NEW_PASS,
        "role": "User"
    })
    print_res("创建用户", create_res)

    # 4. 验证新用户登录
    print(f"\n[4] 验证新用户 {NEW_USER} 登录权限...")
    new_login_res = requests.post(f"{BASE_URL}/login", json={
        "username": NEW_USER,
        "password": NEW_PASS
    })
    print_res("新用户登录", new_login_res)

    # 5. 修改密码测试 (由管理员操作)
    print(f"\n[5] 测试管理员修改 {NEW_USER} 的密码...")
    update_res = requests.put(f"{BASE_URL}/users/password", headers=headers, json={
        "username": NEW_USER,
        "new_password": "new_password_456"
    })
    print_res("修改密码", update_res)

    # 6. 删除测试用户
    print(f"\n[6] 清理数据：删除测试用户 {NEW_USER}...")
    del_res = requests.delete(f"{BASE_URL}/users/{NEW_USER}", headers=headers)
    print_res("删除用户", del_res)

    print("\n=== 所有测试项执行完毕 ===")

if __name__ == "__main__":
    run_suite()
