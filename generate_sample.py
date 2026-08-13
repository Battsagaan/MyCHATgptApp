"""Generate a deterministic 100-row source workbook for evaluation or demos."""
from pathlib import Path
import pandas as pd
import config
from pipeline.storage import write_excel_table

def generate(path: Path = config.INPUT_FOLDER / "HR_sample_100.xlsx", rows: int = 100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    numbers = pd.Series(range(1, rows + 1))
    frame = pd.DataFrame({
        "Emp_ID": numbers.map(lambda n: f"{n:06d}"),
        "Employee_Name": numbers.map(lambda n: f"Ажилтан {n}"),
        "Department": numbers.map(lambda n: ["Mining", "Finance", "HR"][n % 3]),
        "Position": numbers.map(lambda n: ["Operator", "Analyst", "Manager"][n % 3]),
        "Employment_Type": "Full Time", "Event_Date": pd.Timestamp("2026-08-13"),
        "Movement_Type": "Snapshot", "Hours": 8.0, "Amount": numbers * 100.0,
        "Status": "Active",
    })
    write_excel_table(frame, path, "SourceData")
    return path

if __name__ == "__main__":
    print(generate())

