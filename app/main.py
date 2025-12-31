from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, users, jabobo_config,jabobo_manager,device_data_api,chat_config

app = FastAPI(title="Jobobo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册所有模块路由
app.include_router(auth.router, prefix="/api", tags=["认证"])
app.include_router(users.router, prefix="/api", tags=["用户管理"])
app.include_router(jabobo_config.router, prefix="/api", tags=["配置管理"]) 
app.include_router(jabobo_manager.router, prefix="/api", tags=["捷宝宝管理"]) 
app.include_router(device_data_api.router, prefix="/api", tags=["设备端请求管理"]) 
app.include_router(chat_config.router, prefix="/api", tags=["聊天差异化配置"]) 

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
