"""
DisruptionShield - FastAPI Backend (Vercel Serverless Version)
Serves the HTML dashboard and handles API calls
"""
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Ensure root directory is in sys.path for serverless imports
root_path = Path(__file__).parent.parent
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

# Serve the frontend directory statically (Corrected path for api/ subfolder)
frontend_path = root_path / "frontend"
if frontend_path.exists():
    app.mount("/src", StaticFiles(directory=frontend_path / "src"), name="src")
    app.mount("/public", StaticFiles(directory=frontend_path / "public"), name="public")

coordinator = CoordinatorAgent()
shield_active = False # Global shield state


# Lazy DB initialization flag
db_initialized = False

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

@app.get("/api/health")
async def health_check():
    """Endpoint for monitoring and testing deployment."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "db_initialized": db_initialized,
        "vercel": os.getenv("VERCEL") == "1"
    }

@app.middleware("http")
async def db_session_middleware(request, call_next):
    """Ensure DB is ready before any API call."""
    if request.url.path.startswith("/api"):
        await ensure_db()
    response = await call_next(request)
    return response


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = frontend_path / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


class ChatRequest(BaseModel):
    message: str
    agent: str = "Coordinator"


class DisruptRequest(BaseModel):
    message: str
    delay: int = 60

class TaskCreate(BaseModel):
    title: str
    start_time: str
    end_time: str = None

class RecoverRequest(BaseModel):
    message: str

class ShieldToggle(BaseModel):
    active: bool


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
            "Respond naturally and helpfully. "
            "If greeting, greet back warmly. "
            "If asking about capabilities, explain DisruptionShield clearly. "
            "If it is a disruption, describe what this agent is doing. "
            "Be concise, friendly, and professional. Max 3 sentences."
        )

        try:
            response = await call_llm(
                prompt=prompt,
                system_prompt=(
                    f"You are the {req.agent} of DisruptionShield, an AI productivity assistant. "
                    "Respond naturally to any message. Be warm, helpful, and concise."
                ),
                max_tokens=300,
            )
            return {"message": response}
        except Exception as e:
            lower = req.message.lower()
            if any(g in lower for g in ["hi", "hello", "hey"]):
                return {"message": "Hey! 👋 I'm DisruptionShield Coordinator. Tell me about any disruption and I'll re-plan your entire day instantly using 4 AI agents!"}
            return {"message": f"Processing your request with {req.agent}..."}

@app.post("/api/recover")
async def recover(req: RecoverRequest):
    """
    Cascading recovery: Shifts all future tasks and ensures they don't overlap.
    """
    from sqlalchemy import select
    from models.task_model import Task
    from models.disruption_log import DisruptionLog

    message = req.message.lower()
    shift = 0
    if "traffic" in message:
        shift = 30
    elif "power" in message:
        shift = 60
    elif "emergency" in message:
        shift = 90
    elif "meeting" in message:
        shift = 45

    if shift == 0:
        return {"msg": "no disruption"}

    async with AsyncSessionLocal() as session:
        # Query all tasks ordered by start_time
        stmt = select(Task).order_by(Task.start_time)
        result = await session.execute(stmt)
        tasks = result.scalars().all()
        
        now = datetime.now().strftime("%H:%M")
        prev_end = None

        for task in tasks:
            # ❌ skip past tasks
            if task.start_time < now:
                continue

            old_start = task.start_time
            start_dt = datetime.strptime(task.start_time, "%H:%M")

            # 👉 first task shift
            if prev_end is None:
                new_start = start_dt + timedelta(minutes=shift)
            else:
                prev_dt = datetime.strptime(prev_end, "%H:%M")
                # Ensure it doesn't start before the previous task ends
                new_start = max(start_dt + timedelta(minutes=shift), prev_dt)

            # Standard 1 hour duration
            new_end = new_start + timedelta(hours=1)

            # ✅ store original time (only once)
            if not task.original_start_time:
                task.original_start_time = old_start

            # ✅ update
            task.start_time = new_start.strftime("%H:%M")
            task.end_time = new_end.strftime("%H:%M")
            task.status = "rescheduled"

            prev_end = task.end_time

            # ✅ history log
            log = DisruptionLog(
                title=task.title,
                old_start=old_start,
                new_start=task.start_time,
                reason=message,
                disruption_type=message.split()[0] if message else "disruption",
                severity="High" if shift > 30 else "Moderate"
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

@app.get("/api/shield")
async def get_shield():
    return {"active": shield_active}

@app.post("/api/shield")
async def toggle_shield(req: ShieldToggle):
    global shield_active
    shield_active = req.active
    return {"status": "ok", "active": shield_active}

@app.post("/api/seed")
async def seed():
    async with AsyncSessionLocal() as session:
        demo_tasks = [
            {"title": "Submit Q1 financial report",    "priority": 5, "start_time": "09:00", "end_time": "11:00"},
            {"title": "Review client contract draft",  "priority": 4, "start_time": "11:30", "end_time": "12:30"},
            {"title": "Team standup notes",            "priority": 3, "start_time": "14:00", "end_time": "15:00"},
            {"title": "Update project roadmap slides", "priority": 3, "start_time": "15:30", "end_time": "17:30"},
            {"title": "Reply to vendor emails",        "priority": 2, "start_time": "18:00", "end_time": "19:00"},
        ]
        for t in demo_tasks:
            await tool_add_task(session, **t)

        demo_events = [
            {"title": "Morning standup",              "start_time": "09:00", "end_time": "09:30"},
            {"title": "Client strategy presentation", "start_time": "10:00", "end_time": "11:00"},
            {"title": "Q1 report review meeting",     "start_time": "11:30", "end_time": "12:30"},
            {"title": "Lunch with team",              "start_time": "13:00", "end_time": "14:00"},
        ]
        for e in demo_events:
            await tool_add_event(session, **e)

@app.get("/{path:path}")
async def catch_all(path: str):
    """Diagnostic route to identify path mismatches in Vercel."""
    return {
        "error": "Path Not Found",
        "path_received": f"/{path}",
        "available_endpoints": ["/", "/api/tasks", "/api/chat", "/api/health"],
        "hint": "If you see a path like 'api/tasks' here, the rewrite is not stripping the prefix."
    }
