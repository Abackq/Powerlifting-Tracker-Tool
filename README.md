# Powerlifting Tracker

A coaching platform for tracking powerlifting clients' training, built to replace
spreadsheet-based programming. Clients log sessions in a Next.js app backed by
Supabase, with row-level security so each client only sees their own data.

A FastAPI service handles bulk writes, and a Python pipeline migrates existing
Excel programs into the database. It detects the irregular week and day layout
with openpyxl, validates each row, and sends the results through the API.

## Structure
- `frontend/`: Next.js client app
- `backend/`: FastAPI service
- `pipeline/`: Excel migration pipeline
- `database/`: schema and RLS policies
