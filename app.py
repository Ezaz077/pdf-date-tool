import os
import uuid
import tempfile
from pathlib import Path

import fitz
from flask import Flask, render_template, request, jsonify, send_file, session


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "pdf-editor-secret-key"
)

MAX_FILE_SIZE = 20 * 1024 * 1024

BASE_DIR = Path(tempfile.gettempdir()) / "pdf_editor"
BASE_DIR.mkdir(parents=True, exist_ok=True)


def get_job_dir():
    job_id = session.get("job_id")

    if not job_id:
        job_id = str(uuid.uuid4())
        session["job_id"] = job_id

    folder = BASE_DIR / job_id
    folder.mkdir(parents=True, exist_ok=True)

    return folder


def original_pdf():
    return get_job_dir() / "original.pdf"


def edited_pdf():
    return get_job_dir() / "edited.pdf"


def extract_text(pdf_path):

    doc = fitz.open(pdf_path)

    pages = []

    for page_number, page in enumerate(doc):

        page_data = {
            "page": page_number,
            "width": page.rect.width,
            "height": page.rect.height,
            "spans": []
        }

        blocks = page.get_text("dict")["blocks"]

        for block in blocks:

            if "lines" not in block:
                continue

            for line in block["lines"]:

                for span in line["spans"]:

                    text = span.get("text", "")

                    if not text.strip():
                        continue

                    bbox = span["bbox"]

                    page_data["spans"].append({
                        "text": text,
                        "bbox": [
                            bbox[0],
                            bbox[1],
                            bbox[2],
                            bbox[3]
                        ],
                        "font_size": span.get("size", 10)
                    })

        pages.append(page_data)

    doc.close()

    return pages


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():

    if "file" not in request.files:
        return jsonify({
            "success": False,
            "error": "No PDF selected."
        }), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({
            "success": False,
            "error": "No file selected."
        }), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({
            "success": False,
            "error": "Only PDF files are allowed."
        }), 400

    data = file.read()

    if len(data) > MAX_FILE_SIZE:
        return jsonify({
            "success": False,
            "error": "Maximum file size is 20 MB."
        }), 400

    path = original_pdf()

    with open(path, "wb") as f:
        f.write(data)

    try:

        doc = fitz.open(path)

        if doc.is_encrypted:
            doc.close()

            return jsonify({
                "success": False,
                "error": "Password protected PDFs are not supported."
            }), 400

        page_count = len(doc)

        doc.close()

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    old = edited_pdf()

    if old.exists():
        old.unlink()

    pages = extract_text(path)

    return jsonify({
        "success": True,
        "page_count": page_count,
        "pages": pages
    })


@app.route("/page/<int:page_number>")
def page_image(page_number):

    path = original_pdf()

    if not path.exists():
        return "PDF not found.", 404

    doc = fitz.open(path)

    if page_number < 0 or page_number >= len(doc):
        doc.close()
        return "Page not found.", 404

    page = doc[page_number]

    matrix = fitz.Matrix(1.5, 1.5)

    pix = page.get_pixmap(
        matrix=matrix,
        alpha=False
    )

    image_path = get_job_dir() / f"page_{page_number}.png"

    pix.save(str(image_path))

    doc.close()

    return send_file(
        image_path,
        mimetype="image/png"
    )


@app.route("/edit", methods=["POST"])
def edit():

    path = original_pdf()

    if not path.exists():
        return jsonify({
            "success": False,
            "error": "No PDF uploaded."
        }), 400

    data = request.get_json()

    try:

        page_number = int(data["page"])
        bbox = data["bbox"]
        new_text = str(data["new_text"])
        font_size = float(data.get("font_size", 10))

    except Exception:

        return jsonify({
            "success": False,
            "error": "Invalid edit data."
        }), 400

    doc = fitz.open(path)

    page = doc[page_number]

    rect = fitz.Rect(
        float(bbox[0]),
        float(bbox[1]),
        float(bbox[2]),
        float(bbox[3])
    )

    cover = fitz.Rect(
        rect.x0 - 1,
        rect.y0 - 1,
        rect.x1 + 1,
        rect.y1 + 1
    )

    page.draw_rect(
        cover,
        color=(1, 1, 1),
        fill=(1, 1, 1),
        overlay=True
    )

    page.insert_textbox(
        rect,
        new_text,
        fontsize=font_size,
        fontname="helv",
        color=(0, 0, 0),
        overlay=True
    )

    output = edited_pdf()

    doc.save(
        str(output),
        garbage=4,
        deflate=True
    )

    doc.close()

    return jsonify({
        "success": True
    })


@app.route("/reset", methods=["POST"])
def reset():

    output = edited_pdf()

    if output.exists():
        output.unlink()

    path = original_pdf()

    if not path.exists():
        return jsonify({
            "success": False,
            "error": "No PDF uploaded."
        }), 400

    pages = extract_text(path)

    return jsonify({
        "success": True,
        "pages": pages
    })


@app.route("/download")
def download():

    output = edited_pdf()
    original = original_pdf()

    if output.exists():
        path = output
    elif original.exists():
        path = original
    else:
        return "No PDF available.", 404

    return send_file(
        path,
        as_attachment=True,
        download_name="edited.pdf",
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
