"""Business rules for the month-end workforce star schema."""
from __future__ import annotations
import pandas as pd

AUDIT = ["SourceFile", "LoadID", "LoadedDateTime"]

def normalize_grade(value, cfg):
    if pd.isna(value): return pd.NA
    return str(value).strip().upper().translate(cfg.GRADE_NORMALIZATION).replace(" ", "")

def status_flags(value, cfg):
    return cfg.STATUS_RULES.get(value, (0, 1))

def static_dimensions(cfg):
    movements = []
    for i, (code, (name, category, flow, hc, active)) in enumerate(cfg.MOVEMENT_TYPES.items(), 1):
        movements.append([i, code, name, category, flow, hc, active])
    scenarios = [[i, name] for i, name in enumerate(cfg.MOVEMENT_SCENARIOS, 1)]
    return {
      "Dim_Movement_Type": pd.DataFrame(movements, columns=["MovementTypeKey", "MovementCode", "MovementName", "MovementCategory", "FlowValue", "EmploymentHCImpact", "ActiveWorkforceImpact"]),
      "Dim_Movement_Scenario": pd.DataFrame(scenarios, columns=["MovementScenarioKey", "MovementScenarioName"]),
    }

def upsert_dimension(source, master, name_col, key_col, extra=None):
    """SCD1 reference dimension with stable sequential key."""
    values = source[name_col].dropna().drop_duplicates().reset_index(drop=True)
    if master.empty:
        master = pd.DataFrame(columns=[key_col, name_col, *(extra or [])])
    missing = values[~values.isin(master[name_col])]
    if len(missing):
        start = int(pd.to_numeric(master[key_col], errors="coerce").max()) + 1 if len(master) else 1
        new = pd.DataFrame({key_col: range(start, start + len(missing)), name_col: missing.values})
        for col in extra or []: new[col] = True
        master = pd.concat([master, new], ignore_index=True)
    return master

def classify_scenario(old, new):
    dept, pos, grade = old.DepartmentKey != new.DepartmentKey, old.PositionKey != new.PositionKey, old.GradeKey != new.GradeKey
    if grade and (pd.isna(old.GradeRank) or pd.isna(new.GradeRank)): return "Requires Review", "REVIEW"
    diff = (new.GradeRank - old.GradeRank) if grade else 0
    if pos and diff >= 2: return "Fast Track Promotion", "HIGH"
    if pos and diff > 0: return "Promotion", "HIGH"
    if pos and diff < -1: return "Major Downgrade", "HIGH"
    if pos and diff < 0: return "Demotion", "HIGH"
    if grade and diff > 0: return "Grade Promotion", "HIGH"
    if grade and diff < 0: return "Grade Downgrade", "HIGH"
    if dept and pos: return "Functional Transfer", "HIGH"
    if dept: return "Organizational Transfer", "HIGH"
    if pos: return "Position Reclassification", "HIGH"
    return "Lateral Transfer", "HIGH"

def movement_code(old_status, new_status, is_new):
    active = {"Ажиллаж байгаа", "Идэвхтэй"}
    if is_new: return "MEE000001"
    if new_status == "Ажлаас гарсан" and old_status != new_status: return "MEE000002"
    if old_status == "Ажлаас гарсан" and new_status in active: return "MEE000003"
    if new_status == "Жирэмсний амралт" and old_status != new_status: return "MEE000005"
    if new_status == "Уртын өвчтэй" and old_status != new_status: return "MEE000006"
    if old_status == "Жирэмсний амралт" and new_status in active: return "MEE000007"
    if old_status == "Уртын өвчтэй" and new_status in active: return "MEE000008"
    return None

