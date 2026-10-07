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
