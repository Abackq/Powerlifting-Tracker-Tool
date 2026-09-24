from openpyxl import load_workbook
import re

WEEK_PATTERN = re.compile(r"Week\s+(\d+)$", re.IGNORECASE)
DAY_PATTERN = re.compile(r"Day\s+(\d+)$", re.IGNORECASE)

def load_client_workbook(filepath: str):
    workbook = load_workbook(filepath, read_only=True, data_only=True)
    return workbook

def get_block_tabs(workbook, metadata_tab_name: str = "READ ME") -> list[str]:
    "Returns tab names in order, excluding metadata tabs, preserving order for block numbering"
    return [name for name in workbook.sheetnames if name != metadata_tab_name]

def print_sheet_grid(workbook, sheet_name: str):
    """Prints every non-empty cell's row, column, and value for a given sheet.
    Useful for visually inspecting layout before writing detection logic."""
    sheet = workbook[sheet_name]
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value is not None:
                print(f"row={cell.row}, col={cell.column}, value={cell.value!r}")

def find_week_columns(sheet) -> list[dict]:
    "Scans the sheet for 'Week N' labels and returns their row column, and week number."
    weeks = []
    for row in sheet.iter_rows():
        for cell in row:
            if isinstance(cell.value, str):
                match = WEEK_PATTERN.match(cell.value.strip())
                if match:
                    weeks.append({
                        "week_number": int(match.group(1)),
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

if __name__ == "__main__":
    wb = load_client_workbook("Jon Program.xlsx")
    all_blocks = build_all_blocks(wb)
    print(f"Found {len(all_blocks)} blocks")
    print(all_blocks[0])

    # INDIVIDUAL FUNCTION TESTS
    # -----------------------------------------------------------------------------
    # block_tabs = get_block_tabs(wb)
    # print(block_tabs)
    # print_sheet_grid(wb, block_tabs[0]) # inspect the first block tab
    # weeks = find_week_columns(wb[block_tabs[0]])
    # days = find_day_rows(wb[block_tabs[0]], weeks[0])
    # structure = build_week_day_structure(wb[block_tabs[0]])
    