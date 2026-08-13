"""Central business and storage configuration for the HR star-schema pipeline."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INPUT_FOLDER = BASE_DIR / "input"
MASTER_FOLDER = BASE_DIR / "master"
ARCHIVE_FOLDER = BASE_DIR / "archive"
REJECTED_FOLDER = BASE_DIR / "rejected"
LOG_FOLDER = BASE_DIR / "logs"

SOURCE_SHEET = "Data"
PROCESS_ALL_FILES = True
SKIP_PREVIOUSLY_SUCCESSFUL_HASHES = True
DUPLICATE_STRATEGY = "skip"  # skip, update, error
SCD_TYPE = 1

EXPECTED_COLUMNS = [
    "Emp_ID", "Employee_Name", "Department", "Position", "Employment_Type",
    "Event_Date", "Movement_Type", "Hours", "Amount", "Status",
]
REQUIRED_COLUMNS = ["Emp_ID", "Department", "Position", "Event_Date", "Movement_Type"]
TEXT_COLUMNS = [
    "Emp_ID", "Employee_Name", "Department", "Position", "Employment_Type",
    "Movement_Type", "Status",
]
ID_COLUMNS = ["Emp_ID"]
DATE_COLUMNS = ["Event_Date"]
NUMERIC_COLUMNS = ["Hours", "Amount"]
ALLOW_UNEXPECTED_COLUMNS = False

DIMENSION_CONFIG = {
    "Dim_Employee": {
        "surrogate_key": "Employee_Key",
        "business_key": ["Emp_ID"],
        "columns": ["Emp_ID", "Employee_Name", "Employment_Type", "Status"],
    },
    "Dim_Department": {
        "surrogate_key": "Department_Key",
        "business_key": ["Department"],
        "columns": ["Department"],
    },
    "Dim_Position": {
        "surrogate_key": "Position_Key",
        "business_key": ["Position"],
        "columns": ["Position"],
    },
}

FACT_CONFIG = {
    "Fact_HR": {
        "surrogate_key": "Fact_Key",
        "business_key": ["Employee_Key", "Event_Date", "Movement_Type"],
        "columns": [
            "Employee_Key", "Department_Key", "Position_Key", "Date_Key",
            "Event_Date", "Movement_Type", "Hours", "Amount",
        ],
        "dimension_references": {
            "Dim_Employee": {"source_key": ["Emp_ID"], "foreign_key": "Employee_Key"},
            "Dim_Department": {"source_key": ["Department"], "foreign_key": "Department_Key"},
            "Dim_Position": {"source_key": ["Position"], "foreign_key": "Position_Key"},
        },
    }
}

ENABLE_DATE_DIMENSION = True
DATE_START = "2020-01-01"
DATE_END = "2035-12-31"
LOAD_HISTORY_FILE = "Load_History.xlsx"

AUDIT_COLUMNS = ["Source_File", "Source_Row_Number", "Load_Date", "Load_ID"]
LOAD_HISTORY_COLUMNS = [
    "Load_ID", "File_Name", "File_Size", "File_Modified_Date", "File_Hash",
    "Load_Date", "Rows_Processed", "Rows_Accepted", "Rows_Rejected", "Status",
]

