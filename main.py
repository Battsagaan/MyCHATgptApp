"""Business-user entry point: run with ``python main.py``."""
from pipeline.runner import run_all

if __name__ == "__main__":
    print("HR DATA PIPELINE\n" + "=" * 30)
    results = run_all()
    print(f"Completed {sum(r['status'] == 'SUCCESS' for r in results)} file(s); "
          f"skipped {sum(r['status'] == 'SKIPPED' for r in results)} file(s).")

