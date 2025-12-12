
from flask import Flask, render_template, request, send_file
import os, io, re
from PyPDF2 import PdfMerger

app = Flask(__name__)
DATA_FOLDER = "data"

def sort_by_number(name):
    nums = re.findall(r'\d+', name)
    return tuple(map(int, nums)) if nums else (9999,)

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/merge', methods=['POST'])
def merge():
    grade = request.form['grade']
    exam_type = request.form['exam_type']  # 서술형 / 최다빈출 / Final모의고사
    units = request.form.getlist('units')

    base_path = os.path.join(DATA_FOLDER, exam_type, grade)
    merger = PdfMerger()

    for unit in sorted(units, key=sort_by_number):
        unit_path = os.path.join(base_path, unit)
        if not os.path.exists(unit_path):
            continue
        files = sorted(
            [f for f in os.listdir(unit_path) if f.endswith(".pdf")],
            key=sort_by_number
        )
        for f in files:
            merger.append(os.path.join(unit_path, f))

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
    app.run(debug=True)
