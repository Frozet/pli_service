import io
import logging
import os
import re
import stat
import warnings
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from diagnostic_data import FormError

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_ATTACHMENTS_PER_KIND = 8
MAX_IMAGE_PIXELS = 20_000_000
MAX_PDF_PAGES = 20
IMAGE_FORMATS = {"PNG": ("png", "image/png"), "JPEG": ("jpg", "image/jpeg"), "GIF": ("gif", "image/gif")}
IMAGE_SUFFIXES = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".gif": "GIF"}
STORAGE_NAME = re.compile(r"[a-f0-9]{32}\.(?:png|jpg|gif|pdf)")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Upload:
    kind: str
    name: str
    media_type: str
    data: bytes


def validate_image(data, expected):
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data), formats=[expected]) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image pixel limit exceeded")
            image.verify()
        with Image.open(io.BytesIO(data), formats=[expected]) as image:
            image.load()


def read_pdf(data):
    if not data.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF header")
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted or not 1 <= len(reader.pages) <= MAX_PDF_PAGES:
        raise ValueError("Unsupported PDF")
    return reader


def validate_uploads(files):
    uploads = []
    for field, kind in (("photos", "photo"), ("slope_graph", "slope")):
        items = [file for file in files.getlist(field) if file.filename]
        if len(items) > MAX_ATTACHMENTS_PER_KIND:
            raise FormError(f"Допустимо до {MAX_ATTACHMENTS_PER_KIND} файлов каждого типа.")
        for file in items:
            suffix = Path(file.filename).suffix.lower()
            data = file.stream.read(MAX_FILE_BYTES + 1)
            if not data or len(data) > MAX_FILE_BYTES:
                raise FormError("Размер каждого вложения должен быть от 1 байта до 8 МБ.")
            try:
                if kind == "photo" and suffix in IMAGE_SUFFIXES:
                    image_format = IMAGE_SUFFIXES[suffix]
                    validate_image(data, image_format)
                    extension, media_type = IMAGE_FORMATS[image_format]
                elif kind == "slope" and suffix == ".pdf":
                    read_pdf(data)
                    extension, media_type = "pdf", "application/pdf"
                else:
                    raise FormError("Фотографии принимаются в PNG, JPEG или GIF, графики — в PDF.")
            except (UnidentifiedImageError, OSError, PdfReadError, ValueError, SyntaxError,
                    Image.DecompressionBombError, Image.DecompressionBombWarning, RecursionError) as error:
                if isinstance(error, FormError):
                    raise
                raise FormError("Один из файлов повреждён или превышает ограничения формата.") from error
            uploads.append(Upload(kind, f"{uuid4().hex}.{extension}", media_type, data))
    return uploads


class AttachmentStore:
    def __init__(self, root, legacy_root):
        self.root = Path(root).resolve()
        self.legacy_root = Path(legacy_root).resolve()

    def prepare(self):
        self.root.mkdir(mode=0o750, parents=True, exist_ok=True)

    def path(self, stored_name, *, legacy=False):
        root = self.legacy_root if legacy else self.root
        if (not stored_name or stored_name in (".", "..") or "/" in stored_name
                or "\\" in stored_name or "\0" in stored_name):
            raise ValueError("Invalid attachment path")
        if not legacy and not STORAGE_NAME.fullmatch(stored_name):
            raise ValueError("Invalid storage name")
        path = root / stored_name
        if path.is_symlink():
            raise ValueError("Symlink in attachment storage")
        return path

    def read(self, attachment):
        path = self.path(attachment["stored_name"], legacy=attachment["legacy"])
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Attachment is not a regular file")
            data = stream.read(MAX_FILE_BYTES + 1)
        if not data or len(data) > MAX_FILE_BYTES:
            raise ValueError("Unsupported stored file length")
        return data

    def write(self, uploads, written):
        for upload in uploads:
            path = self.path(upload.name)
            with path.open("xb") as file:
                written.append(path)
                file.write(upload.data)
                file.flush()
                os.fsync(file.fileno())
        if uploads:
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)

    def discard(self, written):
        for path in written:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not clean up uncommitted attachment %s", path.name)

    def drain_deletions(self, db):
        with db.transaction() as cursor:
            cursor.execute("""
                SELECT stored_name FROM pending_file_deletions ORDER BY stored_name LIMIT 200
                FOR UPDATE SKIP LOCKED
            """)
            for row in cursor.fetchall():
                name = row["stored_name"]
                try:
                    self.path(name).unlink(missing_ok=True)
                except (OSError, ValueError):
                    logger.exception("Could not delete attachment %s", name)
                    continue
                cursor.execute("DELETE FROM pending_file_deletions WHERE stored_name = %s", (name,))


def remove_attachments(cursor, diagnostic_id, removed):
    for attachment in removed:
        cursor.execute("DELETE FROM diagnostic_attachments WHERE diagnostic_id = %s AND id = %s",
                       (diagnostic_id, attachment["id"]))
        if not attachment["legacy"]:
            cursor.execute("INSERT INTO pending_file_deletions (stored_name) VALUES (%s) ON CONFLICT DO NOTHING",
                           (attachment["stored_name"],))


def add_attachments(cursor, diagnostic_id, uploads):
    cursor.executemany("""
        INSERT INTO diagnostic_attachments (diagnostic_id, kind, stored_name, media_type)
        VALUES (%s, %s, %s, %s)
    """, [(diagnostic_id, upload.kind, upload.name, upload.media_type) for upload in uploads])
