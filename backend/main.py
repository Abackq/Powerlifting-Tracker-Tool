from fastapi import FastAPI
from pydantic import BaseModel
from datetime import date
from uuid import UUID
from supabase import create_client, Client
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
import os
from fastapi import HTTPException

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

# Get health status of the API
@app.get("/health")
def health_check():
    return {"status": "ok"}

class SetInput(BaseModel):
    set_number: int
    reps: int
    weight_value: float | None = None
    weight_unit: str | None = None
    rpe: float | None = None
    set_type: str | None = None
    notes: str | None = None

class ExerciseInput(BaseModel):
    exercise_name: str
    exercise_role: str | None = None
    sets: list[SetInput]

class SessionInput(BaseModel):
    client_id: UUID
    present_date: date | None = None
    program_week_id: UUID | None = None
    day_number: int | None = None
    exercises: list[ExerciseInput]

class ProgramWeekInput(BaseModel):
    client_id: UUID
    block: int
    week: int
    week_start_date: date
    week_end_date: date

class SessionBatchInput(BaseModel):
    sessions: list[SessionInput]

def get_exercise_id(exercise_name: str) -> UUID | None:
    result = supabase.table("exercises").select("id").ilike("name", exercise_name.strip()).execute()
    if result.data:
        return result.data[0]["id"]
    return None

#region sessions
@app.post("/sessions")
def create_session(session: SessionInput):
    if session.program_week_id is None:
        raise HTTPException(status_code=422, detail="program_week_id is required")

    existing = supabase.table("sessions").select("id") \
        .eq("client_id", str(session.client_id)) \
        .eq("program_week_id", str(session.program_week_id)) \
        .eq("day_number", session.day_number) \
        .execute()

    if existing.data:
        session_id = existing.data[0]["id"]
    else:
        session_result = supabase.table("sessions").insert({
            "client_id": str(session.client_id),
            "present_date": session.present_date.isoformat() if session.present_date else None,
            "program_week_id": str(session.program_week_id),
            "day_number": session.day_number
        }).execute()
        session_id = session_result.data[0]["id"]

    rejected_exercises = []
    for exercise in session.exercises:
        exercise_id = get_exercise_id(exercise.exercise_name)
        if exercise_id is None:
            rejected_exercises.append({"exercise_name": exercise.exercise_name, "reason": "Exercise not found"})
            continue

        existing_se = supabase.table("session_exercises").select("id") \
            .eq("session_id", session_id) \
            .eq("exercise_id", exercise_id) \
            .execute()

        if existing_se.data:
            continue  # this exercise was already written on an earlier run

        se_result = supabase.table("session_exercises").insert({
            "session_id": session_id,
            "exercise_id": exercise_id,
            "exercise_role": exercise.exercise_role,
        }).execute()
        session_exercise_id = se_result.data[0]["id"]

        for s in exercise.sets:
            supabase.table("training_log").insert({
                "session_exercise_id": session_exercise_id,
                "set_number": s.set_number,
                "reps": s.reps,
                "weight_value": s.weight_value,
                "weight_unit": s.weight_unit,
                "rpe": s.rpe,
                "set_type": s.set_type,
                "notes": s.notes
            }).execute()

    return {"session_id": session_id, "rejected_exercises": rejected_exercises}

# endregion sessions

#region program weeks
@app.post("/program-weeks")
def create_program_week(program_week: ProgramWeekInput): 
    existing = supabase.table("program_weeks").select("id") \
        .eq("client_id", str(program_week.client_id)) \
        .eq("block", program_week.block) \
        .eq("week", program_week.week) \
        .execute()

    if existing.data:
        return {"program_week_id": existing.data[0]["id"]}

    result = supabase.table("program_weeks").insert({
        "client_id": str(program_week.client_id),
        "block": program_week.block,
        "week": program_week.week,
        "week_start_date": program_week.week_start_date.isoformat(),
        "week_end_date": program_week.week_end_date.isoformat(),
    }).execute()

    return {"program_week_id": result.data[0]["id"]}

# endregion program weeks

#region sessions/batch
@app.post("/sessions/batch")
def create_sessions_batch(batch: SessionBatchInput):
    results = []
    for session in batch.sessions:
        try: 
            result = create_session(session)
            results.append({"status": "ok", **result})
        except HTTPException as e:
            results.append({"status": "error", "detail": e.detail})
        except Exception as e:
            results.append({"status": "error", "detail": str(e)})
    return {"results": results}

#endregion sessions/batch

