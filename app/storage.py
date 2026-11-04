import hashlib
import os
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

MAX_BYTES = 10 * 1024 * 1024
# extension -> (required magic bytes or None, mime that WE choose; the client's mime is ignored)
ALLOWED = {
    "pdf": (b"%PDF-", "application/pdf"),
    "png": (b"\x89PNG\r\n\x1a\n", "image/png"),
    "jpg": (b"\xff\xd8\xff", "image/jpeg"),
    "jpeg": (b"\xff\xd8\xff", "image/jpeg"),
    "docx": (b"PK\x03\x04", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "txt": (None, "text/plain"),
}


class UploadError(ValueError):
    pass


def validate_upload(file_storage):
    name = secure_filename(file_storage.filename or "")
    if not name or "." not in name:
        raise UploadError("invalid file name")
    ext = name.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED:
        raise UploadError("file type not allowed")
    data = file_storage.read(MAX_BYTES + 1)
    if not data:
        raise UploadError("empty file")
    if len(data) > MAX_BYTES:
        raise UploadError("file too large")
    magic, mime = ALLOWED[ext]
    if magic is not None and not data.startswith(magic):
        raise UploadError("file content does not match its extension")
    if ext == "txt":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise UploadError("text file is not valid UTF-8")
        if b"\x00" in data:
            raise UploadError("text file contains binary data")
    return name, mime, data


def save_bytes(data: bytes):
    """Write under a server-generated random name, outside any web-served folder."""
    directory = current_app.config["UPLOAD_DIR"]
    os.makedirs(directory, exist_ok=True)
    storage_name = uuid.uuid4().hex
    with open(os.path.join(directory, storage_name), "xb") as f:
        f.write(data)
    return storage_name, hashlib.sha256(data).hexdigest()


def path_for(storage_name: str) -> str:
    directory = os.path.realpath(current_app.config["UPLOAD_DIR"])
    path = os.path.realpath(os.path.join(directory, storage_name))
    if os.path.dirname(path) != directory:       # belt and braces against path tricks
        raise ValueError("bad storage path")
    return path