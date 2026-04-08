"""
DisruptionShield - FastAPI Backend (Bulletproof Serverless Entry)
Uses late-imports to ensure zero startup crashes and clear error reporting.
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

# ─── Foundation ────────────────────────────────────────────────────────────

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

# ─── Defensive Mounting ─────────────────────────────────────────────────────

frontend_path = root_path / "frontend"
try:
    if frontend_path.exists():
        from fastapi.staticfiles import StaticFiles
        # We mount these safely. If they fail, the app still boots.
        if (frontend_path / "src").exists():
            app.mount("/src", StaticFiles(directory=frontend_path / "src"), name="src")
        if (frontend_path / "public").exists():
            app.mount("/public", StaticFiles(directory=frontend_path / "public"), name="public")
except Exception as e:
    print(f"Non-critical: Static mount failed: {e}")

# ─── Diagnostic Middleware ──────────────────────────────────────────────────

@app.middleware("http")
async def diagnostic_middleware(request, call_next):
    """Global error catcher that displays tracebacks in UI."""
    try:
        # Move DB init here to catch its errors too
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
            <html>
                <body style="font-family: sans-serif; padding: 2rem; background: #0f172a; color: #f8fafc;">
                    <h1 style="color: #ef4444;">DisruptionShield: Internal Diagnostics</h1>
                    <p>The server is running but encountered a runtime failure.</p>
                    <div style="background: #1e293b; padding: 1.5rem; border-radius: 0.5rem; overflow: auto; border: 1px solid #334155;">
                        <pre style="color: #fda4af; margin: 0; font-family: monospace; white-space: pre-wrap;">{error_info}</pre>
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
    """Main dashboard entry point."""
    html_path = frontend_path / "index.html"
    if not html_path.exists():
        return HTMLResponse(content="<h1>Setup Error</h1><p>index.html not found.</p>", status_code=500)
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

@app.get("/api/health")
async def health():
    return {"status": "ok", "db": db_initialized}

@app.post("/api/chat")
async def chat(data: dict = Body(...)):
    # Late-import heavy agents to avoid startup crashes
    from agents.llm_client import call_llm
    from database import AsyncSessionLocal
    from tools.db_tools import tool_get_all_tasks, tool_get_todays_events, tool_get_disruption_history
    
    agent = data.get("agent", "Coordinator")
    message = data.get("message", "")
    
    async with AsyncSessionLocal() as session:
        t_res = await tool_get_all_tasks(session)
        e_res = await tool_get_todays_events(session)
        
        prompt = f"User: {message}\nContext: {len(t_res.get('tasks', []))} tasks active."
        try:
            response = await call_llm(prompt=prompt, system_prompt=f"You are {agent}.")
            return {"message": response}
        except Exception:
            return {"message": f"Processing request with {agent}..."}

@app.post("/api/recover")
async def recover(data: dict = Body(...)):
    # Late-import model logic
    from database import AsyncSessionLocal
    from sqlalchemy import select
    from models.task_model import Task
    from models.disruption_log import DisruptionLog

    message = data.get("message", "").lower()
    shift = 30 # Default
    
    async with AsyncSessionLocal() as session:
        stmt = select(Task).order_by(Task.start_time)
        res = await session.execute(stmt)
        tasks = res.scalars().all()
        
        for task in tasks:
            # Simple shift recovery
            old_start = task.start_time
            if not task.original_start_time: task.original_start_time = old_start
            
            s_dt = datetime.strptime(task.start_time, "%H:%M") + timedelta(minutes=shift)
            task.start_time = s_dt.strftime("%H:%M")
            task.status = "rescheduled"
            
            log = DisruptionLog(title=task.title, old_start=old_start, new_start=task.start_time, reason=message)
            session.add(log)
            
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
