"""
DisruptionShield - FastAPI Backend (Vercel-Optimized Entry Point)
Handles dashboard serving and API orchestration with lazy-loading agents.
"""
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, Depends, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Correct path logic for root-level entry
root_path = Path(__file__).parent
sys.path.append(str(root_path))

from database import init_db, AsyncSessionLocal
from agents.coordinator import CoordinatorAgent
from agents.llm_client import call_llm
from tools.db_tools import (
    tool_add_task, tool_get_all_tasks,
    tool_add_event, tool_get_todays_events,
    tool_get_disruption_history,
    tool_analyze_disruption_patterns,
    tool_get_recovery_plans,
    tool_log_disruption,
)

app = FastAPI(title="DisruptionShield Coordinator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend directory statically
frontend_path = root_path / "frontend"
if frontend_path.exists():
    app.mount("/src", StaticFiles(directory=frontend_path / "src"), name="src")
    app.mount("/public", StaticFiles(directory=frontend_path / "public"), name="public")

# ─── Lazy Initialization ───────────────────────────────────────────────────

_coordinator = None
db_initialized = False

async def get_coordinator():
    """Lazy-loads the CoordinatorAgent to prevent startup timeouts."""
    global _coordinator
    if _coordinator is None:
        print("Lazy-loading CoordinatorAgent...")
        _coordinator = CoordinatorAgent()
    return _coordinator

async def ensure_db():
    """Ensures database is initialized before processing any request."""
    global db_initialized
    if not db_initialized:
        print("Lazy-initializing database...")
        try:
            await init_db()
            db_initialized = True
            print("Database initialized successfully.")
        except Exception as e:
            print(f"FAILED to initialize database: {e}")
            raise

@app.middleware("http")
async def error_handling_middleware(request, call_next):
    """Diagnostic middleware to catch and display internal errors."""
    try:
        if request.url.path.startswith("/api"):
            # Moved DB init check inside the try block to catch crashes here too
            global db_initialized
            if not db_initialized:
                await init_db()
                db_initialized = True
        return await call_next(request)
    except Exception as e:
        import traceback
        from fastapi.responses import HTMLResponse
        error_info = traceback.format_exc()
        print(f"CRITICAL ERROR: {error_info}")
        return HTMLResponse(
            content=f"""
            <html>
                <body style="font-family: sans-serif; padding: 2rem; background: #0f172a; color: #f8fafc;">
                    <h1 style="color: #ef4444;">DisruptionShield: Runtime Error</h1>
                    <p>The server encountered an error during startup or request handling.</p>
                    <div style="background: #1e293b; padding: 1.5rem; border-radius: 0.5rem; overflow: auto; border: 1px solid #334155;">
                        <pre style="color: #fda4af; margin: 0; font-family: monospace; white-space: pre-wrap;">{error_info}</pre>
                    </div>
                    <p style="margin-top: 1.5rem; color: #94a3b8; font-size: 0.875rem;">
                        💡 Common Fix: Ensure <b>GEMINI_API_KEY</b> is set in your Vercel Project Settings.
                    </p>
                </body>
            </html>
            """,
            status_code=500
        )

# ─── Health & Dashboard ─────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Endpoint for monitoring and testing deployment."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "db_initialized": db_initialized,
        "vercel": os.getenv("VERCEL") == "1"
    }

@app.get("/", response_class=HTMLResponse)
@app.get("/api", response_class=HTMLResponse)
async def dashboard():
    """Main dashboard entry point."""
    html_path = frontend_path / "index.html"
    if not html_path.exists():
        return HTMLResponse(content=f"<h1>Setup Error</h1><p>index.html not found. Path: {html_path}</p>", status_code=500)
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

# ─── Models ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    agent: str = "Coordinator"

class TaskCreate(BaseModel):
    title: str
    start_time: str
    end_time: str = None

class RecoverRequest(BaseModel):
    message: str

class ShieldToggle(BaseModel):
    active: bool

# ─── API Endpoints ─────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: ChatRequest):
    async with AsyncSessionLocal() as session:
        tasks_result   = await tool_get_all_tasks(session, status_filter="Pending")
        events_result  = await tool_get_todays_events(session)
        history_result = await tool_get_disruption_history(session, limit=5)

        tasks   = tasks_result.get("tasks", [])[:5]
        events  = events_result.get("events", [])
        history = history_result.get("disruption_logs", [])[:3]

        context = (
            f"Pending tasks: {json.dumps([t['title'] for t in tasks])}\n"
            f"Today's events: {json.dumps([e['title'] for e in events])}\n"
            f"Recent disruptions: {json.dumps([d['disruption_type'] for d in history])}\n"
            f"Current time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Active agent: {req.agent}"
        )

        prompt = (
            f"{context}\n\nUser: {req.message}\n\n"
            "Respond naturally and helpfully. Max 3 sentences."
        )

        try:
            response = await call_llm(
                prompt=prompt,
                system_prompt=(
                    f"You are the {req.agent} of DisruptionShield. Be warm, helpful, and concise."
                ),
                max_tokens=300,
            )
            return {"message": response}
        except Exception as e:
            return {"message": f"Processing your request with {req.agent}..."}

@app.post("/api/recover")
async def recover(req: RecoverRequest):
    """Cascading recovery logic."""
    from sqlalchemy import select
    from models.task_model import Task
    from models.disruption_log import DisruptionLog

    message = req.message.lower()
    shift = 0
    if "traffic" in message: shift = 30
    elif "power" in message: shift = 60
    elif "emergency" in message: shift = 90
    elif "meeting" in message: shift = 45

    if shift == 0: return {"msg": "no disruption"}

    async with AsyncSessionLocal() as session:
        stmt = select(Task).order_by(Task.start_time)
        result = await session.execute(stmt)
        tasks = result.scalars().all()
        
        now = datetime.now().strftime("%H:%M")
        prev_end = None

        for task in tasks:
            if task.start_time < now: continue

            old_start = task.start_time
            start_dt = datetime.strptime(task.start_time, "%H:%M")

            if prev_end is None:
                new_start = start_dt + timedelta(minutes=shift)
            else:
                prev_dt = datetime.strptime(prev_end, "%H:%M")
                new_start = max(start_dt + timedelta(minutes=shift), prev_dt)

            new_end = new_start + timedelta(hours=1)
            if not task.original_start_time: task.original_start_time = old_start

            task.start_time = new_start.strftime("%H:%M")
            task.end_time = new_end.strftime("%H:%M")
            task.status = "rescheduled"
            prev_end = task.end_time

            log = DisruptionLog(
                title=task.title,
                old_start=old_start,
                new_start=task.start_time,
                reason=message,
                disruption_type=message.split()[0] if message else "disruption"
            )
            session.add(log)
        
        await session.commit()
        return {"msg": "rescheduled"}

@app.get("/api/tasks")
async def get_tasks():
    async with AsyncSessionLocal() as session:
        result = await tool_get_all_tasks(session)
        return result.get("tasks", [])

@app.post("/api/tasks")
async def add_task(req: TaskCreate):
    async with AsyncSessionLocal() as session:
        result = await tool_add_task(session, **req.dict())
        return result

@app.get("/api/history")
async def get_history():
    async with AsyncSessionLocal() as session:
        result = await tool_get_disruption_history(session, limit=20)
        return result.get("disruption_logs", [])

@app.post("/api/seed")
async def seed():
    async with AsyncSessionLocal() as session:
        demo_tasks = [
            {"title": "Submit Q1 financial report", "start_time": "09:00", "end_time": "11:00"},
            {"title": "Review client contract draft", "start_time": "11:30", "end_time": "12:30"},
        ]
        for t in demo_tasks: await tool_add_task(session, **t)
    return {"status": "ok", "message": "Demo data loaded!"}

@app.get("/{path:path}")
async def catch_all(path: str):
    """Diagnostic route."""
    return {"error": "Path Not Found", "path": f"/{path}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
