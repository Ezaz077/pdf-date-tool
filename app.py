from flask import Flask, render_template, request, send_file
from pypdf import PdfReader
from datetime import datetime
from io import BytesIO
import os

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():

    uploaded_file = request.files.get("pdf_file")

    registration_date = request.form.get("registration_date")
    journey_date = request.form.get("journey_date")

    if not uploaded_file:
        return "No PDF uploaded.", 400

    if not registration_date:
        return "Web Registration Date is required.", 400

    if not journey_date:
        return "Expected Date of Journey is required.", 400

    if not uploaded_file.filename.lower().endswith(".pdf"):
        return "Please upload a PDF file.", 400

    try:
        reader = PdfReader(uploaded_file)

        page_count = len(reader.pages)

    except Exception:
        return "The uploaded file is not a valid readable PDF.", 400

    try:
        reg_date = datetime.strptime(
            registration_date,
            "%Y-%m-%d"
        ).strftime("%d-%b-%Y").upper()

        journey = datetime.strptime(
            journey_date,
            "%Y-%m-%d"
        ).strftime("%d-%b-%Y").upper()

    except ValueError:
        return "Invalid date format.", 400

    declaration_date = reg_date

    report = f"""PDF DATE VALIDATION REPORT
================================

Original PDF filename:
{uploaded_file.filename}

PDF page count:
{page_count}

Selected Web Registration Date:
{reg_date}

Selected Expected Date of Journey:
{journey}

Declaration Date:
{declaration_date}

RULE:
Declaration Date = Web Registration Date

STATUS:
VALID

NOTE:
This report does not modify the uploaded PDF.
The original PDF remains unchanged.
"""

    report_file = BytesIO(report.encode("utf-8"))
    report_file.seek(0)

    safe_name = os.path.splitext(
        uploaded_file.filename
    )[0]

    report_name = f"{safe_name}_date_report.txt"

    return send_file(
        report_file,
        mimetype="text/plain",
        as_attachment=True,
        download_name=report_name
    )


if __name__ == "__main__":
    app.run()
