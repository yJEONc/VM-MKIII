from flask import Flask, render_template, request, send_file
import os
import io
import re
from PyPDF2 import PdfMerger

app = Flask(__name__)

DATA_FOLDER = "data"


def sort_by_number(name):
    nums = re.findall(r'\d+', name)
    return tuple(map(int, nums)) if nums else (9999,)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/merge", methods=["POST"])
def merge():
    grade = request.form.get("grade")          # 1학년 / 2학년 / 3학년
    exam_type = request.form.get("exam_type")  # 서술형 / 최다빈출 / Final모의고사
    units = request.form.getlist("units")      # 선택된 단원들

    base_path = os.path.join(DATA_FOLDER, exam_type, grade)

    if not os.path.exists(base_path):
        return "해당 경로가 존재하지 않습니다.", 404

    merger = PdfMerger()
    added = False

    for unit in sorted(units, key=sort_by_number):
        unit_path = os.path.join(base_path, unit)
        if not os.path.exists(unit_path):
            continue

        pdf_files = sorted(
            [f for f in os.listdir(unit_path) if f.lower().endswith(".pdf")],
            key=sort_by_number
        )

        for pdf in pdf_files:
            merger.append(os.path.join(unit_path, pdf))
            added = True

    if not added:
        return "병합할 PDF 파일이 없습니다.", 400

    output = io.BytesIO()
    merger.write(output)
    merger.close()
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f"{grade}_{exam_type}_merged.pdf",
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
