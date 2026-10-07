import os
import uuid
import tempfile
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    session,
)
import fitz


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pdf-editor-secret-key")

MAX_FILE_SIZE = 20 * 1024 * 1024

BASE_DIR = Path(tempfile.gettempdir()) / "pdf_text_editor"
BASE_DIR.mkdir(parents=True, exist_ok=True)


def get_job_dir():
    job_id = session.get("job_id")

    if not job_id:
        job_id = str(uuid.uuid4())
        session["job_id"] = job_id

    job_dir = BASE_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    return job_dir


def get_pdf_path():
    return get_job_dir() / "original.pdf"


def get_edited_pdf_path():
    return get_job_dir() / "edited.pdf"


def extract_spans(pdf_path):
    doc = fitz.open(pdf_path)

    pages = []

    for page_number, page in enumerate(doc):
        page_width = page.rect.width
        page_height = page.rect.height

        blocks = page.get_text("dict")["blocks"]

        spans = []

        for block in blocks:
            if "lines" not in block:
                continue

            for line in block["lines"]:
                for span in line["spans"]:

                    text = span.get("text", "")

                    if not text.strip():
                        continue

                    bbox = span["bbox"]

                    spans.append({
                        "text": text,
                        "bbox": [
                            bbox[0],
                            bbox[1],
                            bbox[2],
                            bbox[3]
                        ],
                        "font_size": span.get("size", 10),
                        "font": span.get("font", ""),
                        "page_width": page_width,
                        "page_height": page_height
                    })

        pages.append({
            "page": page_number,
            "width": page_width,
            "height": page_height,
            "spans": spans
        })

    doc.close()

    return pages


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():

    if "file" not in request.files:
        return jsonify({
            "success": False,
            "error": "No file uploaded."
        }), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({
            "success": False,
            "error": "Please select a PDF."
        }), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({
            "success": False,
            "error": "Only PDF files are supported."
        }), 400

    data = file.read()

    if len(data) > MAX_FILE_SIZE:
        return jsonify({
            "success": False,
            "error": "Maximum file size is 20 MB."
        }), 400

    pdf_path = get_pdf_path()

    with open(pdf_path, "wb") as f:
        f.write(data)

    try:
        doc = fitz.open(pdf_path)

        if doc.is_encrypted:
            doc.close()

            return jsonify({
                "success": False,
                "error": "Password-protected PDFs are not supported."
            }), 400

        page_count = len(doc)
        doc.close()

    except Exception as e:

        return jsonify({
            "success": False,
            "error": f"Invalid PDF: {str(e)}"
        }), 400

    edited_path = get_edited_pdf_path()

    if edited_path.exists():
        edited_path.unlink()

    pages = extract_spans(pdf_path)

    return jsonify({
        "success": True,
        "pages": pages,
        "page_count": page_count
    })


@app.route("/page/<int:page_number>")
def page_image(page_number):

    pdf_path = get_pdf_path()

    if not pdf_path.exists():
        return "PDF not found.", 404

    doc = fitz.open(pdf_path)

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
def edit_pdf():

    pdf_path = get_pdf_path()

    if not pdf_path.exists():
        return jsonify({
            "success": False,
            "error": "No PDF uploaded."
        }), 400

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "error": "Invalid request."
        }), 400

    try:
        page_number = int(data["page"])
        bbox = data["bbox"]
        new_text = str(data["new_text"])

        font_size = float(
            data.get("font_size", 10)
        )

    except Exception:
        return jsonify({
            "success": False,
            "error": "Invalid edit data."
        }), 400

    doc = fitz.open(pdf_path)

    if page_number < 0 or page_number >= len(doc):
        doc.close()

        return jsonify({
            "success": False,
            "error": "Invalid page."
        }), 400

    page = doc[page_number]

    rect = fitz.Rect(
        float(bbox[0]),
        float(bbox[1]),
        float(bbox[2]),
        float(bbox[3])
    )

    # Slight padding
    cover_rect = fitz.Rect(
        rect.x0 - 1,
        rect.y0 - 1,
        rect.x1 + 1,
        rect.y1 + 1
    )

    # Cover existing text area
    page.draw_rect(
        cover_rect,
        color=(1, 1, 1),
        fill=(1, 1, 1),
        overlay=True
    )

    # Insert replacement text
    page.insert_textbox(
        rect,
        new_text,
        fontsize=font_size,
        fontname="helv",
        color=(0, 0, 0),
        align=fitz.TEXT_ALIGN_LEFT,
        overlay=True
    )

    edited_path = get_edited_pdf_path()

    doc.save(
        str(edited_path),
        garbage=4,
        deflate=True
    )

    doc.close()

    return jsonify({
        "success": True
    })


@app.route("/reset", methods=["POST"])
def reset_pdf():

    edited_path = get_edited_pdf_path()

    if edited_path.exists():
        edited_path.unlink()

    pdf_path = get_pdf_path()

    if not pdf_path.exists():
        return jsonify({
            "success": False,
            "error": "No PDF uploaded."
        }), 400

    pages = extract_spans(pdf_path)

    return jsonify({
        "success": True,
        "pages": pages
    })


@app.route("/download")
def download_pdf():

    edited_path = get_edited_pdf_path()
    original_path = get_pdf_path()

    if edited_path.exists():
        file_path = edited_path
    elif original_path.exists():
        file_path = original_path
    else:
        return "No PDF available.", 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name="edited.pdf",
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
