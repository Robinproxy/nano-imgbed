import os
import time
import json
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
META_FILE = os.path.join(UPLOAD_DIR, "meta.json") # 用于记录过期时间的数据库替代品
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/i", StaticFiles(directory=UPLOAD_DIR), name="images")

# 从环境变量读取密码，本地测试默认 123456
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "123456")

# --- 辅助函数：读写过期元数据 ---
def load_meta():
    if os.path.exists(META_FILE):
        with open(META_FILE, 'r') as f: return json.load(f)
    return {}

def save_meta(data):
    with open(META_FILE, 'w') as f: json.dump(data, f)

# --- 后台定时清理任务 (阅后即焚核心) ---
@app.on_event("startup")
async def start_cleanup_task():
    async def cleanup_loop():
        while True:
            meta = load_meta()
            now = time.time()
            to_delete = []
            
            # 找出所有已过期的文件
            for filename, expire_at in meta.items():
                if expire_at > 0 and now > expire_at:
                    to_delete.append(filename)
            
            # 执行删除
            for filename in to_delete:
                file_path = os.path.join(UPLOAD_DIR, filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"[清理] 已自动删除过期文件: {filename}")
                del meta[filename]
            
            if to_delete:
                save_meta(meta)
                
            # 每小时检查一次
            await asyncio.sleep(3600)
            
    asyncio.create_task(cleanup_loop())

# --- 路由接口 ---
@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join(BASE_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/verify")
async def verify_token(x_auth_token: str = Header(None)):
    """处理前端的登录请求"""
    if x_auth_token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="密码错误")
    return {"success": True}

@app.post("/upload")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    expire_days: int = Form(0), # 接收前端传来的过期天数
    x_auth_token: str = Header(None)
):
    if x_auth_token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="未授权")

    ext = file.filename.split(".")[-1]
    new_filename = f"{int(time.time())}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, new_filename)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # 如果设置了过期时间，记录到 meta.json
    if expire_days > 0:
        meta = load_meta()
        expire_timestamp = time.time() + (expire_days * 86400) # 转换为秒
        meta[new_filename] = expire_timestamp
        save_meta(meta)

    base_url = str(request.base_url)
    image_url = f"{base_url}i/{new_filename}"

    return JSONResponse(content={"success": True, "url": image_url})