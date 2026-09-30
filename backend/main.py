from fastapi import FastAPI
from pydantic import BaseModel
from datetime import date
from uuid import UUID
from supabase import create_client, Client
from pathlib import Path
from dotenv import load_dotenv
import os
from fastapi import HTTPException

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

class SetInput(BaseModel):
    set_number: int
    reps: int
    weight_value: float
    weight_unit: str
    rpe: float | None = None
    set_type: str | None = None
    notes: str | None = None

class ExerciseInput(BaseModel):
    exercise_id: str
    exercise_role: str
    sets: list[SetInput]

class SessionInput(BaseModel):
    client_id: UUID
    present_date: date | None = None
    program_week_id: UUID | None = None
    day_number: int | None = None
    exercises: list[ExerciseInput]

def get_exercise_id(exercise_name: str) -> UUID | None:
    result = supabase.table("exercises").select("id").eq("name", exercise_name).execute()
    if result.data:
        return result.data[0]["id"]
    return None

@app.post("/sessions")
def create_session(session: SessionInput):
    session_result = supabase.table("sessions").insert({
        "client_id": str(session.client_id),
        "present_date": session.present_date.isoformat() if session.present_date else None,
        "program_week_id": str(session.program_week_id) if session.program_week_id else None,
        "day_number": session.day_number
    }).execute()
    session_id = session_result.data[0]["id"]

    rejected_exercises = []
    for exercise in session.exercises:
        exercise_id = get_exercise_id(exercise.exercise_name)
        if exercise_id is None:
            rejected_exercises.append({"exercise_name": exercise.exercise_name, "reason": "Exercise not found"})
            continue

        se_result = supabase.table("session_exercises").insert({
            "session_id": session_id,
            "exercise_id": exercise_id,
            "exercise_role": exercise.exercise_role
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

        return{"session_id": session_id, "rejected_exercises": rejected_exercises}

    
