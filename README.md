# Excel HR Star-Schema Pipeline

This application turns repeatable HR Excel extracts into persistent, Power BI-ready
dimension and fact workbooks. It validates structure and values, rejects bad rows with
reasons, preserves surrogate keys, applies SCD Type 1 updates, prevents duplicate facts,
backs up masters, and commits verified workbooks transactionally.

## Agreed design and assumptions

No real source workbook was supplied, so version 1 uses **only the ten headers explicitly
provided in the request**. Change mappings in `config.py` when the real standardized
workbook differs; business names are not embedded in processing code.

### Architecture

```text
main.py -> pipeline.runner (orchestration)
                   |-> storage.py (Excel adapter, backups, atomic commit)
                   |-> cleaning.py / validation.py (quality boundary)
                   |-> dimensions.py / facts.py (storage-independent rules)
                   |-> logging_setup.py (file + terminal audit)
config.py ---------+ (all mappings and business rules)
```

Folders are `input/`, `master/`, `archive/`, `rejected/`, and `logs/`. Excel persistence
is isolated in `storage.py`, so a future SQL repository can replace that adapter while
retaining transformation logic.

### Star schema and keys

| Target | Grain / business key | Surrogate key | Source mapping |
|---|---|---|---|
| `Dim_Employee` | `Emp_ID` | `Employee_Key` | `Emp_ID`, `Employee_Name`, `Employment_Type`, `Status` |
| `Dim_Department` | `Department` | `Department_Key` | `Department` |
| `Dim_Position` | `Position` | `Position_Key` | `Position` |
| `Dim_Date` | one row per `Date` | `Date_Key` (`YYYYMMDD`) | generated from configured range |
| `Fact_HR` | `Employee_Key`, `Event_Date`, `Movement_Type` | `Fact_Key` | dimension keys plus `Event_Date`, `Movement_Type`, `Hours`, `Amount` |

`Fact_HR` contains `Employee_Key`, `Department_Key`, `Position_Key`, and `Date_Key`,
forming one-to-many relationships from each dimension. It also contains source filename,
physical Excel row, load timestamp, and load ID for traceability.

Assumptions:

* Worksheet name is `Data`; the first row contains headers.
* A fact represents one employee movement type on one event date. If multiple legitimate
  events can share this grain, expand the configured fact business key with an event ID.
* Ambiguous slash dates are interpreted day-first; unambiguous U.S. dates are retried.
* A numeric Excel cell cannot preserve a zero-prefix Excel discarded before Python reads
  it. Store IDs as Excel text to retain leading zeroes; text IDs are preserved exactly.
* Dimension attributes use the last valid incoming record per business key. SCD Type 1
  overwrites changed non-key attributes, retains the surrogate and `Created_Date`, and
  advances `Updated_Date`. The processor boundary permits a later Type 2 implementation.
* Duplicate strategy defaults to `skip`. Duplicate keys inside a source and against the
  master are omitted; `update` replaces matching fact attributes, and `error` aborts.
* A successful file hash is skipped before transformation. A different file with an
  already-loaded fact grain is still protected by the fact business key.

## Install and run

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/).
2. Create and activate a virtual environment.
3. Install dependencies: `python -m pip install -r requirements.txt`.
4. Put one or more `.xlsx` files in `input/`, each with a `Data` worksheet.
5. Run `python main.py`.

For a demonstration source containing 100 rows, run `python generate_sample.py` first.
The first run automatically creates all master workbooks and `Load_History.xlsx`.

## Configuration

Edit only `config.py` for folder locations, source sheet, expected/required/text/date/
numeric columns, mappings, keys, date range, SCD mode, and duplicate behavior. Unexpected
columns are fatal by default because structural drift must not be silent.

To add a dimension:

1. Add a `DIMENSION_CONFIG` entry with `surrogate_key`, `business_key`, and `columns`.
2. Add its lookup in the fact's `dimension_references` using source key(s) and foreign key.
3. Add the foreign key to the fact's `columns` and business key only if it defines grain.

To add another fact table, add a `FACT_CONFIG` entry with its stable schema, grain, and
dimension references. The current orchestrator processes configured facts uniformly.

## Outputs and operational behavior

* `master/`: stable Power BI tables (one header row, typed values, filters, frozen headers,
  Excel tables, no merged cells).
* `rejected/`: timestamped rejected rows containing `Validation_Status`, all accumulated
  `Error_Reason` values, source file, and physical source row.
* `archive/`: timestamped copy of existing masters immediately before each commit.
* `logs/`: per-load detailed log and ETL summary.
* `master/Load_History.xlsx`: hashes and row/status metrics for successful committed loads.

All transformation happens in memory. Every final dimension key, business key, fact key,
required field, and foreign key is checked. Workbooks are written to a staging directory,
read back for verification, and only then atomically replace their corresponding masters.
A schema, transformation, or integrity failure therefore leaves current masters unchanged.

## Troubleshooting

* **No input files**: place an `.xlsx` file directly in `input/`.
* **Missing worksheet**: rename the worksheet to `Data` or edit `SOURCE_SHEET`.
* **Missing/unexpected/duplicate headers**: correct the extract or intentionally update
  configuration. The log lists every mismatch.
* **Rejected values**: inspect the timestamped rejected workbook and its `Error_Reason`.
* **File was skipped**: its SHA-256 already has a successful load-history record. This is
  expected idempotency; disable hash skipping only when deliberately re-evaluating it.
* **Duplicate fact error**: either fix the source grain, expand the business key, or choose
  the configured `skip`/`update` policy.
* **Master integrity failure**: restore from the latest `archive/` folder and do not edit
  surrogate/business keys manually.

## Tests

Run `python -m pytest`. The suite covers first load (100 facts), same-file idempotency,
new and existing employees, SCD Type 1 changes, invalid-row rejection, new-department key
resolution, cross-file fact duplicate protection, and broken-schema transaction safety.

