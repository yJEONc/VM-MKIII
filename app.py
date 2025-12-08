import os
import io
import re
import json
from datetime import datetime
from typing import List, Dict, Any

from flask import Flask, render_template, request, jsonify, send_file

from PyPDF2 import PdfMerger
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import googleapiclient.discovery_cache.base
googleapiclient.discovery_cache.base.cache = None

SPREADSHEET_ID = "1rsplfNq4e7d-nrp-Wlg1Mn9dsgjAcNn49yPQDXdzwg8"
END_SHEET_NAME = "end"
DATA_DIR = "data"
MATERIAL_TYPES = ["서술형", "최다빈출"]
GOOGLE_CREDENTIALS_ENV = "GOOGLE_CREDENTIALS"

app = Flask(__name__)
END_CACHE: List[Dict[str, Any]] = []

def get_sheets_service():
    cred_json = os.getenv(GOOGLE_CREDENTIALS_ENV)
    if not cred_json:
        raise RuntimeError(f"{GOOGLE_CREDENTIALS_ENV} 환경변수가 설정되지 않았습니다.")
    info = json.loads(cred_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    service = build("sheets", "v4", credentials=creds)
    return service

def fetch_end_data_from_google() -> List[Dict[str, Any]]:
    service = get_sheets_service()
    range_name = f"{END_SHEET_NAME}!A2:D"
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    ).execute()
    values = result.get("values", [])
    data: List[Dict[str, Any]] = []
    for row in values:
        if len(row) < 4:
            continue
        timestamp_str, grade_str, school, units_str = row[:4]
        if not grade_str or not school:
            continue
        try:
            grade = int(grade_str)
        except ValueError:
            continue
        units = [u.strip() for u in units_str.split(",") if u.strip()]
        data.append({"timestamp": timestamp_str,"grade": grade,"school": school,"units": units})
    return data

def load_end_cache():
    global END_CACHE
    try:
        END_CACHE = fetch_end_data_from_google()
    except Exception as e:
        END_CACHE = []

def grade_to_folder(grade: int) -> str:
    return f"{grade}학년"

def find_matching_files(material_type: str, grade: int, unit_code: str) -> List[str]:
    grade_folder = grade_to_folder(grade)
    base_dir = os.path.join(DATA_DIR, material_type, grade_folder)
    if not os.path.isdir(base_dir):
        return []
    try:
        filenames = sorted(os.listdir(base_dir))
    except FileNotFoundError:
        return []
    pattern = re.compile(rf"\b{re.escape(unit_code)}\b")
    matched = []
    for name in filenames:
        if name.lower().endswith(".pdf") and pattern.search(name):
            matched.append(os.path.join(base_dir, name))
    return matched

def extract_title_from_filename(filepath: str, unit_code: str) -> str:
    base = os.path.basename(filepath)
    pattern = re.compile(rf"{re.escape(unit_code)}\.(.*?)\(")
    m = pattern.search(base)
    return m.group(1).strip() if m else ""

@app.before_request
def ensure_cache():
    if not END_CACHE:
        load_end_cache()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/end_data", methods=["GET"])
def api_end_data():
    return jsonify(END_CACHE)

@app.route("/reload", methods=["POST"])
def reload_end_cache():
    try:
        load_end_cache()
        return jsonify({"status":"ok","rows":len(END_CACHE)})
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}),500

@app.route("/api/preview_units", methods=["POST"])
def api_preview_units():
    req = request.get_json() or {}
    try:
        grade = int(req.get("grade"))
    except:
        return jsonify({"error":"invalid_grade"}),400
    school = req.get("school")
    entry = next((d for d in END_CACHE if d["grade"]==grade and d["school"]==school),None)
    if not entry:
        return jsonify({"error":"not_found"}),404
    units_info=[]
    for unit in entry["units"]:
        title=""
        has_file=False
        for material_type in MATERIAL_TYPES:
            files=find_matching_files(material_type,grade,unit)
            if files:
                has_file=True
                t=extract_title_from_filename(files[0],unit)
                if t: title=t; break
        if not has_file: title="(자료 없음)"
        elif not title: title="(제목 없음)"
        units_info.append({"code":unit,"title":title,"has_file":has_file})
    return jsonify({"grade":grade,"school":school,"units":units_info})

@app.route("/merge/<material_type>", methods=["POST"])
def merge_material(material_type):
    if material_type not in MATERIAL_TYPES:
        return jsonify({"error":"invalid_type"}),400
    req = request.get_json() or {}
    try:
        grade = int(req.get("grade"))
    except:
        return jsonify({"error":"invalid_grade"}),400
    school=req.get("school")
    entry = next((d for d in END_CACHE if d["grade"]==grade and d["school"]==school),None)
    if not entry:
        return jsonify({"error":"not_found"}),404
    units=entry["units"]
    merger=PdfMerger()
    total=0
    for unit in units:
        files=find_matching_files(material_type,grade,unit)
        for f in files:
            if os.path.exists(f):
                merger.append(f); total+=1
    if total==0:
        return jsonify({"error":"no_files"}),404
    buf=io.BytesIO()
    merger.write(buf); merger.close(); buf.seek(0)
    filename=f"{school}_{grade}학년_{material_type}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=filename)

if __name__=="__main__":
    port=int(os.getenv("PORT","5000"))
    app.run(host="0.0.0.0", port=port)
