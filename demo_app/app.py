from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool

from demo_app.my_script import process_pdf_to_csv

from dotenv import load_dotenv

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
INDEX_FILE = APP_DIR / "index.html"
RUNS_DIR = APP_DIR / "runs"

app = FastAPI(title="Moda Demo App")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return INDEX_FILE.read_text(encoding="utf-8")


@app.post("/process")
async def process_pdf(pdf: UploadFile = File(...)) -> FileResponse:
    if pdf.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    run_id = uuid4().hex
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(pdf.filename or "uploaded.pdf").name
    input_path = run_dir / safe_name
    output_path = run_dir / "bulk-add.csv"

    file_bytes = await pdf.read()
    input_path.write_bytes(file_bytes)

    try:
        await run_in_threadpool(process_pdf_to_csv, input_path, output_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return FileResponse(
        output_path,
        media_type="text/csv",
        filename=f"{Path(safe_name).stem}_bulk-add.csv",
    )
