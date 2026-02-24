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
META_FILE = os.path.join(UPLOAD_DIR, "meta.json")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/i", StaticFiles(directory=UPLOAD_DIR), name="images")

# 绝对稳健：本地测试无脑 123456
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "123456")

def load_meta():
    if os.path.exists(META_FILE):
        with open(META_FILE, 'r') as f: return json.load(f)
    return {}

def save_meta(data):
    with open(META_FILE, 'w') as f: json.dump(data, f)

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join(BASE_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/verify")
async def verify_token(x_auth_token: str = Header(None)):
    print(f"收到登录请求，密码: {x_auth_token}") # 终端打印，方便你排查
    if x_auth_token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="密码错误")
    return {"success": True}

@app.post("/upload")
async def upload_image(request: Request, file: UploadFile = File(...), expire_days: int = Form(0), x_auth_token: str = Header(None)):
    if x_auth_token != AUTH_TOKEN: 
        raise HTTPException(status_code=401)
    
    ext = file.filename.split(".")[-1]
    new_filename = f"{int(time.time()*1000)}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, new_filename)
    
    with open(file_path, "wb") as buffer: 
        buffer.write(await file.read())
        
    if expire_days > 0:
        meta = load_meta()
        meta[new_filename] = time.time() + (expire_days * 86400)
        save_meta(meta)

    base_url = str(request.base_url)
    return JSONResponse(content={
        "success": True, 
        "url": f"{base_url}i/{new_filename}",
        "size": os.path.getsize(file_path)
    })

@app.get("/api/history")
async def get_history(request: Request, x_auth_token: str = Header(None)):
    if x_auth_token != AUTH_TOKEN: 
        raise HTTPException(status_code=401)
    meta = load_meta()
    files_list = []
    base_url = str(request.base_url)
    for filename in os.listdir(UPLOAD_DIR):
        if filename == "meta.json": continue
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.isfile(file_path):
            stat = os.stat(file_path)
            files_list.append({"filename": filename, "url": f"{base_url}i/{filename}", "time": stat.st_mtime})
    files_list.sort(key=lambda x: x["time"], reverse=True)
    return {"success": True, "images": files_list}

@app.delete("/api/delete/{filename}")
async def delete_image(filename: str, x_auth_token: str = Header(None)):
    if x_auth_token != AUTH_TOKEN: raise HTTPException(status_code=401)
    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path): 
        os.remove(file_path)
        return {"success": True}
    raise HTTPException(status_code=404)