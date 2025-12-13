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


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)

@app.route("/api/merge_final", methods=["POST"])
def api_merge_final():
    data = request.json
    grade = data["grade"]
    school = data["school"]

    units = read_units_codes(grade, school)
    unit_numbers = sorted({int(u.split("-")[0]) for u in units})

    folder = f"data/Final모의고사/{grade}학년"
    matched_pdfs = []

    if os.path.isdir(folder):
        for f in os.listdir(folder):
            if f.lower().endswith(".pdf"):
                for num in unit_numbers:
                    if f"{num}단원" in f:
                        matched_pdfs.append(os.path.join(folder, f))

    # Create empty PDF if nothing found
    merger = PdfMerger()
    if matched_pdfs:
        for p in matched_pdfs:
            merger.append(p)

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
