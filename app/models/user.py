from pydantic import BaseModel

class LoginRequest(BaseModel)
    username str
    password str

class UserCreateRequest(BaseModel)
    username str
    password str
    role str = User

class PasswordUpdateRequest(BaseModel)
    username str
    new_password str
