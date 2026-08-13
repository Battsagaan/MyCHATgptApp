"""Central configuration for the Mongolian month-end workforce model."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INPUT_FOLDER, MASTER_FOLDER = BASE_DIR / "input", BASE_DIR / "master"
ARCHIVE_FOLDER, REJECTED_FOLDER, LOG_FOLDER = BASE_DIR / "archive", BASE_DIR / "rejected", BASE_DIR / "logs"
SOURCE_SHEET = "Data"
PROCESS_ALL_FILES = True
SKIP_PREVIOUSLY_SUCCESSFUL_HASHES = True
ALLOW_UNEXPECTED_COLUMNS = False

EXPECTED_COLUMNS = ["Код", "Нэр", "Овог", "Албан тушаалын нэр", "Хэлтэс тасаг",
    "Ажилд орсон огноо", "Ажилласан жил", "Ажилласан сар", "Ажилтны төлөв",
    "Ажилтны төрөл", "Албан тушаалын зэрэглэл", "Ажлаас гарсан огноо", "Хүйс", "Нас"]
REQUIRED_COLUMNS = ["Код", "Нэр", "Овог", "Албан тушаалын нэр", "Хэлтэс тасаг",
                    "Ажилд орсон огноо", "Ажилтны төлөв", "Ажилтны төрөл"]
SOURCE_COLUMN_MAPPING = {"Код": "EmployeeCode", "Нэр": "FirstName", "Овог": "LastName",
    "Албан тушаалын нэр": "Position", "Хэлтэс тасаг": "Department",
    "Ажилд орсон огноо": "HireDate", "Ажилласан жил": "TenureYearsSource",
    "Ажилласан сар": "TenureMonthsSource", "Ажилтны төлөв": "EmployeeStatus",
    "Ажилтны төрөл": "EmploymentType", "Албан тушаалын зэрэглэл": "Grade",
    "Ажлаас гарсан огноо": "TerminationDate", "Хүйс": "Gender", "Нас": "AgeSnapshot"}
TEXT_COLUMNS = ["Код", "Нэр", "Овог", "Албан тушаалын нэр", "Хэлтэс тасаг", "Ажилтны төлөв",
                "Ажилтны төрөл", "Албан тушаалын зэрэглэл", "Хүйс"]
ID_COLUMNS = ["Код"]
DATE_COLUMNS = ["Ажилд орсон огноо", "Ажлаас гарсан огноо"]
NUMERIC_COLUMNS = ["Ажилласан жил", "Ажилласан сар", "Нас"]

# Normalize visually confusable Cyrillic grade letters before lookup.
GRADE_NORMALIZATION = str.maketrans({"А": "A", "В": "B", "С": "C", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "Т": "T", "Х": "X"})
GRADE_RANK = {"A1": 1, "A2": 2, "A3": 3, "B1": 4, "B2": 5, "B3": 6, "C1": 7, "C2": 8, "C3": 9}
GRADE_GROUPS = {"A": "Entry", "B": "Professional", "C": "Leadership"}

# Names are configurable because organizations use different Mongolian status labels.
STATUS_RULES = {
    "Ажиллаж байгаа": (1, 1), "Идэвхтэй": (1, 1), "Ажлаас гарсан": (0, 0),
    "Жирэмсний амралт": (0, 1), "Уртын өвчтэй": (0, 1),
}
MOVEMENT_TYPES = {
 "MEE000001": ("Шинээр ажилд орж байгаа", "Entry", 1, 1, 1),
 "MEE000002": ("Ажлаас гарсан", "Exit", -1, -1, -1),
 "MEE000003": ("Дахин орж байгаа", "Entry", 1, 1, 1),
 "MEE000004": ("Гадаад шилжилт", "Transfer", 0, 0, 0),
 "MEE000005": ("Жирэмсний амралт", "Leave", 0, 0, -1),
 "MEE000006": ("Уртын өвчтэй", "Leave", 0, 0, -1),
 "MEE000007": ("Жирэмсний амралтаас ажилд орсон", "Return", 0, 0, 1),
 "MEE000008": ("Уртын өвчнөөс буцаж ирсэн", "Return", 0, 0, 1),
}
MOVEMENT_SCENARIOS = ["Grade Promotion", "Grade Downgrade", "Lateral Transfer", "Promotion",
 "Demotion", "Organizational Transfer", "Position Reclassification", "Fast Track Promotion",
 "Major Downgrade", "Career Progression", "Functional Transfer", "Requires Review"]
DATE_START, DATE_END = "2020-01-01", "2035-12-31"
LOAD_HISTORY_FILE = "Load_History.xlsx"
LOAD_HISTORY_COLUMNS = ["Load_ID", "File_Name", "File_Size", "File_Modified_Date", "File_Hash",
 "SnapshotDateKey", "Load_Date", "Rows_Processed", "Rows_Accepted", "Rows_Rejected", "Status"]
