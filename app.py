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
    """Return list of unit codes (e.g. ['1-2','2-1']) for given grade & school from end sheet."""
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_END}!A2:D"
    ).execute()
    rows = result.get("values", [])
    codes = []
    for r in rows:
        if len(r) >= 4:
            # B: grade, C: school, D: units(csv)
            if str(r[1]) == str(grade) and r[2] == school:
                codes = [u.strip() for u in r[3].split(",") if u.strip()]
                break
    return codes

def read_grade_schools(grade):
    """Return list of unique school names that have rows for given grade in end sheet."""
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_END}!A2:D"
    ).execute()
    rows = result.get("values", [])
    schools = []
    seen = set()
    for r in rows:
        if len(r) >= 3:
            if str(r[1]) == str(grade):
                sch = r[2]
                if sch and sch not in seen:
                    seen.add(sch)
                    schools.append(sch)
    return schools

def get_unit_name_map(grade, codes):
    """Given grade and list of codes, return mapping {code: unit_name}."""
    if not codes:
        return {}
    codes_set = set(codes)
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_UNITS}!A2:C"
    ).execute()
    rows = result.get("values", [])
    mapping = {}
    for r in rows:
        if len(r) >= 3:
            g = str(r[0])
            code = str(r[1])
            name = r[2]
            if g == str(grade) and code in codes_set:
                mapping[code] = name
    return mapping

def find_pdfs(material_type, grade, unit_code):
    folder = f"data/{material_type}/{grade}학년"
    if not os.path.isdir(folder):
        return []
    files = []
    # unit_code may contain '-' and such; escape for regex
    pattern = re.compile(rf"{re.escape(unit_code)}\b")
    for f in os.listdir(folder):
        if f.lower().endswith(".pdf") and pattern.search(f):
            files.append(os.path.join(folder, f))
    return files

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/schools")
def api_schools():
    return jsonify(read_school_list())

@app.route("/api/grade_schools", methods=["POST"])
def api_grade_schools():
    data = request.json
    grade = data["grade"]
    schools = read_grade_schools(grade)
    return jsonify(schools)

@app.route("/api/units", methods=["POST"])
def api_units():
    data = request.json
    grade = data["grade"]
    school = data["school"]
    codes = read_units_codes(grade, school)
    return jsonify(codes)

@app.route("/api/unit_names", methods=["POST"])
def api_unit_names():
    data = request.json
    grade = data["grade"]
    codes = data.get("codes", [])
    mapping = get_unit_name_map(grade, codes)
    return jsonify(mapping)

@app.route("/api/merge", methods=["POST"])
def api_merge():
    data = request.json
    grade = data["grade"]
    unit = data["unit"]
    mtype = data["type"]

    pdfs = find_pdfs(mtype, grade, unit)
    if not pdfs:
        return jsonify({"error": "no_files"}), 404

    merger = PdfMerger()
    for p in pdfs:
        merger.append(p)

    buf = io.BytesIO()
    merger.write(buf)
    merger.close()
    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name=f"{grade}학년_{unit}_{mtype}.pdf",
        mimetype="application/pdf"
    )

@app.route("/api/merge_all", methods=["POST"])
def api_merge_all():
    data = request.json
    grade = data["grade"]
    mtype = data["type"]
    school = data["school"]

    units = read_units_codes(grade, school)
    merger = PdfMerger()
    count = 0

    for unit in units:
        pdfs = find_pdfs(mtype, grade, unit)
        for p in pdfs:
            merger.append(p)
            count += 1

    if count == 0:
        return jsonify({"error": "no_files"}), 404

    buf = io.BytesIO()
    merger.write(buf)
    merger.close()
    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name=f"{grade}학년_{school}_{mtype}_전체.pdf",
        mimetype="application/pdf"
    )

# =========================
# Final 모의고사 병합 (추가/수정)
# 규칙:
# - end 시트의 단원코드(예: 2-1, 2-2, 3-1...)에서 "앞 숫자"만 추출
# - 해당 숫자 + '단원' 이 들어간 PDF를 합친다
# - 1학년의 1단원 Final은 존재하지 않으므로 (유일 예외) 1학년이면 1단원은 스킵
# =========================
@app.route("/api/merge_final", methods=["POST"])
def api_merge_final():
    data = request.json
    grade = str(data["grade"])
    school = data["school"]

    units = read_units_codes(grade, school)

    # '2-1' -> 2 같은 대단원 번호만 추출
    unit_numbers = sorted({
        int(u.split("-")[0])
        for u in units
        if "-" in u and u.split("-")[0].isdigit()
    })

    folder = f"data/Final모의고사/{grade}학년"
    if not os.path.isdir(folder):
        return jsonify({"error": "no_folder"}), 404

    merger = PdfMerger()
    count = 0

    for num in unit_numbers:
        # 1학년 1단원 Final은 없음(유일 예외)
        if grade == "1" and num == 1:
            continue

        # 파일명 어딘가에 '2단원', '3단원'이 포함되어 있으면 OK
        # (네 파일명 규칙: ... [Q] 2단원.pdf 형태)
        pattern = re.compile(rf"{num}\s*단원", re.IGNORECASE)

        matched_path = None
        for f in os.listdir(folder):
            if f.lower().endswith(".pdf") and pattern.search(f):
                matched_path = os.path.join(folder, f)
                break  # 단원당 1개라는 전제(중복 파일이 있으면 첫 번째만)

        if not matched_path:
            return jsonify({"error": f"no_unit_{num}"}), 404

        merger.append(matched_path)
        count += 1

    if count == 0:
        return jsonify({"error": "no_files"}), 404

    buf = io.BytesIO()
    merger.write(buf)
    merger.close()
    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name=f"{grade}학년_{school}_FINAL모의고사.pdf",
        mimetype="application/pdf"
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
