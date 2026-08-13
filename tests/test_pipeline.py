from pathlib import Path
from types import SimpleNamespace
import pandas as pd
import pytest
import config as base
from pipeline.runner import run_file
from pipeline.storage import write_excel_table
from pipeline.exceptions import MissingColumnError

def cfg(tmp_path: Path):
    values = {name: getattr(base, name) for name in dir(base) if name.isupper()}
    values.update({"INPUT_FOLDER": tmp_path / "input", "MASTER_FOLDER": tmp_path / "master",
                   "ARCHIVE_FOLDER": tmp_path / "archive", "REJECTED_FOLDER": tmp_path / "rejected",
                   "LOG_FOLDER": tmp_path / "logs"})
    for p in values.values():
        if isinstance(p, Path):
            p.mkdir(parents=True, exist_ok=True) if not p.suffix else None
    return SimpleNamespace(**values)

def rows(count=100):
    n = pd.Series(range(1, count + 1))
    return pd.DataFrame({"Emp_ID": n.map(lambda x: f"{x:06d}"), "Employee_Name": "Нэр",
        "Department": "Mining", "Position": "Operator", "Employment_Type": "Full Time",
        "Event_Date": pd.Timestamp("2026-08-13") + pd.to_timedelta(n, unit="D"),
        "Movement_Type": "Hire", "Hours": 8, "Amount": 100, "Status": "Active"})

def source(c, frame, name="source.xlsx"):
    path = c.INPUT_FOLDER / name
    write_excel_table(frame, path, "Source")
    return path

def read(c, name):
    return pd.read_excel(c.MASTER_FOLDER / f"{name}.xlsx")

def test_first_load_and_same_hash_skip(tmp_path):
    c = cfg(tmp_path); path = source(c, rows())
    first = run_file(path, c)
    assert first["facts"]["Fact_HR"]["new"] == 100
    assert len(read(c, "Fact_HR")) == 100
    assert run_file(path, c)["status"] == "SKIPPED"

def test_new_employee_existing_employee_scd1_and_department(tmp_path):
    c = cfg(tmp_path); run_file(source(c, rows(1), "one.xlsx"), c)
    employee_key = read(c, "Dim_Employee").iloc[0].Employee_Key
    changed = rows(2); changed.loc[0, "Employee_Name"] = "Шинэ нэр"; changed.loc[1, "Department"] = "Safety"
    result = run_file(source(c, changed, "two.xlsx"), c)
    employees = read(c, "Dim_Employee")
    assert employees.loc[employees.Emp_ID.astype(str).str.zfill(6).eq("000001"), "Employee_Key"].iloc[0] == employee_key
    assert employees.loc[employees.Emp_ID.astype(str).str.zfill(6).eq("000001"), "Employee_Name"].iloc[0] == "Шинэ нэр"
    assert result["dimensions"]["Dim_Employee"] == {"new": 1, "updated": 1, "existing": 0}
    assert "Safety" in set(read(c, "Dim_Department").Department)
    facts = read(c, "Fact_HR"); safety_key = read(c, "Dim_Department").set_index("Department").loc["Safety", "Department_Key"]
    assert safety_key in set(facts.Department_Key)

def test_invalid_row_rejected_and_not_loaded(tmp_path):
    c = cfg(tmp_path); frame = rows(2); frame.loc[1, "Emp_ID"] = None
    result = run_file(source(c, frame), c)
    assert result["rejected"] == 1
    assert len(read(c, "Fact_HR")) == 1
    rejected = pd.read_excel(result["rejected_path"])
    assert "Missing Emp_ID" in rejected.iloc[0].Error_Reason

def test_broken_structure_preserves_master(tmp_path):
    c = cfg(tmp_path); run_file(source(c, rows(1), "good.xlsx"), c)
    before = (c.MASTER_FOLDER / "Fact_HR.xlsx").read_bytes()
    broken = rows(1).drop(columns="Event_Date")
    with pytest.raises(MissingColumnError):
        run_file(source(c, broken, "broken.xlsx"), c)
    assert (c.MASTER_FOLDER / "Fact_HR.xlsx").read_bytes() == before

def test_duplicate_fact_key_in_different_file_is_skipped(tmp_path):
    c = cfg(tmp_path); frame = rows(1)
    run_file(source(c, frame, "a.xlsx"), c)
    result = run_file(source(c, frame, "b.xlsx"), c)
    assert result["facts"]["Fact_HR"] == {"new": 0, "duplicates": 1}
    assert len(read(c, "Fact_HR")) == 1

