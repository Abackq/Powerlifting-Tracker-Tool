from openpyxl import load_workbook
import re
import time
from datetime import datetime, date
from datetime import timedelta
import requests
from collections import Counter
import sys

API_URL = "http://127.0.0.1:8000"

WEEK_PATTERN = re.compile(r"^(?:Week\s+(\d+)|Meet\s+Week)$", re.IGNORECASE)
DAY_PATTERN = re.compile(r"Day\s+(\d+)$", re.IGNORECASE)
DATE_FORMATS = ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%B %d, %Y"]
SETS_REPS_PATTERN = re.compile(r"^(\d+)\s*x\s*(\d+)(?:\s*-\s*\d+)?$", re.IGNORECASE)

class UnloggedSet(Exception):
    """Row has no logged load: a prescribed set the client hasn't filled in."""

# region Stage 1: Loading
def load_client_workbook(filepath: str):
    workbook = load_workbook(filepath, read_only=False, data_only=True)
    return workbook

def split_tabs(workbook, metadata_tab_name: str = "READ ME"):
    """Partitions a workbook's tabs into (metadata_sheet, block_tab_names).
    metadata_sheet is None if no matching tab exists; the caller decides whether that's an error."""
    metadata_sheet = None
    block_tabs = []
    for name in workbook.sheetnames:
        if name.strip() == metadata_tab_name.strip():
            metadata_sheet = workbook[name]
        else:
            block_tabs.append(name)
    return metadata_sheet, block_tabs

def get_block_tabs(workbook, metadata_tab_name: str = "READ ME") -> list[str]:
    "Returns tab names in order, excluding metadata tabs, preserving order for block numbering"
    return split_tabs(workbook, metadata_tab_name)[1]

# endregion Stage 1: Loading

# region Stage 2: Structure Mapping (weeks, days, blocks)
def find_week_columns(sheet) -> list[dict]:
    "Scans the sheet for 'Week N' labels and returns their row column, and week number."
    weeks = []
    for row in sheet.iter_rows():
        for cell in row:
            if isinstance(cell.value, str):
                match = WEEK_PATTERN.match(cell.value.strip())
                if match:
                    is_meet_week = match.group(1) is None
                    weeks.append({
                        "week_number": len(weeks) + 1 if is_meet_week else int(match.group(1)),
                        "is_meet_week": is_meet_week,
                        "row": cell.row,
                        "start_column": cell.column
                    })
    return weeks

def find_day_rows(sheet, week: dict) -> list[dict]:
    "Scans down from the start column of the given week to find 'Day N' labels."
    days = []
    col = week["start_column"]
    for row in sheet.iter_rows(min_row=week["row"] + 1, min_col=col, max_col=col):
        cell = row[0]
        if isinstance(cell.value, str):
            match = DAY_PATTERN.match(cell.value.strip())
            if match:
                days.append({
                    "day_number": int(match.group(1)),
                    "row": cell.row
                })
    return days

def build_week_day_structure(sheet) -> list[dict]:
    "Combines week detection and day detection into a structured list."
    weeks = find_week_columns(sheet)
    for week in weeks:
        week["days"] = find_day_rows(sheet, week)
        compute_day_ranges(sheet, week)
    return weeks

def build_all_blocks(workbook) -> list[dict]:
    """Builds the full week/day structure for every training block tab, attaching 
    the sequential block number based on tab order."""
    block_tabs = get_block_tabs(workbook)
    blocks = []
    for block_number, tab_name in enumerate(block_tabs, start=1):
        sheet = workbook[tab_name]
        blocks.append({
            "block_number": block_number,
            "tab_name": tab_name,
            "weeks": build_week_day_structure(sheet)
        })
    return blocks

def resolve_day_end(sheet, day: dict, search_limit: int, exercise_col: int) -> None:
    """Scans downward from day['start_row'] until a blank row is found,
    but never searches past search_limit (the next day's row, or sheet's max_row)."""
    row = day["start_row"]
    while row < search_limit:
        cell = sheet.cell(row=row, column=exercise_col)
        if cell.value is None:
            day["end_row"] = row
            return
        row += 1
    day["end_row"] = search_limit  # reached the limit without finding a blank row

def compute_day_ranges(sheet, week: dict) -> list[dict]:
    """Adds start_row and end_row to each day, using blank-row detection bounded
    by the next day's row (or sheet end, for the last day)."""
    days = week["days"]
    exercise_col = week["start_column"]
    max_row = sheet.max_row
    for i, day in enumerate(days):
        day["start_row"] = day["row"] + 1  # Exercises start the row after "Day N"
        search_limit = days[i + 1]["row"] if i + 1 < len(days) else max_row + 1
        resolve_day_end(sheet, day, search_limit, exercise_col)
    return days

# endregion Stage 2: Structure Mapping (weeks, days, blocks)

# region Stage 3: Extraction
def parse_day_headers(sheet, week: dict, day: dict) -> dict:
    """Reads the header row for a given day and returns a dict mapping
    field name -> column number, handling the duplicate 'load' header case."""
    header_row = day["row"]
    start_col = week["start_column"]
    max_col = start_col + 10  # generous upper bound for one day's column band; adjust if needed

    load_columns = []
    field_columns = {}

    for col in range(start_col, max_col):
        cell = sheet.cell(row=header_row, column=col)
        if not isinstance(cell.value, str):
            continue
        header = cell.value.strip().lower()
        if header == "load":
            load_columns.append(col)
        elif header in ("rpe", "notes", "range", "top end"):
            field_columns[header] = col

    if len(load_columns) >= 2:
        field_columns["prescribed_rpe_or_backoff"] = load_columns[0]
        field_columns["actual_load"] = load_columns[1]
    elif len(load_columns) == 1:
        field_columns["actual_load"] = load_columns[0]  # only one load column present — no prescribed value to disambiguate

    return field_columns

def extract_day_exercises(sheet, week: dict, day: dict) -> list[dict]:
    """Extracts each exercise row within a day's row range into a raw dict."""
    fields = parse_day_headers(sheet, week, day)
    name_col = week["start_column"]
    sets_reps_col = week["start_column"] + 1

    exercises = []
    for row in range(day["start_row"], day["end_row"]):
        name_cell = sheet.cell(row=row, column=name_col)
        if name_cell.value is None:
            continue  # skip any stray blank row within the range

        exercise = {
            "block_number": None,  # filled in by caller, which knows the block
            "week_number": week["week_number"],
            "day_number": day["day_number"],
            "row": row,
            "exercise_name": name_cell.value,
            "sets_x_reps": sheet.cell(row=row, column=sets_reps_col).value,
            "prescribed_raw": sheet.cell(row=row, column=fields["prescribed_rpe_or_backoff"]).value if "prescribed_rpe_or_backoff" in fields else None,
            "actual_load_raw": sheet.cell(row=row, column=fields["actual_load"]).value if "actual_load" in fields else None,
            "actual_rpe_raw": sheet.cell(row=row, column=fields["rpe"]).value if "rpe" in fields else None,
            "notes": sheet.cell(row=row, column=fields["notes"]).value if "notes" in fields else None,
        }
        exercises.append(exercise)
    return exercises

def extract_all_exercises(workbook, all_blocks: list[dict], client_id) -> list[dict]:
    """Walks every block -> week -> day, calls extract_day_exercises for each,
    and flattens the results into one single list of raw exercise rows."""
    all_raw_rows = []
    for block in all_blocks:
        sheet = workbook[block["tab_name"]]
        for week in block["weeks"]:
            for day in week["days"]:
                rows = extract_day_exercises(sheet, week, day)
                for row in rows:
                    row["block_number"] = block["block_number"]
                    row["client_id"] = client_id
                all_raw_rows.extend(rows)
    return all_raw_rows

# endregion Stage 3: Extraction

# region Stage 4: Validation
def split_prescribed_value(prescribed_raw) -> dict:
    """Never raises: unreadable or implausible prescribed values become null plus a note."""
    empty = {"prescribed_rpe": None, "prescribed_backoff_pct": None, "set_type": None, "note": None}

    if prescribed_raw is None:
        return empty
    if isinstance(prescribed_raw, datetime):
        # Excel-corrupted range like '6/7' (read as June 7): keep the high end, same as actual RPE
        high = max(prescribed_raw.month, prescribed_raw.day)
        rpe = float(high) if high <= 10 else None
        return {**empty, "prescribed_rpe": rpe, "set_type": "top"}
    if not isinstance(prescribed_raw, (int, float)):
        return {**empty, "note": f"prescribed (unreadable): {prescribed_raw}"}

    if prescribed_raw >= 0:
        if prescribed_raw <= 10:
            return {**empty, "prescribed_rpe": prescribed_raw, "set_type": "top"}
        return {**empty, "set_type": "top", "note": f"prescribed (out of range): {prescribed_raw}"}

    pct = abs(prescribed_raw) * 100
    if pct <= 100:
        return {**empty, "prescribed_backoff_pct": pct, "set_type": "backdown"}
    return {**empty, "set_type": "backdown", "note": f"prescribed (out of range): {prescribed_raw}"}

def validate_numeric_field(value, field_name: str) -> float:
    """Confirms a value (actual_load_raw or actual_rpe_raw) is numeric.
    Raises ValueError if it isn't."""
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} is not numeric: {value!r}")
    return value

def process_exercise_row(raw_row: dict) -> dict:
    """Takes a raw extracted row and returns a clean, validated record.
    Raises ValueError if any field fails validation, and the caller
    routes it to the rejects list."""

    if raw_row["actual_load_raw"] is None:
        raise UnloggedSet()

    prescribed = split_prescribed_value(raw_row["prescribed_raw"])
    actual_load, load_note = numeric_or_note(raw_row["actual_load_raw"], "load")
    actual_rpe, rpe_note = rpe_or_note(normalize_rpe(raw_row["actual_rpe_raw"]))
    num_sets, reps = parse_sets_x_reps(raw_row["sets_x_reps"])

    notes = " | ".join(str(n) for n in [raw_row["notes"], load_note, rpe_note, prescribed["note"]] if n) or None

    return {
        "client_id": raw_row["client_id"],
        "block_number": raw_row["block_number"],
        "week_number": raw_row["week_number"],
        "day_number": raw_row["day_number"],
        "exercise_name": raw_row["exercise_name"],
        "num_sets": num_sets,
        "reps": reps,
        "set_type": prescribed["set_type"],
        "prescribed_rpe": prescribed["prescribed_rpe"],
        "prescribed_backoff_pct": prescribed["prescribed_backoff_pct"],
        "actual_load": actual_load,
        "actual_rpe": actual_rpe,
        "notes": notes,
    }

def process_all_exercises(raw_rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Processes every raw extracted row, separating successes from failures.
    Returns (clean_records, rejected_records)."""
    clean_records = []
    rejected_records = []
    unlogged_records = []

    for raw_row in raw_rows:
        try:
            clean_records.append(process_exercise_row(raw_row))
        except UnloggedSet:
            unlogged_records.append(raw_row)
        except ValueError as e:
            rejected_records.append({
                "client_id": raw_row["client_id"],
                "block_number": raw_row["block_number"],
                "week_number": raw_row["week_number"],
                "day_number": raw_row["day_number"],
                "rejection_reason": str(e)
            })

    return clean_records, rejected_records, unlogged_records

def normalize_rpe(value):
    """Excel turns RPE ranges like '6/7' into dates (June 7).
    Converts them back, keeping the highest number of the range."""
    if isinstance(value, datetime):
        highest = max(value.month, value.day)
        if highest <= 10:   # only trust it if it's a plausible RPE
            return float(highest)
    return value

def numeric_or_note(value, field_name: str):
    """Returns (number, None) if value is numeric, (None, None) if blank,
    or (None, note) if it's text we can't read. The raw text goes to notes."""
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        return value, None
    return None, f"{field_name} (unreadable): {value}"

def rpe_or_note(value):
    """Numbers outside the valid RPE range aren't real RPEs: send no RPE, keep the raw value in notes."""
    number, note = numeric_or_note(value, "rpe")
    if number is not None and not (1 <= number <= 10):
        return None, f"rpe (out of range): {number}"
    return number, note

# endregion Stage 4: Validation

# region Stage 5: Date Derivation
def find_date_started(workbook) -> date:
    """Finds the 'Date Started' label on the metadata tab and returns the date
    in the cell immediately to its right. Raises ValueError if it can't be found or parsed."""
    metadata_sheet, _ = split_tabs(workbook)
    if metadata_sheet is None:
        raise ValueError("metadata tab not found")

    for row in metadata_sheet.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.strip().lower().startswith("date started"):
                value = metadata_sheet.cell(row=cell.row, column=cell.column + 1).value
                return parse_date_value(value)

    raise ValueError("'Date Started' label not found on metadata tab")

def parse_date_value(value) -> date:
    """Converts a cell value into a date, handling real Excel dates and date-like text."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    raise ValueError(f"could not parse date from: {value!r}")

def compute_block_start_dates(all_blocks: list[dict], date_started: date) -> None:
    """Attaches 'start_date' to each block. Blocks run back-to-back in whole
    Mon-Sun weeks, so each block starts (weeks in previous block) * 7 days after the last."""
    if date_started.weekday() != 0:  # weekday() returns 0 for Monday
        raise ValueError(f"Date Started {date_started} is not a Monday")

    block_start = date_started
    for block in all_blocks:
        block["start_date"] = block_start
        block_length_weeks = max((w["week_number"] for w in block["weeks"]), default=0)
        block_start += timedelta(weeks=block_length_weeks)

def find_short_weeks(all_blocks: list[dict], expected_days: int = 4) -> None:
    """Prints every week whose day count differs from expected_days."""
    for block in all_blocks:
        for week in block["weeks"]:
            day_count = len(week["days"])
            if day_count != expected_days:
                print(block["block_number"], block["tab_name"], "week", week["week_number"], "-", day_count, "days")

def compute_week_date_ranges(all_blocks: list[dict]) -> None:
    """Attaches week_start date and week_end_date to each week, using the block's
    start date and the week's position within its block."""
    for block in all_blocks:
        for week in block["weeks"]:
            week_start = block["start_date"] + timedelta(weeks=week["week_number"] - 1)
            week["week_start_date"] = week_start
            week["week_end_date"] = week_start + timedelta(days=6)

# endregion Stage 5: Date Derivation

#region Stage 6: API Payloads
def build_session_payloads(clean_records: list[dict], program_week_ids: dict) -> list[dict]:
    """Groups flat clean records into nested sessions for POST /sessions/batch.
    program_week_ids maps (block_number, week_number) -> program_week_id."""
    sessions = {}  # (client_id, block, week, day) -> session payload

    for record in clean_records:
        key = (record["client_id"], record["block_number"], record["week_number"], record["day_number"])

        if key not in sessions:
            week_key = (record["block_number"], record["week_number"])
            if week_key not in program_week_ids:
                raise ValueError(f"no program_week_id for block/week {week_key}")
            sessions[key] = {
                "client_id": record["client_id"],
                "program_week_id": program_week_ids[week_key],
                "day_number": record["day_number"],
                "exercises": {},
            }

        exercises = sessions[key]["exercises"]
        name = record["exercise_name"].strip()
        if name.lower() not in exercises:
            exercises[name.lower()] = {"exercise_name": name, "sets": []}

        for new_set in expand_sets(record):
            new_set["set_number"] = len(exercises[name.lower()]["sets"]) + 1
            exercises[name.lower()]["sets"].append(new_set)

    payloads = []
    for session in sessions.values():
        session["exercises"] = list(session["exercises"].values())
        payloads.append(session)
    return payloads

def expand_sets(record: dict) -> list[dict]:
    """The one place that decides how a row like '2x6' becomes sets.
    Currently: num_sets identical sets, each with the row's load and RPE."""
    return [
        {
            "reps": record["reps"],
            "weight_value": record["actual_load"],
            "weight_unit": None,
            "rpe": record["actual_rpe"],
            "set_type": None, # labels dropped for now; the CHECK constraint allows null
            "notes": record["notes"],
            "prescribed_rpe": record["prescribed_rpe"],
            "prescribed_backoff_pct": record["prescribed_backoff_pct"],
        }
        for _ in range(record["num_sets"])
    ]

def parse_sets_x_reps(value) -> tuple[int, int]:
    """Splits '2x6' into (2, 6). Raises ValueError if it doesn't match."""
    if not isinstance(value, str):
        raise ValueError(f"sets_x_reps is not text: {value!r}")
    match = SETS_REPS_PATTERN.match(value.strip())
    if match is None:
        raise ValueError(f"sets_x_reps not parseable: {value!r}")
    return int(match.group(1)), int(match.group(2))

def get_program_week_ids(all_blocks: list[dict], client_id: str) -> dict:
    """Calls POST /program-weeks once per (block, week) and returns
    {(block_number, week_number): program_week_id}."""
    ids = {}
    for block in all_blocks:
        for week in block["weeks"]:
            response = requests.post(f"{API_URL}/program-weeks", json={
                "client_id": client_id,
                "block": block["block_number"],
                "week": week["week_number"],
                "week_start_date": week["week_start_date"].isoformat(),
                "week_end_date": week["week_end_date"].isoformat(),
            })
            response.raise_for_status()
            ids[(block["block_number"], week["week_number"])] = response.json()["program_week_id"]
    return ids

def send_payloads(payloads: list[dict], chunk_size: int = 10, max_failed_chunks: int = 2) -> list[dict]:
    """Posts sessions to /sessions/batch in chunks. Stops if whole chunks keep failing,
    which usually means the backend can't reach Supabase."""
    results = []
    failed_chunks = 0

    for i in range(0, len(payloads), chunk_size):
        chunk = payloads[i:i + chunk_size]
        try:
            response = requests.post(f"{API_URL}/sessions/batch", json={"sessions": chunk}, timeout=120)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(
                f"Stopped at session {i}: {len(results)} sessions confirmed sent. Cause: {e}"
            ) from e
        
        chunk_results = response.json()["results"]
        results.extend(chunk_results)
        print(f"sent {min(i + chunk_size, len(payloads))}/{len(payloads)}")

        if all(r["status"] == "error" for r in chunk_results):
            failed_chunks += 1
            if failed_chunks >= max_failed_chunks:
                raise RuntimeError(
                    f"Stopped after {len(results)} sessions: {max_failed_chunks} chunks in a row "
                    f"failed completely. Last error: {chunk_results[0]['detail']}"
                )
        else:
            failed_chunks = 0

    return results

# endregion Stage 6: API Payloads

DRY_RUN = False   # add this near the top of the file with your other constants
                 # True = parse and check only, writes nothing. False = real run.

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python pipeline.py <client_id>")
    client_id = sys.argv[1]  
    wb = load_client_workbook("Jon Program.xlsx")
    all_blocks = build_all_blocks(wb)
    compute_block_start_dates(all_blocks, find_date_started(wb))
    compute_week_date_ranges(all_blocks)
    raw_rows = extract_all_exercises(wb, all_blocks, client_id)
    clean, rejected, unlogged = process_all_exercises(raw_rows)
    print(f"{len(clean)} clean, {len(rejected)} rejected, {len(unlogged)} unlogged")

    if DRY_RUN:
        print(Counter(r["prescribed_raw"].strftime("%m/%d")
                for r in raw_rows
                if isinstance(r["prescribed_raw"], datetime) and r["actual_load_raw"] is not None)) 
        # What kind of value sits in the prescribed cell, for rows that have a logged load
        print(sum(r["num_sets"] for r in clean if r["prescribed_rpe"] is not None), "sets should have a prescribed RPE")
        print(Counter(type(r["prescribed_raw"]).__name__ for r in raw_rows if r["actual_load_raw"] is not None))
        raise SystemExit   # stops here, before any API calls 

    week_ids = get_program_week_ids(all_blocks, client_id)
    payloads = build_session_payloads(clean, week_ids)
    print(len(payloads), "sessions built")

    t0 = time.time()
    results = send_payloads(payloads)
    print(f"{time.time() - t0:.0f}s total")

    errors = [r for r in results if r["status"] == "error"]
    failed_ex = [e for r in results if r["status"] == "ok" for e in r.get("failed_exercises", [])]
    rejected_ex = [e for r in results if r["status"] == "ok" for e in r["rejected_exercises"]]
    print(len(results), "sent,", len(errors), "errors,", len(failed_ex), "exercises failed,", len(rejected_ex), "exercises rejected")
    print(Counter(e["exercise_name"] for e in rejected_ex).most_common())
    for e in failed_ex[:5]:
        print(e["exercise_name"], e["reason"][:200])
    for r in errors[:5]:
        print(r["detail"])

    expected = sum(len(e["sets"]) for s in payloads for e in s["exercises"])
    print(expected, "sets expected")