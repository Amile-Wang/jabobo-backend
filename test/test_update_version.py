import requests
import json

# 配置接口基础信息（根据你的实际部署地址修改）
BASE_URL = "http://47.99.34.84:8007"  # 你的FastAPI服务地址
UPDATE_VERSION_API = f"{BASE_URL}/api/user/device/update_version"

def test_update_version(jabobo_id: str, current_version: str = None, expected_version: str = None):
    """
    测试更新版本号接口
    :param jabobo_id: 设备ID（必传）
    :param current_version: 当前版本号（可选）
    :param expected_version: 预期版本号（可选）
    """
    # 构造请求参数
    params = {"jabobo_id": jabobo_id}
    if current_version:
        params["current_version"] = current_version
    if expected_version:
        params["expected_version"] = expected_version

    try:
        # 发送PUT请求（接口定义为PUT方法）
        response = requests.put(UPDATE_VERSION_API, params=params)
        # 打印请求信息
        print(f"\n=== 测试用例：设备ID={jabobo_id} | 当前版本={current_version or '未传'} | 预期版本={expected_version or '未传'} ===")
        print(f"请求URL: {response.url}")
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ 请求失败：{str(e)}")
        return None

if __name__ == "__main__":
    # ========== 测试用例 ==========
    # 测试用例1：更新单个版本号（仅当前版本）
    # test_update_version(jabobo_id="test_device_001", current_version="1.0.0")

    # # 测试用例2：更新单个版本号（仅预期版本）
    # test_update_version(jabobo_id="test_device_001", expected_version="1.1.0")

    # 测试用例3：同时更新两个版本号
    test_update_version(jabobo_id="80:b5:4e:e0:98:cc", current_version="1.2.0", expected_version="1.3.0")

    # # 测试用例4：设备ID不存在（预期返回更新失败）
    # test_update_version(jabobo_id="non_exist_device_999", current_version="1.0.0")

    # # 测试用例5：参数缺失（未传任何版本号，预期返回400错误）
    # test_update_version(jabobo_id="test_device_001")

    # # 测试用例6：设备ID为空（预期返回400错误）
    # test_update_version(jabobo_id="", current_version="1.0.0")