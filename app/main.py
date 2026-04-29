from __future__ import annotations

from pathlib import Path
import asyncio
import time

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models import ChatRequest, ChatResponse, DirectoryChatRequest, FilePathChatRequest, HealthResponse, PrivacyMode
from app.services.audit_store import AuditSnapshotStore
from app.services.auth import APIKeyAuth
from app.services.cloud_llm import CloudLLMClient
from app.services.detectors import HybridPIIDetector
from app.services.file_parser import LocalFileParser, UnsupportedFileTypeError
from app.services.firewall import PrivacyFirewallService
from app.services.job_store import InMemoryJobStore
from app.services.local_llm import LocalLLMClient
from app.services.outbound_guard import OutboundPrivacyGuard
from app.services.privacy_logger import PrivacySafeLogger
from app.services.sanitizer import SmartSanitizer
from app.services.session_store import SessionPlaceholderStore
from app.services.web_search import SecureWebSearchClient
from starlette.responses import Response
from uuid import uuid4


settings = get_settings()
api_auth = APIKeyAuth(settings)
store = SessionPlaceholderStore(ttl_minutes=settings.session_ttl_minutes)
detector = HybridPIIDetector(enable_presidio=settings.enable_presidio)
sanitizer = SmartSanitizer(store)
local_llm = LocalLLMClient(settings)
cloud_llm = CloudLLMClient(settings)
web_search = SecureWebSearchClient(settings)
outbound_guard = OutboundPrivacyGuard(settings)
privacy_logger = PrivacySafeLogger(settings)
file_parser = LocalFileParser(max_directory_files=settings.max_directory_files)
job_store = InMemoryJobStore()
audit_store = AuditSnapshotStore(settings, Path(__file__).resolve().parent.parent)
firewall = PrivacyFirewallService(detector, sanitizer, local_llm, cloud_llm, web_search, outbound_guard, privacy_logger)

app = FastAPI(title="Local Privacy Firewall for LLMs", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.middleware("http")
async def privacy_safe_request_logging(request: Request, call_next) -> Response:
    request_id = uuid4().hex[:12]
    session_id = None
    if request.method == "GET":
        session_id = request.path_params.get("session_id")
    started_at = privacy_logger.request_started(
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        session_id=session_id,
    )
    try:
        response = await call_next(request)
    except Exception:
        privacy_logger.request_completed(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            status_code=500,
            started_at=started_at,
        )
        raise
    response.headers["X-Request-Id"] = request_id
    privacy_logger.request_completed(
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        status_code=response.status_code,
        started_at=started_at,
    )
    return response


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        local_llm_provider=settings.local_llm_provider,
        local_model=settings.local_llm_model,
        cloud_provider=settings.cloud_provider,
        cloud_model=settings.cloud_model,
        presidio_enabled=settings.enable_presidio,
        web_search_enabled=settings.enable_web_search,
        block_cloud_on_residual_risk=settings.block_cloud_on_residual_risk,
        max_outbound_prompt_chars=settings.max_outbound_prompt_chars,
        api_auth_enabled=settings.api_auth_enabled,
        admin_audit_access_enabled=settings.api_auth_enabled,
        audit_snapshots_enabled=audit_store.enabled(),
        privacy_logging_enabled=settings.privacy_logging_enabled,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, _: object = Depends(api_auth.require_user)) -> ChatResponse:
    try:
        response = await firewall.process(
            session_id=request.session_id,
            message=request.message,
            mode=request.mode,
            use_web_search=request.use_web_search,
        )
        audit_store.write(response)
        return response
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/chat/file", response_model=ChatResponse)
async def chat_file(
    session_id: str = Form(...),
    mode: PrivacyMode = Form(PrivacyMode.HYBRID),
    use_web_search: bool = Form(False),
    message: str = Form(""),
    file: UploadFile = File(...),
    _: object = Depends(api_auth.require_user),
) -> ChatResponse:
    try:
        parsed = await file_parser.parse_upload(file.filename or "upload.bin", await file.read())
        response = await firewall.process_file(
            session_id=session_id,
            parsed_file=parsed,
            mode=mode,
            use_web_search=use_web_search,
            message=message,
        )
        audit_store.write(response)
        return response
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/chat/path", response_model=ChatResponse)
async def chat_path(request: FilePathChatRequest, _: object = Depends(api_auth.require_user)) -> ChatResponse:
    try:
        parsed = file_parser.parse_path(request.path)
        response = await firewall.process_file(
            session_id=request.session_id,
            parsed_file=parsed,
            mode=request.mode,
            use_web_search=request.use_web_search,
            message=request.message,
        )
        audit_store.write(response)
        return response
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/chat/directory", response_model=ChatResponse)
async def chat_directory(request: DirectoryChatRequest, _: object = Depends(api_auth.require_user)) -> ChatResponse:
    try:
        parsed_files = file_parser.parse_directory(
            request.path,
            recursive=request.recursive,
            max_files=request.max_files,
        )
        response = await firewall.process_files(
            session_id=request.session_id,
            parsed_files=parsed_files,
            mode=request.mode,
            use_web_search=request.use_web_search,
            message=request.message,
        )
        audit_store.write(response)
        return response
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/jobs/directory")
async def create_directory_job(request: DirectoryChatRequest, _: object = Depends(api_auth.require_user)) -> dict[str, str]:
    record = await job_store.create("directory")
    asyncio.create_task(_run_directory_job(record.job_id, request))
    return {"job_id": record.job_id, "status": record.status}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, _: object = Depends(api_auth.require_user)):
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/admin/jobs")
async def list_jobs(_: object = Depends(api_auth.require_admin)):
    return {"jobs": await job_store.list()}


@app.get("/api/audits")
async def list_audits(_: object = Depends(api_auth.require_admin)) -> dict[str, list[str]]:
    return {"audit_ids": audit_store.list_ids()}


@app.get("/api/audits/{audit_id}")
async def get_audit(audit_id: str, _: object = Depends(api_auth.require_admin)):
    record = audit_store.read(audit_id)
    if not record:
        raise HTTPException(status_code=404, detail="Audit snapshot not found or audit storage disabled")
    return record


@app.delete("/api/session/{session_id}")
async def reset_session(session_id: str, _: object = Depends(api_auth.require_user)) -> dict[str, str]:
    store.reset(session_id)
    return {"status": "cleared"}


async def _run_directory_job(job_id: str, request: DirectoryChatRequest) -> None:
    await job_store.mark_running(job_id, step="discovering files")
    privacy_logger.background_progress(
        job_id=job_id,
        step="discovering files",
        progress_percent=0,
        items_processed=0,
        total_items=0,
    )
    try:
        started_at = time.perf_counter()
        file_paths = file_parser.discover_directory_files(
            request.path,
            recursive=request.recursive,
            max_files=request.max_files,
        )
        total_items = len(file_paths)
        await job_store.update_progress(
            job_id,
            progress_percent=10,
            current_step="parsing files",
            items_processed=0,
            total_items=total_items,
            eta_seconds=None,
        )
        privacy_logger.background_progress(
            job_id=job_id,
            step="parsing files",
            progress_percent=10,
            items_processed=0,
            total_items=total_items,
        )
        parsed_files = []
        recent_items: list[str] = []
        for index, path in enumerate(file_paths, start=1):
            item_label = _safe_job_item_label(index, path.suffix.lower())
            parser_name = _parser_name_for_suffix(path.suffix.lower())
            parsed_files.append(file_parser.parse_path(str(path)))
            recent_items.append(item_label)
            progress = 10 + int((index / max(total_items, 1)) * 55)
            elapsed = max(time.perf_counter() - started_at, 0.001)
            average_per_item = elapsed / index
            remaining_items = max(total_items - index, 0)
            eta_seconds = int(average_per_item * remaining_items)
            await job_store.update_progress(
                job_id,
                progress_percent=progress,
                current_step=f"parsing files ({index}/{total_items})",
                items_processed=index,
                total_items=total_items,
                current_item_label=item_label,
                current_item_parser=parser_name,
                eta_seconds=eta_seconds,
                recent_items=recent_items,
            )
            privacy_logger.background_progress(
                job_id=job_id,
                step="parsing files",
                progress_percent=progress,
                items_processed=index,
                total_items=total_items,
            )
        await job_store.update_progress(
            job_id,
            progress_percent=75,
            current_step="sanitizing and routing",
            items_processed=total_items,
            total_items=total_items,
            current_item_label=None,
            current_item_parser=None,
            eta_seconds=max(int(time.perf_counter() - started_at) // 4, 1),
            recent_items=recent_items,
        )
        privacy_logger.background_progress(
            job_id=job_id,
            step="sanitizing and routing",
            progress_percent=75,
            items_processed=total_items,
            total_items=total_items,
        )
        result = await firewall.process_files(
            session_id=request.session_id,
            parsed_files=parsed_files,
            mode=request.mode,
            use_web_search=request.use_web_search,
            message=request.message,
        )
        audit_store.write(result)
        await job_store.update_progress(
            job_id,
            progress_percent=95,
            current_step="finalizing result",
            items_processed=total_items,
            total_items=total_items,
            current_item_label=None,
            current_item_parser=None,
            eta_seconds=1,
            recent_items=recent_items,
        )
        privacy_logger.background_progress(
            job_id=job_id,
            step="finalizing result",
            progress_percent=95,
            items_processed=total_items,
            total_items=total_items,
        )
        await job_store.mark_completed(job_id, result)
    except Exception as exc:
        await job_store.mark_failed(job_id, str(exc))


def _safe_job_item_label(index: int, extension: str) -> str:
    suffix = extension.lstrip(".").upper() if extension else "FILE"
    return f"Document_{_alpha_index(index)}_{suffix}"


def _alpha_index(index: int) -> str:
    value = index
    chars = []
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        chars.append(chr(ord("A") + remainder))
    return "".join(reversed(chars))


def _parser_name_for_suffix(suffix: str) -> str:
    mapping = {
        ".pdf": "pypdf",
        ".docx": "docx-xml",
        ".pptx": "pptx-xml",
        ".xlsx": "xlsx-xml",
        ".csv": "csv",
        ".tsv": "tsv",
        ".json": "json",
        ".xml": "xml",
        ".png": "tesseract-ocr",
        ".jpg": "tesseract-ocr",
        ".jpeg": "tesseract-ocr",
        ".tif": "tesseract-ocr",
        ".tiff": "tesseract-ocr",
        ".bmp": "tesseract-ocr",
        ".mp3": "whisper-local",
        ".wav": "whisper-local",
        ".m4a": "whisper-local",
        ".mp4": "whisper-local",
        ".mov": "whisper-local",
        ".mkv": "whisper-local",
    }
    return mapping.get(suffix, "text")
