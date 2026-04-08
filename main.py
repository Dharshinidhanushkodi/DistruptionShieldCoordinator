"""
DisruptionShield - FastAPI Backend (Production Build)
Serves the compiled React 'dist' folder for maximum performance and stability.
"""
import os
import sys
import json
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, Depends, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# ─── Foundation ────────────────────────────────────────────────────────────

# Use absolute path resolution to ensure stability on Vercel
root_path = Path(__file__).resolve().parent
sys.path.append(str(root_path))

app = FastAPI(title="DisruptionShield Coordinator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared state
db_initialized = False

# ─── Production Asset Mounting ──────────────────────────────────────────────

# Path to the compiled frontend
dist_path = root_path / "frontend" / "dist"

try:
    if dist_path.exists():
        print(f"Production build found at: {dist_path}")
        # Mount /assets to dist/assets
        if (dist_path / "assets").exists():
            app.mount("/assets", StaticFiles(directory=str(dist_path / "assets")), name="assets")
        # Mount the rest of dist to /static fallback
        app.mount("/static", StaticFiles(directory=str(dist_path)), name="static")
    else:
        print("CRITICAL: Production 'dist' folder not found. Falling back to source mode.")
        src_path = root_path / "frontend"
        if (src_path / "src").exists():
            app.mount("/src", StaticFiles(directory=str(src_path / "src")), name="src")
except Exception as e:
    print(f"Non-critical: Static mount failed: {e}")

# ─── Diagnostic Middleware ──────────────────────────────────────────────────

@app.middleware("http")
async def diagnostic_middleware(request, call_next):
    """Global error catcher that displays tracebacks in UI."""
    try:
        if request.url.path.startswith("/api"):
            global db_initialized
            if not db_initialized:
                from database import init_db
                await init_db()
                db_initialized = True
        return await call_next(request)
    except Exception as e:
        error_info = traceback.format_exc()
        print(f"CRITICAL RUNTIME ERROR:\n{error_info}")
        return HTMLResponse(
            content=f"""
            <html style="background: #0f172a; color: #f8fafc; font-family: sans-serif;">
                <body style="padding: 2rem;">
                    <h1 style="color: #ef4444;">DisruptionShield: Internal Diagnostics</h1>
                    <p>The server encountered a runtime failure.</p>
                    <div style="background: #1e293b; padding: 1.5rem; border-radius: 0.5rem; border: 1px solid #334155;">
                        <pre style="color: #fda4af; font-family: monospace;">{error_info}</pre>
                    </div>
                </body>
            </html>
            """,
            status_code=500
        )

# ─── Routes ────────────────────────────────────────────────────────────────

@app.get("/")
@app.get("/api")
async def dashboard():
    """Main dashboard entry point. Favors production dist/index.html."""
    html_path = dist_path / "index.html"
    if not html_path.exists():
        html_path = root_path / "frontend" / "index.html"
        
    if not html_path.exists():
        return HTMLResponse(content="<h1>Setup Error</h1><p>index.html not found. Deployment mismatch.</p>", status_code=500)
    
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

@app.get("/api/health")
async def health():
    return {
        "status": "ok", 
        "db": db_initialized, 
        "dist_exists": dist_path.exists(),
        "root": str(root_path)
    }

# ─── Logic Overrides (Late Imports) ─────────────────────────────────────────

@app.post("/api/chat")
async def chat(data: dict = Body(...)):
    from agents.llm_client import call_llm
    from database import AsyncSessionLocal
    from tools.db_tools import tool_get_all_tasks
    
    agent = data.get("agent", "Coordinator")
    message = data.get("message", "")
    
    async with AsyncSessionLocal() as session:
        t_res = await tool_get_all_tasks(session)
        tasks = t_res.get('tasks', [])
        prompt = f"User: {message}\nContext: {len(tasks)} tasks."
        try:
            response = await call_llm(prompt=prompt, system_prompt=f"You are {agent}.")
            return {"message": response}
        except Exception:
            return {"message": "System active. Ready for input."}

@app.post("/api/recover")
async def recover(data: dict = Body(...)):
    from database import AsyncSessionLocal
    from sqlalchemy import select
    from models.task_model import Task
    from models.disruption_log import DisruptionLog

    message = data.get("message", "").lower()
    shift = 30
    
    async with AsyncSessionLocal() as session:
        stmt = select(Task).order_by(Task.start_time)
        res = await session.execute(stmt)
        tasks = res.scalars().all()
        
        for task in tasks:
            old_start = task.start_time
            if not task.original_start_time: task.original_start_time = old_start
            s_dt = datetime.strptime(task.start_time, "%H:%M") + timedelta(minutes=shift)
            task.start_time = s_dt.strftime("%H:%M")
            task.status = "rescheduled"
            session.add(DisruptionLog(title=task.title, old_start=old_start, new_start=task.start_time, reason=message))
            
        await session.commit()
        return {"msg": "rescheduled"}

@app.get("/api/tasks")
async def get_tasks():
    from database import AsyncSessionLocal
    from tools.db_tools import tool_get_all_tasks
    async with AsyncSessionLocal() as session:
        res = await tool_get_all_tasks(session)
        return res.get("tasks", [])

@app.get("/{path:path}")
async def catch_all(path: str):
    return {"error": "not found", "path": path}
