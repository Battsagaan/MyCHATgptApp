"""Windows-friendly command line for the month-end workforce pipeline."""
import argparse
import sys
from pipeline.runner import run_all, validate_snapshot_date

def main(argv=None):
    parser=argparse.ArgumentParser(description="Load a month-end employee snapshot")
    parser.add_argument("--snapshot-date", help="Required month-end date, e.g. 2026-08-31")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview without modifying master data")
    args=parser.parse_args(argv)
    value=args.snapshot_date or input("Snapshot date (YYYY-MM-DD, month end): ").strip()
    try:
        validate_snapshot_date(value); results=run_all(value, dry_run=args.dry_run)
    except Exception as exc:
        print(f"PROCESS FAILED: {exc}",file=sys.stderr); return 1
    if args.dry_run:
        print("\n" + "="*60 + "\nDRY-RUN RECONCILIATION SUMMARY\n" + "="*60)
        for result in results:
            print(f"Source rows: {result['source_rows']:,}\nAccepted rows: {result['accepted']:,}\nRejected rows: {result['rejected']:,}")
            if result["rejected_rows"]:
                print("Rejected row details:")
                for row in result["rejected_rows"]: print(f"  - {row}")
            print("New dimension members:")
            for name,count in result["dimension_changes"].items(): print(f"  {name}: {count:,}")
            print(f"Snapshot rows to add: {result['snapshot_rows']:,}\nWorkforce movements to add: {result['workforce_movements']:,}\nPosition/grade movements to add: {result['position_grade_movements']:,}")
            print(f"Unknown grades requiring review: {result['unknown_grades'] or 'None'}\nUnknown statuses requiring configuration review: {result['unknown_statuses'] or 'None'}")
        print("NO MASTER OR FACT FILES WERE MODIFIED.\n" + "="*60)
    else:
        print(f"Completed {sum(r['status']=='SUCCESS' for r in results)}; skipped {sum(r['status']=='SKIPPED' for r in results)}")
    return 0

if __name__ == "__main__": raise SystemExit(main())
