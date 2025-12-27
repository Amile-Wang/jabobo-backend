from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, users, personas

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
app.include_router(personas.router, prefix="/api", tags=["业务配置"]) 

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
