# Mongolian Monthly Workforce Star-Schema Pipeline

This application loads the exact 14-column Mongolian month-end employee file into an immutable workforce snapshot model, compares consecutive months, and creates workforce-flow and position/grade movement facts for Power BI.

## Model

**Dimensions:** `Dim_Employee`, `Dim_Department`, `Dim_Position`, `Dim_Grade`, `Dim_Employment_Type`, `Dim_Employee_Status`, `Dim_Movement_Type`, `Dim_Movement_Scenario`, and `Dim_Date`.

**Facts:**

* `Fact_Employee_Snapshot`: one employee per month end; unique business key `EmployeeKey + SnapshotDateKey`. Every accepted source employee is included, even unchanged employees.
* `Fact_Workforce_Flow`: one detected status/new-hire movement event per employee.
* `Fact_Position_Grade_Movement`: one employee comparison when department, position, grade, or employment type changed.

The first month is a baseline and creates snapshot facts only. Later months compare with the latest prior snapshot. Existing historical snapshot rows are never updated, and the same file/month hash is skipped.

## Exact input schema

The `Data` worksheet must contain exactly: `Код`, `Нэр`, `Овог`, `Албан тушаалын нэр`, `Хэлтэс тасаг`, `Ажилд орсон огноо`, `Ажилласан жил`, `Ажилласан сар`, `Ажилтны төлөв`, `Ажилтны төрөл`, `Албан тушаалын зэрэглэл`, `Ажлаас гарсан огноо`, `Хүйс`, `Нас`.

The complete source-to-target mapping, grade ranks/groups, status flags, movement codes, and movement scenarios are centralized in `config.py`. **Before first use**, confirm `SOURCE_SHEET`, `GRADE_RANK`, `GRADE_GROUPS`, and `STATUS_RULES` match your organization's real values. Unknown grade ranks are not guessed: changed unknown grades become `Requires Review`.

Grade codes normalize confusable Cyrillic letters (for example `А` → `A` and `В` → `B`) before rank lookup.

## Windows installation

Install 64-bit Python 3.10+ and select **Add Python to PATH**. In Command Prompt:

```bat
cd /d C:\Users\YourName\Documents\excel_data_pipeline
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Place one `.xlsx` or Excel 97–2003 `.xls` file directly in:

```text
C:\Users\YourName\Documents\excel_data_pipeline\input\
```

Close the workbook in Excel. Run with the required month-end date:

```bat
.venv\Scripts\python.exe main.py --snapshot-date 2026-08-31
```

The date must be the last calendar day of the month. If `--snapshot-date` is omitted, the program prompts for it interactively. Excel temporary files beginning `~$` are ignored.

### Safe dry-run preview

Before committing a month, run:

```bat
.venv\Scripts\python.exe main.py --snapshot-date 2026-08-31 --dry-run
```

Dry-run reads the real workbook, validates and cleans all 14 columns, detects duplicate
employee codes, reports unknown grade ranks and statuses, lists rejected rows, previews
new dimension members, and reconciles snapshot, workforce-flow, and position/grade
movement counts. It does not back up, write, append, replace, or otherwise modify any
master or fact workbook. A normal run is still required to commit the month.

## Outputs and safety

Missing `input`, `master`, `archive`, `rejected`, and `logs` folders are created automatically. The successful first load creates one `.xlsx` file per dimension/fact plus `Load_History.xlsx` in `master`. Rejected records are written to `rejected`, logs to `logs`, and existing masters are copied to a timestamped `archive` folder before replacement.

Processing occurs in memory. Output workbooks are staged and verified before atomic replacement. A bad schema, invalid snapshot date, duplicate month, backward historical load, or failed save leaves existing master files unchanged. Duplicate `Код` values within one monthly file are rejected rather than arbitrarily selected.

## Detection rules

* New employee → `MEE000001`.
* Active after terminated → rehire `MEE000003`.
* Transition to terminated → `MEE000002`.
* Transition to maternity/long sick leave → `MEE000005`/`MEE000006`.
* Return from maternity/long sick leave → `MEE000007`/`MEE000008`.
* Department, position, grade, and employment-type changes create a position/grade movement only when at least one relevant value changed.
* Position plus grade-rank increase/decrease yields Promotion/Demotion (large changes yield Fast Track Promotion/Major Downgrade); grade-only change yields Grade Promotion/Grade Downgrade; department and position combinations yield organizational/functional scenarios; missing rank yields Requires Review.

The configured movement catalog also reserves `MEE000004` for validated external-transfer events. The source has no explicit movement/event column, so it is not auto-inferred merely from a department change.

## Tests

```bat
.venv\Scripts\python.exe -m pytest -q
```

Tests cover the Mongolian schema, baseline/second snapshots, unchanged staff, new hire, termination, rehire, both leave/return pairs, department/position/grade changes, promotion/demotion, unknown ranks, Cyrillic normalization, duplicate employee codes, replay idempotency, immutable history, transaction safety, folder creation, and the CLI.
