import base64
import binascii
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.schemas import (
    AssignIn,
    EvidenceIn,
    PublicReportIn,
    TransitionIn,
    TriageIn,
    UploadIn,
    event_out,
    incident_out,
)
from api.service import IncidentService
from api.settings import Settings
from auth.identity import resolve_actor
from domain.errors import BadRequest, DomainError
from domain.model import Actor, IncidentType, Severity, Status

IDEM_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
TENANT_RE = r"^[a-z0-9-]{1,64}$"
HTTP_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHORIZED"}


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers={"X-Request-Id": request_id},
    )


def encode_cursor(sk: str | None) -> str | None:
    return base64.urlsafe_b64encode(sk.encode()).decode().rstrip("=") if sk else None


def decode_cursor(cursor: str | None) -> str | None:
    if not cursor:
        return None
    try:
        return base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise BadRequest("invalid cursor") from exc


def create_app(service: IncidentService, settings: Settings) -> FastAPI:
    app = FastAPI(title="DrainWatch Ops API", version="0.1.0")

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        aws_event = request.scope.get("aws.event") or {}
        request.state.request_id = (aws_event.get("requestContext") or {}).get(
            "requestId"
        ) or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return error_response(request, exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        parts = [
            f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}" for e in exc.errors()
        ]
        return error_response(request, 422, "VALIDATION_ERROR", "; ".join(parts))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        return error_response(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        return error_response(request, 500, "INTERNAL", "internal error")

    def current_actor(request: Request) -> Actor:
        return resolve_actor(request.headers, request.scope.get("aws.event"), settings.app_env)

    ActorDep = Annotated[Actor, Depends(current_actor)]
    IncidentId = Annotated[str, Path(max_length=26)]

    v1 = APIRouter(prefix="/api/v1")

    @v1.post("/public/{tenant}/incidents", status_code=201)
    def report(
        body: PublicReportIn,
        tenant: Annotated[str, Path(pattern=TENANT_RE)],
        idempotency_key: Annotated[str | None, Header()] = None,
    ):
        if not idempotency_key or not IDEM_KEY_RE.match(idempotency_key):
            raise BadRequest("Idempotency-Key header required: 8-128 chars of A-Z a-z 0-9 _ -")
        ref = service.report(tenant, idempotency_key, body.model_dump(mode="json"))
        return {"reference": ref}

    @v1.get("/incidents")
    def queue(
        actor: ActorDep,
        status: Status | None = None,
        severity: Severity | None = None,
        type: IncidentType | None = None,
        older_than_hours: Annotated[int | None, Query(ge=0, le=24 * 365)] = None,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        page = service.queue(
            actor, status, severity, type, older_than_hours, decode_cursor(cursor), limit
        )
        return {
            "items": [incident_out(i) for i in page.items],
            "next_cursor": encode_cursor(page.next_cursor),
        }

    @v1.get("/incidents/{incident_id}")
    def get_incident(actor: ActorDep, incident_id: IncidentId):
        return incident_out(service.get(actor, incident_id))

    @v1.post("/incidents/{incident_id}/triage")
    def triage(actor: ActorDep, incident_id: IncidentId, body: TriageIn):
        inc = service.triage(actor, incident_id, body.expected_version, body.severity, body.reason)
        return incident_out(inc)

    @v1.post("/incidents/{incident_id}/assignments")
    def assign(actor: ActorDep, incident_id: IncidentId, body: AssignIn):
        inc = service.assign(actor, incident_id, body.expected_version, body.worker_id, body.reason)
        return incident_out(inc)

    @v1.post("/incidents/{incident_id}/transitions")
    def transition(actor: ActorDep, incident_id: IncidentId, body: TransitionIn):
        inc = service.transition(actor, incident_id, body.expected_version, body.to, body.note)
        return incident_out(inc)

    @v1.post("/incidents/{incident_id}/uploads", status_code=201)
    def upload(actor: ActorDep, incident_id: IncidentId, body: UploadIn):
        key, signed = service.presign_upload(
            actor, incident_id, body.content_type, body.content_length
        )
        return {
            "key": key,
            "url": signed.url,
            "method": "PUT",
            "headers": signed.headers,
            "expires_in": signed.expires_in,
        }

    @v1.post("/incidents/{incident_id}/evidence")
    def evidence(actor: ActorDep, incident_id: IncidentId, body: EvidenceIn):
        return incident_out(service.add_evidence(actor, incident_id, body.key, body.kind))

    @v1.get("/incidents/{incident_id}/events")
    def events(actor: ActorDep, incident_id: IncidentId):
        return {"items": [event_out(e) for e in service.events(actor, incident_id)]}

    @v1.get("/workers")
    def workers(actor: ActorDep):
        return {"items": [{"id": w.id, "name": w.name} for w in service.list_workers(actor)]}

    app.include_router(v1)

    if settings.app_env == "local":

        @app.put("/_stub-upload/{key:path}", include_in_schema=False)
        async def stub_upload(key: str, request: Request):
            size = len(await request.body())
            return {"stored": False, "key": key, "bytes": size}

    return app
