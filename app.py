from flask import Flask, render_template, request, jsonify, send_file
import os, io, re, json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from PyPDF2 import PdfMerger

SPREADSHEET_ID = "1rsplfNq4e7d-nrp-Wlg1Mn9dsgjAcNn49yPQDXdzwg8"
SHEET_SCHOOL = "school"
SHEET_END = "end"
SHEET_UNITS = "units"
GOOGLE_ENV = "GOOGLE_CREDENTIALS"

app = Flask(__name__)

def get_service():
    info = json.loads(os.getenv(GOOGLE_ENV))
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build("sheets", "v4", credentials=creds)

def read_school_list():
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_SCHOOL}!A2:A"
    ).execute()
    vals = result.get("values", [])
    return [v[0] for v in vals if v]

def read_units_codes(grade, school):
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_END}!A2:D"
    ).execute()
    rows = result.get("values", [])
    for r in rows:
        if len(r) >= 4 and str(r[1]) == str(grade) and r[2] == school:
            return [u.strip() for u in r[3].split(",") if u.strip()]
    return []

def read_grade_schools(grade):
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_END}!A2:D"
    ).execute()
    rows = result.get("values", [])
    seen = set()
    schools = []
    for r in rows:
        if len(r) >= 3 and str(r[1]) == str(grade):
            if r[2] not in seen:
                seen.add(r[2])
                schools.append(r[2])
    return schools

def get_unit_name_map(grade, codes):
    if not codes:
        return {}
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_UNITS}!A2:C"
    ).execute()
    rows = result.get("values", [])
    mapping = {}
    for r in rows:
        if len(r) >= 3 and str(r[0]) == str(grade) and r[1] in codes:
            mapping[r[1]] = r[2]
    return mapping

def find_pdfs(material_type, grade, unit_code):
    folder = f"data/{material_type}/{grade}학년"
    if not os.path.isdir(folder):
        return []
    pattern = re.compile(rf"{re.escape(unit_code)}\b")
    return [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(".pdf") and pattern.search(f)
    ]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/schools")
def api_schools():
    return jsonify(read_school_list())

@app.route("/api/grade_schools", methods=["POST"])
def api_grade_schools():
    return jsonify(read_grade_schools(request.json["grade"]))

@app.route("/api/units", methods=["POST"])
def api_units():
    d = request.json
    return jsonify(read_units_codes(d["grade"], d["school"]))

@app.route("/api/unit_names", methods=["POST"])
def api_unit_names():
    d = request.json
    return jsonify(get_unit_name_map(d["grade"], d.get("codes", [])))

@app.route("/api/merge_all", methods=["POST"])
def api_merge_all():
    d = request.json
    merger = PdfMerger()
    count = 0
    for unit in read_units_codes(d["grade"], d["school"]):
        for p in find_pdfs(d["type"], d["grade"], unit):
            merger.append(p)
            count += 1
    if count == 0:
        return jsonify({"error": "no_files"}), 404
    buf = io.BytesIO()
    merger.write(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f'{d["grade"]}학년_{d["school"]}_{d["type"]}_전체.pdf',
        mimetype="application/pdf"
    )

@app.route("/api/merge_final", methods=["POST"])
def api_merge_final():
    d = request.json
    grade = str(d["grade"])
    units = read_units_codes(grade, d["school"])
    nums = sorted({int(u.split("-")[0]) for u in units if "-" in u})
    folder = f"data/Final모의고사/{grade}학년"
    merger = PdfMerger()
    for n in nums:
        if grade == "1" and n == 1:
            continue
        pat = re.compile(rf"{n}\s*단원")
        for f in os.listdir(folder):
            if pat.search(f):
                merger.append(os.path.join(folder, f))
                break
    buf = io.BytesIO()
    merger.write(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f'{grade}학년_{d["school"]}_FINAL모의고사.pdf',
        mimetype="application/pdf"
    )

# ===== 오투 모의고사 (추가 기능) =====
@app.route("/api/merge_otoo", methods=["POST"])
def api_merge_otoo():
    d = request.json
    grade = str(d["grade"])
    units = read_units_codes(grade, d["school"])
    nums = sorted({int(u.split("-")[0]) for u in units if "-" in u})
    folder = f"data/오투모의고사/{grade}학년"
    merger = PdfMerger()
    for n in nums:
        if grade == "1" and n == 1:
            continue
        pat = re.compile(rf"{n}\s*단원")
        for f in os.listdir(folder):
            if pat.search(f):
                merger.append(os.path.join(folder, f))
                break
    buf = io.BytesIO()
    merger.write(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f'{grade}학년_{d["school"]}_오투모의고사.pdf',
        mimetype="application/pdf"
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
