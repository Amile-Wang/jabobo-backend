from pydantic import BaseModel, Field
from enum import Enum

# 新增：定义客户端类型枚举，限定只能传 web/android/ios
class ClientType(str, Enum):
    WEB = "web"
    ANDROID = "android"
    IOS = "ios"

class LoginRequest(BaseModel):
    username: str
    password: str
    # 新增：客户端类型字段，默认值为 web，不传入时自动使用默认值
    client_type: ClientType = Field(default=ClientType.WEB)

class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "User"

class PasswordUpdateRequest(BaseModel):
    username: str
    new_password: str