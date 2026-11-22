import base64
import logging
import subprocess
import sys
from io import BytesIO

from flask import current_app, render_template
from pypdf import PdfWriter
from pypdf.errors import PdfReadError

from attachments import read_pdf, validate_image
from diagnostic_data import MAX_DEFECTS, MAX_SPANS
from graph_generate import generate_diagnostic_plot

logger = logging.getLogger(__name__)
BROKEN_FILE_ERRORS = (OSError, ValueError, PdfReadError, RecursionError)


def data_uri(data, media_type):
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def graph_for(details):
    return render_diagnostic_graph(details["diagnostic"]["type"], details["wells_details"], details["problem_details"])


def render_diagnostic_graph(pipe_type, spans, defects):
    return generate_diagnostic_plot(
        pipe_type, spans[:MAX_SPANS], tuple(item.distance for item in defects[:MAX_DEFECTS]),
        truncated=len(spans) > MAX_SPANS or len(defects) > MAX_DEFECTS,
    )


def generate_report(details, store, current_date):
    photos, appendices = [], []
    missing = 0
    remaining_bytes = 32 * 1024 * 1024
    remaining_pages = 80
    for attachment in details["attachments"]:
        try:
            data = store.read(attachment)
            if len(data) > remaining_bytes:
                raise ValueError("Report attachments exceed byte budget")
            if attachment["kind"] == "photo":
                if attachment["legacy"]:
                    validate_image(data, attachment["media_type"].split("/")[1].upper())
                photos.append(data_uri(data, attachment["media_type"]))
            else:
                appendix = read_pdf(data)
                pages = len(appendix.pages)
                if pages > remaining_pages:
                    raise ValueError("Report appendices exceed page budget")
                with PdfWriter() as sanitized, BytesIO() as output:
                    sanitized.append(appendix, import_outline=False, excluded_fields=("/Annots", "/AA", "/B"))
                    sanitized.write(output)
                    appendices.append(output.getvalue())
                remaining_pages -= pages
            remaining_bytes -= len(data)
        except BROKEN_FILE_ERRORS:
            logger.warning("Attachment %s omitted from report", attachment["id"], exc_info=True)
            missing += 1
    html = render_template(
        "diagnostic_pdf.html", **details, photos_paths=photos, missing_files=missing,
        plot_image=data_uri(graph_for(details), "image/png"), current_date=current_date,
    )
    report = subprocess.run(
        [sys.executable, "-m", "pdf_report"], input=html.encode(),
        timeout=current_app.config["PDF_TIMEOUT"], capture_output=True, check=True,
    ).stdout
    with PdfWriter() as writer:
        writer.append(BytesIO(report), import_outline=False)
        for appendix in appendices:
            writer.append(BytesIO(appendix), import_outline=False)
        output = BytesIO()
        writer.write(output)
        output.seek(0)
        return output


def render_stdin():
    from weasyprint import HTML
    from weasyprint.urls import URLFetcher

    # Only data URIs emitted by the report template may be resolved.
    fetcher = URLFetcher(allowed_protocols={"data"}, timeout=2, allow_redirects=False)
    sys.stdout.buffer.write(HTML(string=sys.stdin.read(), url_fetcher=fetcher).write_pdf())


if __name__ == "__main__":
    render_stdin()
