from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
import os, io, re, json, time
from threading import Lock
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from PyPDF2 import PdfMerger

SPREADSHEET_ID = "1rsplfNq4e7d-nrp-Wlg1Mn9dsgjAcNn49yPQDXdzwg8"
SHEET_SCHOOL = "school"
SHEET_END = "end"
SHEET_UNITS = "units"
GOOGLE_ENV = "GOOGLE_CREDENTIALS"

app = Flask(__name__)

# =========================
# Cache (END/UNITS/SCHOOL)
# =========================
CACHE_LOCK = Lock()
CACHE = {
    "end_rows": None,     # list[list[str]]
    "units_rows": None,   # list[list[str]]
    "school_list": None,  # list[str]
    "loaded_at": None     # float unix time
}

def get_service():
    info = json.loads(os.getenv(GOOGLE_ENV))
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build("sheets", "v4", credentials=creds)

def refresh_cache():
    """
    Load all required sheet ranges once and keep in memory.
    This function MUST be called inside CACHE_LOCK.
    """
    service = get_service()

    # END: A2:D
    end_res = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_END}!A2:D"
    ).execute()
    end_rows = end_res.get("values", [])

    # UNITS: A2:C
    units_res = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_UNITS}!A2:C"
    ).execute()
    units_rows = units_res.get("values", [])

    # SCHOOL: A2:A
    school_res = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_SCHOOL}!A2:A"
    ).execute()
    school_rows = school_res.get("values", [])
    school_list = [v[0] for v in school_rows if v]

    CACHE["end_rows"] = end_rows
    CACHE["units_rows"] = units_rows
    CACHE["school_list"] = school_list
    CACHE["loaded_at"] = time.time()

def ensure_cache():
    """
    Lazy init cache on first use.
    """
    with CACHE_LOCK:
        if CACHE["end_rows"] is None or CACHE["units_rows"] is None or CACHE["school_list"] is None:
            refresh_cache()

# =========================
# Data Access (Cache-based)
# =========================
def read_school_list():
    ensure_cache()
    return CACHE["school_list"]

def read_units_codes(grade, school):
    ensure_cache()
    rows = CACHE["end_rows"]
    for r in rows:
        if len(r) >= 4 and str(r[1]) == str(grade) and r[2] == school:
            return [u.strip() for u in r[3].split(",") if u.strip()]
    return []

def read_grade_schools(grade):
    ensure_cache()
    rows = CACHE["end_rows"]
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
    ensure_cache()
    rows = CACHE["units_rows"]
    codes_set = set(codes)
    mapping = {}
    for r in rows:
        if len(r) >= 3 and str(r[0]) == str(grade) and r[1] in codes_set:
            mapping[r[1]] = r[2]
    return mapping

# =========================
# PDF Helpers
# =========================
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

# =========================
# Routes
# =========================
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

@app.route("/api/bundle_units", methods=["POST"])
def api_bundle_units():
    d = request.json
    grade = str(d["grade"])
    schools = d.get("schools", [])
    if not schools:
        return jsonify({})

    # 학교별 codes 수집
    school_codes = {}
    all_codes = set()

    for sch in schools:
        codes = read_units_codes(grade, sch)  # ✅ 이미 캐시 기반
        school_codes[sch] = codes
        all_codes.update(codes)

    # 단원명 매핑은 grade에 대해 "한 번만"
    name_map = get_unit_name_map(grade, list(all_codes))  # ✅ 캐시 기반

    # 학교별로 필요한 것만 잘라서 내려주기
    out = {}
    for sch, codes in school_codes.items():
        out[sch] = {
            "codes": codes,
            "names": {c: name_map.get(c, "") for c in codes}
        }

    return jsonify(out)


# ===== 수동 캐시 갱신(추가) =====
@app.route("/api/refresh_cache", methods=["POST"])
def api_refresh_cache():
    with CACHE_LOCK:
        refresh_cache()
        loaded_at = CACHE["loaded_at"]
    return jsonify({"ok": True, "loaded_at": loaded_at})

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
    if not os.path.isdir(folder):
        return jsonify({"error": "folder_not_found", "folder": folder}), 404

    merger = PdfMerger()
    appended = 0

    for n in nums:
        if grade == "1" and n == 1:
            continue
        pat = re.compile(rf"{n}\s*단원")
        matched = False
        for f in os.listdir(folder):
            if pat.search(f):
                merger.append(os.path.join(folder, f))
                appended += 1
                matched = True
                break
        # matched=False면 해당 단원 파일이 없는 것 → 그냥 스킵(기존 로직 유지)

    if appended == 0:
        return jsonify({"error": "no_files"}), 404

    buf = io.BytesIO()
    merger.write(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f'{grade}학년_{d["school"]}_FINAL모의고사.pdf',
        mimetype="application/pdf"
    )

# ===== 오투 모의고사 (기존 추가 기능 유지) =====
@app.route("/api/merge_otoo", methods=["POST"])
def api_merge_otoo():
    d = request.json
    grade = str(d["grade"])
    units = read_units_codes(grade, d["school"])
    nums = sorted({int(u.split("-")[0]) for u in units if "-" in u})

    folder = f"data/오투모의고사/{grade}학년"
    if not os.path.isdir(folder):
        return jsonify({"error": "folder_not_found", "folder": folder}), 404

    merger = PdfMerger()
    appended = 0

    for n in nums:
        if grade == "1" and n == 1:
            continue
        pat = re.compile(rf"{n}\s*단원")
        for f in os.listdir(folder):
            if pat.search(f):
                merger.append(os.path.join(folder, f))
                appended += 1
                break

    if appended == 0:
        return jsonify({"error": "no_files"}), 404

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
