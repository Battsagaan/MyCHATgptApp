"""Create a sample Mongolian month-end employee source."""
import pandas as pd
import config
from pipeline.storage import write_excel_table

def generate(path=config.INPUT_FOLDER/"Master-data-sample.xlsx", rows=100):
    n=pd.Series(range(1,rows+1)); path.parent.mkdir(parents=True,exist_ok=True)
    df=pd.DataFrame({"Код":n.map(lambda x:f"{x:06d}"),"Нэр":n.map(lambda x:f"Нэр {x}"),"Овог":"Бат",
      "Албан тушаалын нэр":"Ажилтан","Хэлтэс тасаг":"Үйл ажиллагаа","Ажилд орсон огноо":pd.Timestamp("2020-01-01"),
      "Ажилласан жил":6,"Ажилласан сар":0,"Ажилтны төлөв":"Ажиллаж байгаа","Ажилтны төрөл":"Үндсэн",
      "Албан тушаалын зэрэглэл":"A1","Ажлаас гарсан огноо":pd.NaT,"Хүйс":"Эр","Нас":30})
    write_excel_table(df,path,"SourceData"); return path
if __name__=="__main__": print(generate())
