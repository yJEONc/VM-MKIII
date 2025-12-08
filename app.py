from flask import Flask, render_template, request, jsonify, send_file
import os, io, re, json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from PyPDF2 import PdfMerger

SPREADSHEET_ID = "1rsplfNq4e7d-nrp-Wlg1Mn9dsgjAcNn49yPQDXdzwg8"
SHEET_SCHOOL = "school"
SHEET_END = "end"
GOOGLE_ENV = "GOOGLE_CREDENTIALS"

app = Flask(__name__)

def get_service():
    info = json.loads(os.getenv(GOOGLE_ENV))
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build("sheets","v4",credentials=creds)

def read_school_list():
    service=get_service()
    result=service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_SCHOOL}!A2:A"
    ).execute()
    vals=result.get("values",[])
    return [v[0] for v in vals if v]

def read_units(grade,school):
    service=get_service()
    result=service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_END}!A2:D"
    ).execute()
    rows=result.get("values",[])
    for r in rows:
        if len(r)>=4:
            if str(r[1])==str(grade) and r[2]==school:
                return [u.strip() for u in r[3].split(",")]
    return []

def find_pdfs(material_type,grade,unit):
    folder=f"data/{material_type}/{grade}학년"
    if not os.path.isdir(folder): 
        return []
    files=[]
    for f in os.listdir(folder):
        if f.lower().endswith(".pdf") and re.search(rf"{unit}\b",f):
            files.append(os.path.join(folder,f))
    return files

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/schools")
def api_schools():
    return jsonify(read_school_list())

@app.route("/api/units",methods=["POST"])
def api_units():
    data=request.json
    grade=data["grade"]
    school=data["school"]
    return jsonify(read_units(grade,school))

@app.route("/api/merge",methods=["POST"])
def api_merge():
    data=request.json
    grade=data["grade"]
    unit=data["unit"]
    mtype=data["type"]

    pdfs=find_pdfs(mtype,grade,unit)
    if not pdfs:
        return jsonify({"error":"no_files"}),404

    merger=PdfMerger()
    for p in pdfs: 
        merger.append(p)

    buf=io.BytesIO()
    merger.write(buf)
    merger.close()
    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name=f"{grade}학년_{unit}_{mtype}.pdf",
        mimetype="application/pdf"
    )

if __name__=="__main__":
    port=int(os.getenv("PORT","5000"))
    app.run(host="0.0.0.0",port=port)
