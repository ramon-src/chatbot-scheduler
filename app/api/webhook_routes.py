"""WhatsApp webhook endpoints (Evolution default, Meta scaffold).

Both POST routes always return 200 for accepted/duplicate/ignored messages so
providers stop redelivering; only authentication failures return 403.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.channels.evolution_adapter import EvolutionInboundAdapter
from app.channels.meta_adapter import (
    MetaInboundAdapter,
    valid_meta_signature,
    verify_meta_handshake,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.services.ingestion_service import IngestionService, dispatch_agent_run

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_evolution = EvolutionInboundAdapter()
_meta = MetaInboundAdapter()

_OK = {"status": "ok"}


def _ingest_and_maybe_schedule(db: Session, inbound, background: BackgroundTasks) -> None:
    result = IngestionService(db).handle(inbound)
    if result.status == "professional" and result.user_id is not None:
        background.add_task(dispatch_agent_run, inbound, result.user_id)


@router.get("/whatsapp")
async def meta_verify(request: Request) -> Response:
    params = request.query_params
    challenge = verify_meta_handshake(
        params.get("hub.mode"),
        params.get("hub.verify_token"),
        params.get("hub.challenge"),
        settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN or "",
    )
    if challenge is None:
        return Response(status_code=403)
    return PlainTextResponse(challenge)


@router.post("/whatsapp")
async def meta_inbound(
    request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
):
    raw_body = await request.body()
    if not valid_meta_signature(
        raw_body, request.headers.get("X-Hub-Signature-256"), settings.WHATSAPP_APP_SECRET
    ):
        return Response(status_code=403)
    payload = await request.json()
    inbound = _meta.parse(payload)
    if inbound is None:
        return _OK
    _ingest_and_maybe_schedule(db, inbound, background)
    return _OK


@router.post("/evolution")
async def evolution_inbound(
    request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
):
    expected = settings.EVOLUTION_WEBHOOK_TOKEN
    if expected:
        provided = request.headers.get("X-Webhook-Token") or request.query_params.get("token")
        if provided != expected:
            return Response(status_code=403)
    payload = await request.json()
    inbound = _evolution.parse(payload)
    if inbound is None:
        return _OK
    _ingest_and_maybe_schedule(db, inbound, background)
    return _OK
