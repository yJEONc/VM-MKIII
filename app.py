
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

# ================= 기본 설정 =================

SPREADSHEET_ID = "1rsplfNq4e7d-nrp-Wlg1Mn9dsgjAcNn49yPQDXdzwg8"
END_SHEET_NAME = "end"
DATA_DIR = "data"
MATERIAL_TYPES = ["서술형", "최다빈출"]
GOOGLE_CREDENTIALS_ENV = "GOOGLE_CREDENTIALS"

app = Flask(__name__)

# 캐시: 서버 시작 시 1회 로드, /reload 로 갱신
END_CACHE: List[Dict[str, Any]] = []


# ================= 구글 시트 관련 =================

def get_sheets_service():
    """
    Render 환경에서 GOOGLE_CREDENTIALS 환경변수에 JSON 문자열로
    서비스 계정 키가 저장되어 있다고 가정.
    """
    cred_json = os.getenv(GOOGLE_CREDENTIALS_ENV)
    if not cred_json:
        raise RuntimeError(f"{GOOGLE_CREDENTIALS_ENV} 환경변수가 설정되지 않았습니다.")

    info = json.loads(cred_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    service = build("sheets", "v4", credentials=creds)
    return service


def fetch_end_data_from_google() -> List[Dict[str, Any]]:
    """
    end 시트에서 데이터 읽어오기
    컬럼: timestamp | grade | school | units(쉼표로 구분)
    """
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
        data.append(
            {
                "timestamp": timestamp_str,
                "grade": grade,
                "school": school,
                "units": units,
            }
        )
    return data


def load_end_cache():
    global END_CACHE
    try:
        END_CACHE = fetch_end_data_from_google()
        app.logger.info(f"Loaded end cache: {len(END_CACHE)} rows")
    except Exception as e:
        app.logger.error(f"Failed to load end cache: {e}")
        END_CACHE = []


# ================= 파일/타이틀 관련 =================

def grade_to_folder(grade: int) -> str:
    return f"{grade}학년"


def find_matching_files(material_type: str, grade: int, unit_code: str) -> List[str]:
    """
    자료 종류(서술형/최다빈출), 학년, 단원코드에 해당하는 파일 리스트 반환
    """
    grade_folder = grade_to_folder(grade)
    base_dir = os.path.join(DATA_DIR, material_type, grade_folder)
    if not os.path.isdir(base_dir):
        return []

    try:
        filenames = sorted(os.listdir(base_dir))
    except FileNotFoundError:
        return []

    pattern = re.compile(rf"\b{re.escape(unit_code)}\b")

    matched: List[str] = []
    for name in filenames:
        if not name.lower().endswith(".pdf"):
            continue
        if pattern.search(name):
            matched.append(os.path.join(base_dir, name))
    return matched


def extract_title_from_filename(filepath: str, unit_code: str) -> str:
    """
    파일명에서 '단원코드.제목(...' 패턴에서 제목만 추출
    예: '서술형 공략 2-1.생물의 구성(01) 중1.pdf' -> '생물의 구성'
    """
    base = os.path.basename(filepath)
    pattern = re.compile(rf"{re.escape(unit_code)}\.(.*?)\(")
    m = pattern.search(base)
    if m:
        return m.group(1).strip()
    return ""


# ================= 라우트 =================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/end_data", methods=["GET"])
def api_end_data():
    """
    캐시에 저장된 end 데이터를 그대로 반환
    """
    return jsonify(END_CACHE)


@app.route("/reload", methods=["POST"])
def reload_end_cache():
    """
    시험범위 업데이트 버튼에서 호출.
    Google Sheets에서 end 시트를 다시 읽어와 캐시를 갱신.
    """
    try:
        load_end_cache()
        return jsonify({"status": "ok", "rows": len(END_CACHE)})
    except Exception as e:
        app.logger.error(f"/reload error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/preview_units", methods=["POST"])
def api_preview_units():
    """
    선택된 학년/학교에 대해:
    - 캐시된 end 데이터에서 해당 row 찾기
    - 단원코드 + 제목(가능하면) + 자료 존재 여부 반환
    """
    req = request.get_json() or {}
    try:
        grade = int(req.get("grade"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_grade"}), 400
    school = req.get("school")
    if not school:
        return jsonify({"error": "invalid_school"}), 400

    entry = next((d for d in END_CACHE if d["grade"] == grade and d["school"] == school), None)
    if not entry:
        return jsonify({"error": "not_found"}), 404

    units_info = []
    for unit in entry["units"]:
        title = ""
        has_file = False

        # 서술형/최다빈출 둘 중 아무 폴더에서라도 제목 후보 찾기
        for material_type in MATERIAL_TYPES:
            files = find_matching_files(material_type, grade, unit)
            if files:
                has_file = True
                t = extract_title_from_filename(files[0], unit)
                if t:
                    title = t
                    break

        if not has_file:
            # A안: 자료가 없으면 (자료 없음)
            title = "(자료 없음)"
        elif not title:
            title = "(제목 없음)"

        units_info.append(
            {
                "code": unit,
                "title": title,
                "has_file": has_file,
            }
        )

    return jsonify(
        {
            "grade": grade,
            "school": school,
            "units": units_info,
        }
    )


@app.route("/merge/<material_type>", methods=["POST"])
def merge_material(material_type: str):
    """
    material_type: '서술형' 또는 '최다빈출'
    body: { grade: 1, school: "개성중학교" }
    """
    if material_type not in MATERIAL_TYPES:
        return jsonify({"error": "invalid_type"}), 400

    req = request.get_json() or {}
    try:
        grade = int(req.get("grade"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_grade"}), 400
    school = req.get("school")
    if not school:
        return jsonify({"error": "invalid_school"}), 400

    entry = next((d for d in END_CACHE if d["grade"] == grade and d["school"] == school), None)
    if not entry:
        return jsonify({"error": "not_found"}), 404

    units = entry["units"]
    merger = PdfMerger()
    total_files = 0

    for unit in units:
        files = find_matching_files(material_type, grade, unit)
        if not files:
            # A안: 파일 없으면 조용히 스킵
            continue
        for fpath in files:
            if os.path.exists(fpath):
                merger.append(fpath)
                total_files += 1

    if total_files == 0:
        return jsonify({"error": "no_files"}), 404

    buf = io.BytesIO()
    merger.write(buf)
    merger.close()
    buf.seek(0)

    today = datetime.now().strftime("%Y%m%d")
    filename = f"{school}_{grade}학년_{material_type}_{today}.pdf"

    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


# ================= 서버 시작 시 캐시 로드 =================

@app.before_first_request
def init_cache():
    load_end_cache()


if __name__ == "__main__":
    # 로컬 테스트용
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
