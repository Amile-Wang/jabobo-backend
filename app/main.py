from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.routes import auth, users, jabobo_config, jabobo_manager, device_data_api, jabobo_knowlege, chat_config, jabobo_voice

# --- 1. 定义禁用缓存中间件 ---
class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # 针对所有 /api 开头的请求禁用缓存
        if request.url.path.startswith("/api"):
            # no-store: 强制不存储（CDN/浏览器都不准存副本）
            # no-cache: 使用缓存前必须先去后端验证（配合 max-age=0）
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            
            # Vary: 非常重要！告诉 CDN 缓存键必须包含 Token 和用户名
            # 这样用户 A 的请求结果绝对不会给用户 B
            response.headers["Vary"] = "Authorization, x-username"
            
        return response

app = FastAPI(title="Jobobo API")

# --- 2. 挂载中间件 ---
# 注意：中间件的执行顺序是从下往上的，所以我们先加缓存控制，再加 CORS
app.add_middleware(NoCacheMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. 注册所有模块路由 ---
# 你的前缀是 /api，中间件会匹配这个前缀
app.include_router(auth.router, prefix="/api", tags=["认证"])
app.include_router(users.router, prefix="/api", tags=["用户管理"])
app.include_router(jabobo_config.router, prefix="/api", tags=["配置管理"]) 
app.include_router(jabobo_manager.router, prefix="/api", tags=["捷宝宝管理"]) 
app.include_router(device_data_api.router, prefix="/api", tags=["设备端请求管理"]) 
app.include_router(jabobo_knowlege.router, prefix="/api", tags=["知识库管理"])
app.include_router(chat_config.router, prefix="/api", tags=["聊天差异化配置"]) 
app.include_router(jabobo_voice.router, prefix="/api", tags=["声纹管理"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)