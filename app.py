import os
import json
from flask import Flask, request, jsonify, render_template, send_file
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from PyPDF2 import PdfMerger
import io
import re

app = Flask(__name__)

cached_end_data = []
GOOGLE_SHEET_ID = "1rsplfNq4e7d-nrp-Wlg1Mn9dsgjAcNn49yPQDXdzwg8"
END_RANGE = "end!A:D"

def get_google_service():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json is None:
        raise RuntimeError("GOOGLE_CREDENTIALS environment variable not set")

    info = json.loads(creds_json)
    creds = Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    service = build("sheets", "v4", credentials=creds)
    return service.spreadsheets()

def load_end_sheet_data():
    global cached_end_data
    try:
        service = get_google_service()
        result = service.values().get(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=END_RANGE
        ).execute()
        values = result.get("values", [])
        cached_end_data = values[1:]
        print("End sheet cached successfully.")
    except Exception as e:
        print("Failed to load end sheet:", e)

with app.app_context():
    load_end_sheet_data()

def extract_title_from_filename(filename):
    m = re.search(r"\d-\d\.(.+?)\(", filename)
    if m:
        return m.group(1)
    return filename

def find_pdf_files(base_dir, grade, unit_code):
    folder_path = os.path.join(base_dir, grade)
    if not os.path.isdir(folder_path):
        return []
    matches = []
    for f in os.listdir(folder_path):
        if f.endswith(".pdf") and unit_code in f:
            matches.append(os.path.join(folder_path, f))
    return matches

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/end_data")
def api_end_data():
    return jsonify(cached_end_data)

@app.route("/reload", methods=["POST"])
def api_reload():
    load_end_sheet_data()
    return jsonify({"status": "updated"})

@app.route("/api/preview_units", methods=["POST"])
def preview_units():
    data = request.get_json()
    grade = data["grade"]
    school = data["school"]
    filtered = [
        row for row in cached_end_data
        if row[1] == grade and row[2] == school
    ]
    result = []
    for ts, g, s, units in filtered:
        unit_list = units.split(",")
        for u in unit_list:
            result.append({"unit": u})
    return jsonify(result)

@app.route("/merge/최다빈출", methods=["POST"])
def merge_chodata():
    data = request.get_json()
    grade = data["grade"]
    school = data["school"]
    units = data["units"]
    files_to_merge = []
    for u in units:
        pdfs = find_pdf_files("./data/최다빈출", grade + "학년", u)
        files_to_merge.extend(pdfs)
    if not files_to_merge:
        return jsonify({"error": "자료 없음"}), 400
    merger = PdfMerger()
    for f in files_to_merge:
        merger.append(f)
    mem = io.BytesIO()
    merger.write(mem)
    merger.close()
    mem.seek(0)
    filename = f"{school}_{grade}학년_최다빈출.pdf"
    return send_file(mem, download_name=filename, as_attachment=True)

@app.route("/merge/서술형", methods=["POST"])
def merge_descriptive():
    data = request.get_json()
    grade = data["grade"]
    school = data["school"]
    units = data["units"]
    files_to_merge = []
    for u in units:
        pdfs = find_pdf_files("./data/서술형", grade + "학년", u)
        files_to_merge.extend(pdfs)
    if not files_to_merge:
        return jsonify({"error": "자료 없음"}), 400
    merger = PdfMerger()
    for f in files_to_merge:
        merger.append(f)
    mem = io.BytesIO()
    merger.write(mem)
    merger.close()
    mem.seek(0)
    filename = f"{school}_{grade}학년_서술형.pdf"
    return send_file(mem, download_name=filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
