"""Month-end snapshot orchestration and transactional Excel commit."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import config
from .cleaning import clean_dataframe
from .exceptions import DataValidationError
from .facts import create_date_dimension
from .logging_setup import configure_logging
from .storage import backup_master_files, inspect_source, load_master_table, load_source_file, save_master_tables, save_rejected_rows
from .utils import ensure_folders, file_sha256, load_id
from .validation import validate_schema, validate_rows
from .workforce import AUDIT, classify_scenario, movement_code, normalize_grade, static_dimensions, status_flags, upsert_dimension

def validate_snapshot_date(value) -> pd.Timestamp:
    date = pd.Timestamp(value).normalize()
    if date != date + pd.offsets.MonthEnd(0):
        raise DataValidationError(f"SnapshotDate must be the last calendar day of its month: {date.date()}")
    return date

def schemas(cfg=config):
    return {
      "Dim_Employee": ["EmployeeKey","EmployeeCode","FirstName","LastName","Gender","CreatedDate","UpdatedDate"],
      "Dim_Department": ["DepartmentKey","DepartmentName","DepartmentNameNormalized","IsActive"],
      "Dim_Position": ["PositionKey","PositionName","PositionNameNormalized","IsActive"],
      "Dim_Grade": ["GradeKey","GradeCode","GradeRank","GradeGroup","IsActive"],
      "Dim_Employment_Type": ["EmploymentTypeKey","EmploymentTypeName","IsActive"],
      "Dim_Employee_Status": ["StatusKey","StatusName","ActiveWorkforceFlag","EmploymentRelationshipFlag"],
      "Fact_Employee_Snapshot": ["SnapshotFactKey","SnapshotDateKey","EmployeeKey","DepartmentKey","PositionKey","GradeKey","EmploymentTypeKey","StatusKey","HireDate","TerminationDate","AgeSnapshot","TenureYearsSource","TenureMonthsSource","TenureMonthsCalculated","HeadcountValue","ActiveWorkforceFlag","EmploymentRelationshipFlag","SourceFile","SourceRowNumber","LoadID","LoadedDateTime"],
      "Fact_Workforce_Flow": ["FlowFactKey","EmployeeKey","EventDateKey","MovementTypeKey","DepartmentKey","PositionKey","GradeKey","EmploymentTypeKey","FlowValue","EmploymentHCImpact","ActiveWorkforceImpact","PreviousStatusKey","NewStatusKey","PreviousSnapshotDateKey","CurrentSnapshotDateKey","IsAutoDetected","DetectionRule","ValidationStatus",*AUDIT],
      "Fact_Position_Grade_Movement": ["MovementFactKey","EmployeeKey","MovementDateKey","MovementScenarioKey","OldDepartmentKey","NewDepartmentKey","OldPositionKey","NewPositionKey","OldGradeKey","NewGradeKey","OldGradeRank","NewGradeRank","GradeRankDifference","PositionChangedFlag","GradeChangedFlag","DepartmentChangedFlag","EmploymentTypeChangedFlag","MovementCount","PreviousSnapshotDateKey","CurrentSnapshotDateKey","IsAutoDetected","ConfidenceStatus","ValidationStatus",*AUDIT],
      "Load_History": cfg.LOAD_HISTORY_COLUMNS,
    }

def _load(name, cols, cfg): return load_master_table(cfg.MASTER_FOLDER/f"{name}.xlsx", cols)
def _next(df, key): return int(pd.to_numeric(df[key], errors="coerce").max()) + 1 if len(df) else 1

def run_file(path: Path, snapshot_date, cfg=config, dry_run: bool = False):
    snap = validate_snapshot_date(snapshot_date); snap_key = int(snap.strftime("%Y%m%d")); now = pd.Timestamp.now(); lid = load_id(now.to_pydatetime())
    logger = configure_logging(cfg.LOG_FOLDER, lid); sc = schemas(cfg)
    validate_schema(inspect_source(path, cfg.SOURCE_SHEET), cfg)
    history = _load("Load_History", sc["Load_History"], cfg); digest = file_sha256(path)
    if not dry_run and len(history) and ((history.File_Hash == digest) & (pd.to_numeric(history.SnapshotDateKey) == snap_key) & (history.Status == "SUCCESS")).any():
        return {"status":"SKIPPED","load_id":lid}
    raw=load_source_file(path,cfg.SOURCE_SHEET); clean, errors=clean_dataframe(raw,cfg); valid,rejected=validate_rows(clean,errors,cfg)
    valid=valid.rename(columns=cfg.SOURCE_COLUMN_MAPPING); rejected["Source_File"]=path.name
    duplicates=valid.EmployeeCode.duplicated(False)
    if duplicates.any():
        bad=valid.loc[duplicates].copy(); bad["Validation_Status"]="REJECTED"; bad["Error_Reason"]="Duplicate EmployeeCode within snapshot"; bad["Source_File"]=path.name
        rejected=pd.concat([rejected,bad],ignore_index=True); valid=valid.loc[~duplicates]
    valid["GradeCode"]=valid.Grade.map(lambda x: normalize_grade(x,cfg))
    tables={}; dimension_changes={}
    # Employee SCD1
    emp=_load("Dim_Employee",sc["Dim_Employee"],cfg); incoming=valid[["EmployeeCode","FirstName","LastName","Gender"]].drop_duplicates("EmployeeCode",keep="last")
    dimension_changes["Dim_Employee"] = int((~incoming.EmployeeCode.isin(emp.EmployeeCode)).sum()) if len(emp) else len(incoming)
    old=emp.set_index("EmployeeCode") if len(emp) else emp
    for _,r in incoming.iterrows():
        if r.EmployeeCode in old.index:
            idx=emp.index[emp.EmployeeCode==r.EmployeeCode][0]; changed=any(str(emp.at[idx,c])!=str(r[c]) for c in ["FirstName","LastName","Gender"])
            if changed: emp.loc[idx,["FirstName","LastName","Gender","UpdatedDate"]]=[r.FirstName,r.LastName,r.Gender,now]
        else:
            emp.loc[len(emp)]=[_next(emp,"EmployeeKey"),r.EmployeeCode,r.FirstName,r.LastName,r.Gender,now,now]
    tables["Dim_Employee"]=emp
    # Reference dimensions
    specs=[("Dim_Department","Department","DepartmentName","DepartmentKey"),("Dim_Position","Position","PositionName","PositionKey"),("Dim_Employment_Type","EmploymentType","EmploymentTypeName","EmploymentTypeKey")]
    for name,src,natural,key in specs:
        master=_load(name,sc[name],cfg); temp=valid.rename(columns={src:natural}); extra=[c for c in sc[name] if c not in [key,natural]]
        dimension_changes[name] = int((~temp[natural].dropna().drop_duplicates().isin(master[natural])).sum()) if len(master) else temp[natural].dropna().nunique()
        master=upsert_dimension(temp,master,natural,key,extra)
        if "Normalized" in "".join(extra): master[extra[0]]=master[natural].astype("string").str.replace(r"\s+"," ",regex=True).str.strip().str.casefold()
        tables[name]=master
    grade=_load("Dim_Grade",sc["Dim_Grade"],cfg); dimension_changes["Dim_Grade"] = int((~valid.GradeCode.dropna().drop_duplicates().isin(grade.GradeCode)).sum()) if len(grade) else valid.GradeCode.dropna().nunique(); grade=upsert_dimension(valid,grade,"GradeCode","GradeKey",["GradeRank","GradeGroup","IsActive"])
    grade["GradeRank"]=grade.GradeCode.map(cfg.GRADE_RANK); grade["GradeGroup"]=grade.GradeCode.astype("string").str[0].map(cfg.GRADE_GROUPS); grade["IsActive"]=True; tables["Dim_Grade"]=grade
    status=_load("Dim_Employee_Status",sc["Dim_Employee_Status"],cfg); dimension_changes["Dim_Employee_Status"] = int((~valid.EmployeeStatus.dropna().drop_duplicates().isin(status.StatusName)).sum()) if len(status) else valid.EmployeeStatus.dropna().nunique(); status=upsert_dimension(valid.rename(columns={"EmployeeStatus":"StatusName"}),status,"StatusName","StatusKey",["ActiveWorkforceFlag","EmploymentRelationshipFlag"])
    flags=status.StatusName.map(lambda x: status_flags(x,cfg)); status["ActiveWorkforceFlag"]=[x[0] for x in flags]; status["EmploymentRelationshipFlag"]=[x[1] for x in flags]; tables["Dim_Employee_Status"]=status
    tables.update(static_dimensions(cfg)); tables["Dim_Date"]=create_date_dimension(cfg.DATE_START,cfg.DATE_END)
    # Resolve keys
    cur=valid.copy()
    for dim,source,natural,key in [("Dim_Employee","EmployeeCode","EmployeeCode","EmployeeKey"),("Dim_Department","Department","DepartmentName","DepartmentKey"),("Dim_Position","Position","PositionName","PositionKey"),("Dim_Grade","GradeCode","GradeCode","GradeKey"),("Dim_Employment_Type","EmploymentType","EmploymentTypeName","EmploymentTypeKey"),("Dim_Employee_Status","EmployeeStatus","StatusName","StatusKey")]:
        cur=cur.merge(tables[dim][[natural,key]],left_on=source,right_on=natural,how="left").drop(columns=[natural] if natural!=source else [])
    cur["SnapshotDateKey"]=snap_key; cur["TenureMonthsCalculated"]=((snap.dt.year-valid.HireDate.dt.year)*12+(snap.month-valid.HireDate.dt.month)) if False else ((snap.year-cur.HireDate.dt.year)*12+(snap.month-cur.HireDate.dt.month)).clip(lower=0)
    f=_load("Fact_Employee_Snapshot",sc["Fact_Employee_Snapshot"],cfg)
    if len(f) and snap_key < pd.to_numeric(f.SnapshotDateKey).max(): raise DataValidationError("Historical snapshots are immutable; load dates must not go backwards")
    if len(f) and snap_key == pd.to_numeric(f.SnapshotDateKey).max() and not ((history.File_Hash==digest)&(pd.to_numeric(history.SnapshotDateKey)==snap_key)).any(): raise DataValidationError("Snapshot month already exists and is immutable")
    previous_key=int(pd.to_numeric(f.SnapshotDateKey).max()) if len(f) else None; prev=f[pd.to_numeric(f.SnapshotDateKey)==previous_key].copy() if previous_key else pd.DataFrame()
    snapshot=pd.DataFrame({"SnapshotDateKey":snap_key,"EmployeeKey":cur.EmployeeKey,"DepartmentKey":cur.DepartmentKey,"PositionKey":cur.PositionKey,"GradeKey":cur.GradeKey,"EmploymentTypeKey":cur.EmploymentTypeKey,"StatusKey":cur.StatusKey,"HireDate":cur.HireDate,"TerminationDate":cur.TerminationDate,"AgeSnapshot":cur.AgeSnapshot,"TenureYearsSource":cur.TenureYearsSource,"TenureMonthsSource":cur.TenureMonthsSource,"TenureMonthsCalculated":cur.TenureMonthsCalculated,"HeadcountValue":1,"ActiveWorkforceFlag":cur.EmployeeStatus.map(lambda x:status_flags(x,cfg)[0]),"EmploymentRelationshipFlag":cur.EmployeeStatus.map(lambda x:status_flags(x,cfg)[1]),"SourceFile":path.name,"SourceRowNumber":cur.Source_Row_Number,"LoadID":lid,"LoadedDateTime":now})
    snapshot.insert(0,"SnapshotFactKey",range(_next(f,"SnapshotFactKey"),_next(f,"SnapshotFactKey")+len(snapshot))); tables["Fact_Employee_Snapshot"]=pd.concat([f,snapshot],ignore_index=True)
    flows=_load("Fact_Workforce_Flow",sc["Fact_Workforce_Flow"],cfg); moves=_load("Fact_Position_Grade_Movement",sc["Fact_Position_Grade_Movement"],cfg)
    if previous_key:
        compare=cur.merge(prev,on="EmployeeKey",how="left",suffixes=("","Old")); mt=tables["Dim_Movement_Type"].set_index("MovementCode"); scenario=tables["Dim_Movement_Scenario"].set_index("MovementScenarioName")
        flowrows=[]; moverows=[]
        for r in compare.itertuples():
            isnew=pd.isna(r.SnapshotDateKeyOld); oldstatus=None if isnew else status.set_index("StatusKey").StatusName.get(r.StatusKeyOld); code=movement_code(oldstatus,r.EmployeeStatus,isnew)
            if code:
                m=mt.loc[code]; event=r.HireDate if code in ("MEE000001","MEE000003") else (r.TerminationDate if code=="MEE000002" and pd.notna(r.TerminationDate) else snap)
                flowrows.append([r.EmployeeKey,int(event.strftime("%Y%m%d")),m.MovementTypeKey,r.DepartmentKey,r.PositionKey,r.GradeKey,r.EmploymentTypeKey,m.FlowValue,m.EmploymentHCImpact,m.ActiveWorkforceImpact,None if isnew else r.StatusKeyOld,r.StatusKey,None if isnew else previous_key,snap_key,True,code,"VALID",path.name,lid,now])
            if not isnew:
                changed=any(getattr(r,x)!=getattr(r,x+"Old") for x in ["DepartmentKey","PositionKey","GradeKey","EmploymentTypeKey"])
                if changed:
                    oldgrade=grade.set_index("GradeKey").GradeRank.get(r.GradeKeyOld); newgrade=grade.set_index("GradeKey").GradeRank.get(r.GradeKey); name,conf=classify_scenario(pd.Series({"DepartmentKey":r.DepartmentKeyOld,"PositionKey":r.PositionKeyOld,"GradeKey":r.GradeKeyOld,"GradeRank":oldgrade}),pd.Series({"DepartmentKey":r.DepartmentKey,"PositionKey":r.PositionKey,"GradeKey":r.GradeKey,"GradeRank":newgrade}))
                    moverows.append([r.EmployeeKey,snap_key,scenario.loc[name].MovementScenarioKey,r.DepartmentKeyOld,r.DepartmentKey,r.PositionKeyOld,r.PositionKey,r.GradeKeyOld,r.GradeKey,oldgrade,newgrade,None if pd.isna(oldgrade) or pd.isna(newgrade) else newgrade-oldgrade,r.PositionKey!=r.PositionKeyOld,r.GradeKey!=r.GradeKeyOld,r.DepartmentKey!=r.DepartmentKeyOld,r.EmploymentTypeKey!=r.EmploymentTypeKeyOld,1,previous_key,snap_key,True,conf,"VALID",path.name,lid,now])
        if flowrows:
            add=pd.DataFrame(flowrows,columns=sc["Fact_Workforce_Flow"][1:]); add.insert(0,"FlowFactKey",range(_next(flows,"FlowFactKey"),_next(flows,"FlowFactKey")+len(add))); flows=pd.concat([flows,add],ignore_index=True)
        if moverows:
            add=pd.DataFrame(moverows,columns=sc["Fact_Position_Grade_Movement"][1:]); add.insert(0,"MovementFactKey",range(_next(moves,"MovementFactKey"),_next(moves,"MovementFactKey")+len(add))); moves=pd.concat([moves,add],ignore_index=True)
    tables["Fact_Workforce_Flow"],tables["Fact_Position_Grade_Movement"]=flows,moves
    unknown_grades=sorted(valid.loc[valid.GradeCode.notna() & ~valid.GradeCode.isin(cfg.GRADE_RANK),"GradeCode"].unique().tolist())
    unknown_statuses=sorted(valid.loc[~valid.EmployeeStatus.isin(cfg.STATUS_RULES),"EmployeeStatus"].dropna().unique().tolist())
    preview={"status":"DRY_RUN" if dry_run else "SUCCESS","load_id":lid,"source_rows":len(raw),"accepted":len(valid),"rejected":len(rejected),
             "rejected_rows":rejected[[c for c in ["Source_Row_Number","EmployeeCode","Код","Error_Reason"] if c in rejected.columns]].to_dict("records"),
             "dimension_changes":dimension_changes,"snapshot_rows":len(snapshot),"workforce_movements":len(flows)-len(_load("Fact_Workforce_Flow",sc["Fact_Workforce_Flow"],cfg)),
             "position_grade_movements":len(moves)-len(_load("Fact_Position_Grade_Movement",sc["Fact_Position_Grade_Movement"],cfg)),
             "unknown_grades":unknown_grades,"unknown_statuses":unknown_statuses}
    if dry_run:
        logger.info("DRY RUN complete; no master data was modified")
        return preview
    stat=path.stat(); row=pd.DataFrame([[lid,path.name,stat.st_size,pd.Timestamp(stat.st_mtime,unit="s"),digest,snap_key,now,len(raw),len(valid),len(rejected),"SUCCESS"]],columns=sc["Load_History"]); tables["Load_History"]=pd.concat([history,row],ignore_index=True)
    stamp=now.strftime("%Y-%m-%d_%H%M%S_%f"); backup_master_files(cfg.MASTER_FOLDER,cfg.ARCHIVE_FOLDER,stamp,list(tables)); save_master_tables(tables,cfg.MASTER_FOLDER); save_rejected_rows(rejected,cfg.REJECTED_FOLDER,stamp)
    logger.info("Snapshot %s: %s accepted, %s rejected",snap.date(),len(valid),len(rejected)); return preview

def run_all(snapshot_date, cfg=config, dry_run: bool = False):
    ensure_folders([cfg.INPUT_FOLDER,cfg.MASTER_FOLDER,cfg.ARCHIVE_FOLDER,cfg.REJECTED_FOLDER,cfg.LOG_FOLDER]); files=sorted(p for ext in ("*.xlsx","*.xls") for p in cfg.INPUT_FOLDER.glob(ext) if not p.name.startswith("~$"))
    if not files: raise FileNotFoundError(f"No .xlsx or .xls source files found in {cfg.INPUT_FOLDER}")
    return [run_file(p,snapshot_date,cfg,dry_run=dry_run) for p in (files if cfg.PROCESS_ALL_FILES else files[:1])]
