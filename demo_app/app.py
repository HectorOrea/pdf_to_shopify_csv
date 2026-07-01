import hashlib
import hmac
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from demo_app.my_script import process_pdf_to_csv

from dotenv import load_dotenv

"""
This initializes the app and defines the backend. The decorators specify what 
type of http request causes that function to run
"""


APP_DIR = Path(__file__).resolve().parent
load_dotenv()
load_dotenv(APP_DIR / ".env")

DASHBOARD_FILE = APP_DIR / "home-index.html"
LOGIN_FILE = APP_DIR / "login-index.html"
SHOPIFY_TOOL_FILE = APP_DIR / "shopify-index.html"
SUM_TOOL_FILE = APP_DIR / "sum-index.html"
RUNS_DIR = APP_DIR / "runs"
AUTH_COOKIE_NAME = "moda_auth"
AUTH_MESSAGE = b"moda-internal-tools"

app = FastAPI(title="Moda Demo App")


class SumRequest(BaseModel):
    a: float
    b: float


def _app_password() -> str:
    password = os.environ.get("MODA_APP_PASSWORD")
    if not password:
        raise RuntimeError("Missing required environment variable: MODA_APP_PASSWORD")
    return password


def _auth_token() -> str:
    secret = os.environ.get("MODA_APP_SESSION_SECRET") or _app_password()
    return hmac.new(secret.encode("utf-8"), AUTH_MESSAGE, hashlib.sha256).hexdigest()


def _is_authenticated(request: Request) -> bool:
    cookie_value = request.cookies.get(AUTH_COOKIE_NAME)
    return bool(cookie_value) and hmac.compare_digest(cookie_value, _auth_token())


def _require_api_auth(request: Request) -> None:
    if not _is_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required.")


def _protected_html(request: Request, html_file: Path) -> Response:
    if not _is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(html_file.read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/login", response_class=HTMLResponse)
def login_page() -> str:
    return LOGIN_FILE.read_text(encoding="utf-8")


@app.post("/login")
def login(password: str = Form(...)) -> Response:
    if not hmac.compare_digest(password, _app_password()):
        html = LOGIN_FILE.read_text(encoding="utf-8").replace(
            '<div id="error"></div>',
            '<div id="error">Incorrect password.</div>',
        )
        return HTMLResponse(html, status_code=401)

    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        AUTH_COOKIE_NAME,
        _auth_token(),
        httponly=True,
        samesite="lax",
        secure=os.environ.get("MODA_COOKIE_SECURE", "").lower() == "true",
        max_age=60 * 60 * 12,
    )
    return response


@app.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(AUTH_COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> Response:
    return _protected_html(request, DASHBOARD_FILE)


@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/dashbaord", response_class=HTMLResponse)
def dashboard(request: Request) -> Response:
    return _protected_html(request, DASHBOARD_FILE)


@app.get("/shopify_tool", response_class=HTMLResponse)
def shopify_tool(request: Request) -> Response:
    return _protected_html(request, SHOPIFY_TOOL_FILE)


@app.get("/sum_tool", response_class=HTMLResponse)
def sum_tool(request: Request) -> Response:
    return _protected_html(request, SUM_TOOL_FILE)


@app.post("/sum")
def sum_numbers(payload: SumRequest, request: Request) -> dict[str, float]:
    _require_api_auth(request)
    return {"sum": payload.a + payload.b}


@app.post("/process")
async def process_pdf(request: Request, pdf: UploadFile = File(...)) -> FileResponse: # UploadFile type is a FastAPI convention that correctly parses the FormData object parsed and posted here
    _require_api_auth(request)
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
