from pathlib import Path
from types import SimpleNamespace
import shutil, subprocess, sys
import pandas as pd
import pytest
import xlwt
import config as base
from pipeline.runner import run_file, run_all, validate_snapshot_date
from pipeline.storage import load_master_table, write_excel_table
from pipeline.runner import schemas
from pipeline.workforce import normalize_grade, classify_scenario
from pipeline.exceptions import DataValidationError, MissingColumnError


def cfg(tmp):
 d={n:getattr(base,n) for n in dir(base) if n.isupper()}; d.update({"INPUT_FOLDER":tmp/"input","MASTER_FOLDER":tmp/"master","ARCHIVE_FOLDER":tmp/"archive","REJECTED_FOLDER":tmp/"rejected","LOG_FOLDER":tmp/"logs"}); return SimpleNamespace(**d)
def row(code="001", status="Ажиллаж байгаа", dept="Mining", pos="Operator", grade="A1", etype="Үндсэн"):
 return {"Код":code,"Нэр":"Бат","Овог":"Болд","Албан тушаалын нэр":pos,"Хэлтэс тасаг":dept,"Ажилд орсон огноо":pd.Timestamp("2020-01-01"),"Ажилласан жил":6,"Ажилласан сар":8,"Ажилтны төлөв":status,"Ажилтны төрөл":etype,"Албан тушаалын зэрэглэл":grade,"Ажлаас гарсан огноо":pd.NaT,"Хүйс":"Эр","Нас":36}
def source(c, rows, name):
 c.INPUT_FOLDER.mkdir(parents=True,exist_ok=True); p=c.INPUT_FOLDER/name; write_excel_table(pd.DataFrame(rows),p,"Data"); return p
def legacy_xls(path, rows, sheet="Data"):
 """Generate a genuine BIFF8 workbook at test time; never commit binaries."""
 path.parent.mkdir(parents=True,exist_ok=True); workbook=xlwt.Workbook(); worksheet=workbook.add_sheet(sheet)
 frame=pd.DataFrame(rows)
 for column,value in enumerate(frame.columns): worksheet.write(0,column,value)
 for row_index,values in enumerate(frame.itertuples(index=False,name=None),1):
  for column,value in enumerate(values):
   if pd.isna(value): value=""
   elif isinstance(value,pd.Timestamp): value=value.strftime("%Y-%m-%d")
   worksheet.write(row_index,column,value)
 workbook.save(str(path)); return path
def read(c,n): return pd.read_excel(c.MASTER_FOLDER/f"{n}.xlsx")
def load(c,rows,date,name): return run_file(source(c,rows,name),date,c)

def test_actual_headers_and_first_snapshot_baseline(tmp_path):
 c=cfg(tmp_path); load(c,[row()],"2026-08-31","a.xlsx"); assert list(pd.DataFrame([row()]).columns)==c.EXPECTED_COLUMNS; assert len(read(c,"Fact_Employee_Snapshot"))==1; assert read(c,"Fact_Workforce_Flow").empty; assert read(c,"Fact_Position_Grade_Movement").empty

def test_second_unchanged_and_idempotency_and_immutability(tmp_path):
 c=cfg(tmp_path); load(c,[row()],"2026-07-31","a.xlsx"); load(c,[row()],"2026-08-31","b.xlsx"); assert len(read(c,"Fact_Employee_Snapshot"))==2; assert read(c,"Fact_Position_Grade_Movement").empty; assert run_file(c.INPUT_FOLDER/"b.xlsx","2026-08-31",c)["status"]=="SKIPPED"; assert len(read(c,"Dim_Employee"))==1
 with pytest.raises(DataValidationError): load(c,[row()],"2026-06-30","old.xlsx")

def test_duplicate_employee_rejected(tmp_path):
 c=cfg(tmp_path); r=load(c,[row(),row()],"2026-08-31","a.xlsx"); assert r["accepted"]==0 and r["rejected"]==2; assert read(c,"Fact_Employee_Snapshot").empty

@pytest.mark.parametrize("before,after,code",[("Ажиллаж байгаа","Ажлаас гарсан","MEE000002"),("Ажлаас гарсан","Ажиллаж байгаа","MEE000003"),("Ажиллаж байгаа","Жирэмсний амралт","MEE000005"),("Жирэмсний амралт","Ажиллаж байгаа","MEE000007"),("Ажиллаж байгаа","Уртын өвчтэй","MEE000006"),("Уртын өвчтэй","Ажиллаж байгаа","MEE000008")])
def test_status_flows(tmp_path,before,after,code):
 c=cfg(tmp_path); load(c,[row(status=before)],"2026-07-31","a.xlsx"); load(c,[row(status=after)],"2026-08-31","b.xlsx"); flow=read(c,"Fact_Workforce_Flow"); mt=read(c,"Dim_Movement_Type"); assert mt.set_index("MovementTypeKey").loc[flow.iloc[-1].MovementTypeKey].MovementCode==code

def test_new_hire_on_second_snapshot(tmp_path):
 c=cfg(tmp_path); load(c,[row()],"2026-07-31","a.xlsx"); load(c,[row(),row("002")],"2026-08-31","b.xlsx"); assert len(read(c,"Fact_Workforce_Flow"))==1

@pytest.mark.parametrize("kwargs,scenario",[({"dept":"Finance"},"Organizational Transfer"),({"pos":"Senior Operator"},"Position Reclassification"),({"grade":"A2"},"Grade Promotion")])
def test_attribute_movements(tmp_path,kwargs,scenario):
 c=cfg(tmp_path); load(c,[row()],"2026-07-31","a.xlsx"); load(c,[row(**kwargs)],"2026-08-31","b.xlsx"); m=read(c,"Fact_Position_Grade_Movement").iloc[-1]; scenarios=read(c,"Dim_Movement_Scenario").set_index("MovementScenarioKey"); assert scenarios.loc[m.MovementScenarioKey].MovementScenarioName==scenario

def test_grade_downgrade_unknown_and_cyrillic_normalization(tmp_path):
 c=cfg(tmp_path); assert normalize_grade("А1",c)=="A1"
 load(c,[row(grade="B1")],"2026-07-31","a.xlsx"); load(c,[row(grade="A1")],"2026-08-31","b.xlsx"); scenarios=read(c,"Dim_Movement_Scenario").set_index("MovementScenarioKey"); m=read(c,"Fact_Position_Grade_Movement").iloc[-1]; assert scenarios.loc[m.MovementScenarioKey].MovementScenarioName=="Grade Downgrade"
 c2=cfg(tmp_path/"u"); load(c2,[row(grade="Z1")],"2026-07-31","a.xlsx"); load(c2,[row(grade="Z2")],"2026-08-31","b.xlsx"); m=read(c2,"Fact_Position_Grade_Movement").iloc[-1]; assert read(c2,"Dim_Movement_Scenario").set_index("MovementScenarioKey").loc[m.MovementScenarioKey].MovementScenarioName=="Requires Review"

def test_promotion_and_demotion_classification():
 old=pd.Series(dict(DepartmentKey=1,PositionKey=1,GradeKey=1,GradeRank=1)); new=pd.Series(dict(DepartmentKey=1,PositionKey=2,GradeKey=2,GradeRank=2)); assert classify_scenario(old,new)[0]=="Promotion"; assert classify_scenario(new,old)[0]=="Demotion"

def test_failure_preserves_master(tmp_path):
 c=cfg(tmp_path); load(c,[row()],"2026-08-31","a.xlsx"); before=(c.MASTER_FOLDER/"Fact_Employee_Snapshot.xlsx").read_bytes(); broken=pd.DataFrame([row()]).drop(columns="Код"); p=source(c,broken.to_dict("records"),"bad.xlsx")
 with pytest.raises(MissingColumnError): run_file(p,"2026-09-30",c)
 assert (c.MASTER_FOLDER/"Fact_Employee_Snapshot.xlsx").read_bytes()==before

def test_month_end_validation():
 with pytest.raises(DataValidationError): validate_snapshot_date("2026-08-30")

def test_run_all_creates_folders_and_cli(tmp_path):
 c=cfg(tmp_path); source(c,[row()],"Master-data.xlsx"); run_all("2026-08-31",c); assert (c.MASTER_FOLDER/"Fact_Employee_Snapshot.xlsx").exists()
 app=tmp_path/"app"; shutil.copytree(Path(__file__).parents[1],app,ignore=shutil.ignore_patterns('.git','master','input','logs','archive','rejected','.pytest_cache','__pycache__')); (app/"input").mkdir(); write_excel_table(pd.DataFrame([row()]),app/"input"/"x.xlsx","Data"); result=subprocess.run([sys.executable,str(app/"main.py"),"--snapshot-date","2026-08-31"],cwd=tmp_path,capture_output=True,text=True); assert result.returncode==0,result.stderr

def test_real_biff8_xls_input_is_generated_and_loaded(tmp_path):
 c=cfg(tmp_path); legacy_xls(c.INPUT_FOLDER/"Master-data.xls",[row()])
 result=run_all("2026-08-31",c)
 assert result[0]["status"]=="SUCCESS"
 assert len(read(c,"Fact_Employee_Snapshot"))==1
 employee_master=load_master_table(c.MASTER_FOLDER/"Dim_Employee.xlsx",schemas(c)["Dim_Employee"])
 assert employee_master.iloc[0].EmployeeCode=="001"

def test_dry_run_reconciles_without_modifying_masters(tmp_path):
 c=cfg(tmp_path); load(c,[row()],"2026-07-31","baseline.xlsx"); before={p.name:p.read_bytes() for p in c.MASTER_FOLDER.glob("*.xlsx")}
 preview=run_file(source(c,[row(),row("002",grade="Z9",status="Тодорхойгүй")],"august.xlsx"),"2026-08-31",c,dry_run=True)
 after={p.name:p.read_bytes() for p in c.MASTER_FOLDER.glob("*.xlsx")}
 assert before==after
 assert preview["status"]=="DRY_RUN" and preview["snapshot_rows"]==2
 assert preview["workforce_movements"]==1 and preview["position_grade_movements"]==0
 assert preview["dimension_changes"]["Dim_Employee"]==1
 assert preview["unknown_grades"]==["Z9"] and preview["unknown_statuses"]==["Тодорхойгүй"]

def test_dry_run_shows_duplicate_rejections_and_cli_summary(tmp_path):
 c=cfg(tmp_path); p=source(c,[row(),row()],"duplicate.xlsx"); preview=run_file(p,"2026-08-31",c,dry_run=True)
 assert preview["rejected"]==2 and preview["snapshot_rows"]==0
 assert all("Duplicate EmployeeCode" in item["Error_Reason"] for item in preview["rejected_rows"])
 app=tmp_path/"dry_app"; shutil.copytree(Path(__file__).parents[1],app,ignore=shutil.ignore_patterns('.git','master','input','logs','archive','rejected','.pytest_cache','__pycache__')); (app/"input").mkdir(); write_excel_table(pd.DataFrame([row()]),app/"input"/"x.xlsx","Data")
 result=subprocess.run([sys.executable,str(app/"main.py"),"--snapshot-date","2026-08-31","--dry-run"],cwd=tmp_path,capture_output=True,text=True)
 assert result.returncode==0 and "DRY-RUN RECONCILIATION SUMMARY" in result.stdout and "NO MASTER OR FACT FILES WERE MODIFIED" in result.stdout
 assert not (app/"master").exists() or not list((app/"master").glob("*.xlsx"))
