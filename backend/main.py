from fastapi import FastAPI
from pydantic import BaseModel
from datetime import date
from uuid import UUID
from supabase import create_client, Client
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
print("Looking for .env at:", env_path)
print(".env exists:", env_path.exists())
result = load_dotenv(env_path)
print("load_dotenv succeeded:", result)

import os

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class SetInput(BaseModel):
    set_number: int
    reps: int
    weight_value: float
    weight_unit: str
    rpe: float | None = None
    set_type: str | None = None
    notes: str | None = None

class ExerciseInput(BaseModel):
    exercise_id: UUID
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

app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}