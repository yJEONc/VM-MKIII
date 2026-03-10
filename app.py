from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
import os, io, re, json, time
from threading import Lock
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from PyPDF2 import PdfMerger

SPREADSHEET_ID = "1rsplfNq4e7d-nrp-Wlg1Mn9dsgjAcNn49yPQDXdzwg8"
SHEET_SCHOOL = "class+"
SHEET_END = "end"
SHEET_UNITS = "units"
GOOGLE_ENV = "GOOGLE_CREDENTIALS"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

PUBLIC_PATHS = {"/login", "/logout"}


@app.before_request
def require_login():
    path = request.path

    # 정적 파일은 허용
    if path.startswith("/static/"):
        return None

    # 로그인/로그아웃 페이지는 허용
    if path in PUBLIC_PATHS:
        return None

    # 로그인 안 했으면 차단
    if not session.get("logged_in"):
        if path.startswith("/api/"):
            return jsonify({"error": "unauthorized"}), 401
        return redirect(url_for("login"))


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


def parse_science_date(text):
    """
    S열(과학시험일) 정렬용
    우선순위 1: 가장 빠른 날짜
    지원 예:
    2026-04-30
    2026.04.30
    2026/04/30
    4/30
    4-30
    """
    text = (text or "").strip()
    if not text:
        return (9999, 12, 31)

    # YYYY-MM-DD / YYYY.MM.DD / YYYY/MM/DD
    m = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', text)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # MM/DD 또는 MM-DD
    m = re.search(r'(\d{1,2})[./-](\d{1,2})', text)
    if m:
        return (9999, int(m.group(1)), int(m.group(2)))

    return (9999, 12, 31)


def parse_exam_period(text):
    """
    R열(시험기간) 정렬용
    우선순위 2: 시험기간의 시작일이 빠른 순
    예:
    4/30~5/1
    4/22-4/23
    4.22~4.23
    """
    text = (text or "").strip()
    if not text:
        return (99, 99)

    m = re.search(r'(\d{1,2})[./-](\d{1,2})', text)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    return (99, 99)


def school_sort_key(science_date, exam_period, school_name):
    return (
        parse_science_date(science_date),   # 1순위: 과학시험일
        parse_exam_period(exam_period),     # 2순위: 시험기간 시작일
        school_name or ""                   # 3순위: 학교명
    )


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

    # SCHOOL LIST SOURCE: class+!I2:S
    # I = 현재 학교
    # R = 시험기간
    # S = 과학시험일
    school_res = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_SCHOOL}!I2:S"
    ).execute()
    school_rows = school_res.get("values", [])

    # 학교명별로 가장 빠른 (과학시험일, 시험기간) 한 건만 남김
    best_by_school = {}

    for row in school_rows:
        # I~S 범위 인덱스
        # I=0, J=1, K=2, L=3, M=4, N=5, O=6, P=7, Q=8, R=9, S=10
        school_name = row[0].strip() if len(row) > 0 and row[0] else ""
        exam_period = row[9].strip() if len(row) > 9 and row[9] else ""
        science_date = row[10].strip() if len(row) > 10 and row[10] else ""

        if not school_name:
            continue

        current_key = school_sort_key(science_date, exam_period, school_name)

        if school_name not in best_by_school:
            best_by_school[school_name] = {
                "school": school_name,
                "science_date": science_date,
                "exam_period": exam_period,
                "sort_key": current_key
            }
        else:
            if current_key < best_by_school[school_name]["sort_key"]:
                best_by_school[school_name] = {
                    "school": school_name,
                    "science_date": science_date,
                    "exam_period": exam_period,
                    "sort_key": current_key
                }

    school_list = [
        item["school"]
        for item in sorted(best_by_school.values(), key=lambda x: x["sort_key"])
    ]

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


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    password = request.form.get("password", "")
    real = os.getenv("APP_PASSWORD", "")

    if real and password == real:
        session["logged_in"] = True
        return redirect(url_for("index"))

    return render_template("login.html", error="비밀번호가 올바르지 않습니다.")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


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
        codes = read_units_codes(grade, sch)
        school_codes[sch] = codes
        all_codes.update(codes)

    # 단원명 매핑은 grade에 대해 한 번만
    name_map = get_unit_name_map(grade, list(all_codes))

    # 학교별 필요한 것만 반환
    out = {}
    for sch, codes in school_codes.items():
        out[sch] = {
            "codes": codes,
            "names": {c: name_map.get(c, "") for c in codes}
        }

    return jsonify(out)


# ===== 수동 캐시 갱신 =====
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
