# Lead Agent + Help Tool + Minimal Outbound — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atender números desconhecidos com um `LeadAgent` (vendas/onboarding) que qualifica e cria a conta do profissional em trial, dar suporte ao profissional via tool `product_help`, e enviar a resposta do lead de volta no WhatsApp por uma porta de outbound mínima (Evolution).

**Architecture:** Roteamento por identidade (sem manager LLM): `IngestionService` já classifica `professional` vs `lead`; esta fatia liga `lead` → `dispatch_lead_run`. Leads reusam a memória existente (`ChatSession`/`ChatMessage`) via owner nullable. A resposta do lead é enviada por uma porta `OutboundAdapter` com adapter Evolution best-effort.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2 (Column-style), Alembic (schema `simplificapsi`), Pydantic AI (FallbackModel via `get_llm_model`), Pydantic v2, httpx, pytest (asyncio_mode=auto).

## Global Constraints

- DB schema é sempre `simplificapsi`. Timezone fixo `America/Sao_Paulo` (via `settings.TIMEZONE`).
- Contrato de tool: `{"success": bool, "data": Any, "message": str}`. A `message` NUNCA contém IDs, JSON, HTML, markdown ou URLs.
- Respostas ao usuário sempre em PT-BR.
- Código, identificadores e enums em inglês. Status do lead: `new` | `engaged` | `qualified` | `converted`.
- Sem segredos hardcoded. Outbound reusa `EVOLUTION_API_URL/EVOLUTION_API_KEY/EVOLUTION_INSTANCE`.
- Trabalho best-effort em background (lead run + outbound): logar, nunca levantar, nunca quebrar o webhook (sempre 200).
- Claim atômico para exactly-once: `UPDATE ... WHERE agent_run_at IS NULL` (READ COMMITTED).
- Commits nunca atribuem a IA (sem `Co-Authored-By: Claude` etc.).
- Migrations encadeiam a partir de `0010_event_occurrences` (branch `feat/lead-help-outbound`).

---

### Task 1: Trial column on users + config

**Files:**
- Create: `migrations/versions/0011_user_access_expires.py`
- Modify: `app/models/user.py` (add column), `app/core/config.py` (add `LEAD_TRIAL_DAYS`, `LEAD_AGENT_MODEL`)
- Test: `tests/unit/test_user_trial.py`

**Interfaces:**
- Produces: `User.access_expires_at: datetime | None`; `settings.LEAD_TRIAL_DAYS: int` (default 7); `settings.LEAD_AGENT_MODEL: str` (default "gpt-5.4-mini").

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_user_trial.py
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User


def test_user_has_access_expires_at_column():
    db = SessionLocal()
    try:
        expires = datetime.now(ZoneInfo(settings.TIMEZONE)) + timedelta(days=7)
        u = User(name="Trial User", email="trial-col-test@simplificapsi.test", access_expires_at=expires)
        db.add(u)
        db.commit()
        db.refresh(u)
        assert u.access_expires_at is not None
    finally:
        db.query(User).filter(User.email == "trial-col-test@simplificapsi.test").delete()
        db.commit()
        db.close()


def test_lead_trial_days_default():
    assert settings.LEAD_TRIAL_DAYS == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_user_trial.py -v`
Expected: FAIL — `TypeError: 'access_expires_at' is an invalid keyword argument` / `AttributeError: ... LEAD_TRIAL_DAYS`.

- [ ] **Step 3: Write the migration**

```python
# migrations/versions/0011_user_access_expires.py
"""add access_expires_at to users (trial expiry for lead-created accounts)

Revision ID: 0011_user_access_expires
Revises: 0010_event_occurrences
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_user_access_expires"
down_revision = "0010_event_occurrences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_column("users", "access_expires_at", schema="simplificapsi")
```

- [ ] **Step 4: Add the model column + config**

In `app/models/user.py`, under the TIMESTAMPS block (next to `created_at`/`updated_at`), add:

```python
    # Trial expiry for accounts created by the lead agent (NULL = no expiry).
    access_expires_at = Column(DateTime(timezone=True), nullable=True)
```

In `app/core/config.py`, next to `SIMPLIFICA_AGENT_MODEL`/`TIMEZONE`, add:

```python
    LEAD_AGENT_MODEL: str = Field(default="gpt-5.4-mini", env="LEAD_AGENT_MODEL")
    LEAD_TRIAL_DAYS: int = Field(default=7, env="LEAD_TRIAL_DAYS")
```

- [ ] **Step 5: Apply migration and run the test**

Run: `uv run alembic upgrade head && uv run pytest tests/unit/test_user_trial.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/0011_user_access_expires.py app/models/user.py app/core/config.py tests/unit/test_user_trial.py
git commit -m "feat(users): access_expires_at trial column + lead config"
```

---

### Task 2: Lead model + migration

**Files:**
- Create: `migrations/versions/0012_leads.py`, `app/models/lead.py`
- Modify: `app/models/__init__.py` (register `Lead` for mapper/metadata)
- Test: `tests/unit/test_lead_model.py`

**Interfaces:**
- Produces: `Lead` model — columns `id, phone, name, email, status, notes, user_id, created_at, updated_at`. `status` default `"new"`. `phone` unique. `Lead.chat_sessions` relationship (back_populates set up in Task 3).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_lead_model.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.lead import Lead


def test_create_lead_defaults_to_new():
    db = SessionLocal()
    try:
        lead = Lead(phone="5551900000001")
        db.add(lead)
        db.commit()
        db.refresh(lead)
        assert lead.status == "new"
        assert lead.user_id is None
    finally:
        db.query(Lead).filter(Lead.phone == "5551900000001").delete()
        db.commit()
        db.close()


def test_lead_phone_is_unique():
    db = SessionLocal()
    try:
        db.add(Lead(phone="5551900000002"))
        db.commit()
        db.add(Lead(phone="5551900000002"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.query(Lead).filter(Lead.phone == "5551900000002").delete()
        db.commit()
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_lead_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.lead'`.

- [ ] **Step 3: Write the model**

```python
# app/models/lead.py
"""Lead model: an unknown WhatsApp number being qualified by the lead agent."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Lead(Base):
    """A prospective professional (unlinked sender) in the qualification funnel."""

    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("phone", name="uq_leads_phone"),
        {"schema": "simplificapsi"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(20), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    # new | engaged | qualified | converted
    status = Column(String(20), nullable=False, server_default="new", default="new", index=True)
    notes = Column(Text, nullable=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("simplificapsi.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    chat_sessions = relationship(
        "ChatSession", back_populates="lead", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Lead(id={self.id}, phone={self.phone}, status={self.status})>"
```

In `app/models/__init__.py`, add `from app.models.lead import Lead` alongside the other model imports (so the mapper sees it — required for the Task 3 relationship and for metadata).

- [ ] **Step 4: Write the migration**

```python
# migrations/versions/0012_leads.py
"""create leads table (qualification funnel for unlinked WhatsApp numbers)

Revision ID: 0012_leads
Revises: 0011_user_access_expires
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_leads"
down_revision = "0011_user_access_expires"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="new", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("phone", name="uq_leads_phone"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["simplificapsi.users.id"], name="fk_leads_user_id", ondelete="SET NULL"
        ),
        schema="simplificapsi",
    )
    op.create_index("ix_leads_phone", "leads", ["phone"], schema="simplificapsi")
    op.create_index("ix_leads_status", "leads", ["status"], schema="simplificapsi")


def downgrade() -> None:
    op.drop_index("ix_leads_status", table_name="leads", schema="simplificapsi")
    op.drop_index("ix_leads_phone", table_name="leads", schema="simplificapsi")
    op.drop_table("leads", schema="simplificapsi")
```

- [ ] **Step 5: Apply migration and run the test**

Run: `uv run alembic upgrade head && uv run pytest tests/unit/test_lead_model.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/0012_leads.py app/models/lead.py app/models/__init__.py tests/unit/test_lead_model.py
git commit -m "feat(lead): Lead model + leads table (migration 0012)"
```

---

### Task 3: Owner-agnostic chat_sessions (reuse memory for leads)

**Files:**
- Create: `migrations/versions/0013_chat_sessions_owner.py`
- Modify: `app/models/chat_session.py` (user_id nullable, add lead_id, CHECK, relationship)
- Test: `tests/unit/test_chat_session_owner.py`

**Interfaces:**
- Produces: `ChatSession.user_id` nullable; `ChatSession.lead_id: UUID | None`; `ChatSession.lead` relationship; DB CHECK `ck_chat_sessions_one_owner` enforcing exactly one owner.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_chat_session_owner.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.chat_session import ChatSession
from app.models.lead import Lead


def test_lead_owned_session_is_allowed():
    db = SessionLocal()
    try:
        lead = Lead(phone="5551900000010")
        db.add(lead)
        db.commit()
        db.refresh(lead)
        s = ChatSession(lead_id=lead.id, session_id="sess-lead-1", phone_number="5551900000010")
        db.add(s)
        db.commit()
        db.refresh(s)
        assert s.user_id is None and s.lead_id == lead.id
    finally:
        db.rollback()
        db.query(ChatSession).filter(ChatSession.session_id == "sess-lead-1").delete()
        db.query(Lead).filter(Lead.phone == "5551900000010").delete()
        db.commit()
        db.close()


def test_session_rejects_two_owners():
    db = SessionLocal()
    try:
        lead = Lead(phone="5551900000011")
        db.add(lead)
        db.commit()
        db.refresh(lead)
        # both user_id and lead_id set -> CHECK violation
        from uuid import uuid4
        s = ChatSession(user_id=uuid4(), lead_id=lead.id, session_id="sess-bad", phone_number="x")
        db.add(s)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.query(Lead).filter(Lead.phone == "5551900000011").delete()
        db.commit()
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_chat_session_owner.py -v`
Expected: FAIL — `TypeError: 'lead_id' is an invalid keyword argument for ChatSession`.

- [ ] **Step 3: Write the migration**

```python
# migrations/versions/0013_chat_sessions_owner.py
"""make chat_sessions owner-agnostic (user OR lead)

Revision ID: 0013_chat_sessions_owner
Revises: 0012_leads
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_chat_sessions_owner"
down_revision = "0012_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "chat_sessions", "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True, schema="simplificapsi",
    )
    op.add_column(
        "chat_sessions",
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="simplificapsi",
    )
    op.create_foreign_key(
        "fk_chat_sessions_lead_id", "chat_sessions", "leads",
        ["lead_id"], ["id"],
        source_schema="simplificapsi", referent_schema="simplificapsi",
        ondelete="CASCADE",
    )
    op.create_index("ix_chat_sessions_lead_id", "chat_sessions", ["lead_id"], schema="simplificapsi")
    op.create_check_constraint(
        "ck_chat_sessions_one_owner", "chat_sessions",
        "(user_id IS NOT NULL) <> (lead_id IS NOT NULL)",
        schema="simplificapsi",
    )


def downgrade() -> None:
    op.drop_constraint("ck_chat_sessions_one_owner", "chat_sessions", schema="simplificapsi")
    op.drop_index("ix_chat_sessions_lead_id", table_name="chat_sessions", schema="simplificapsi")
    op.drop_constraint("fk_chat_sessions_lead_id", "chat_sessions", schema="simplificapsi", type_="foreignkey")
    op.drop_column("chat_sessions", "lead_id", schema="simplificapsi")
    op.alter_column(
        "chat_sessions", "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False, schema="simplificapsi",
    )
```

- [ ] **Step 4: Update the model**

In `app/models/chat_session.py`:

Add `CheckConstraint` to the imports from sqlalchemy:
```python
from sqlalchemy import JSON, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text
```

Replace the `__table_args__` line:
```python
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL) <> (lead_id IS NOT NULL)",
            name="ck_chat_sessions_one_owner",
        ),
        {"schema": "simplificapsi"},
    )
```

Make `user_id` nullable and add `lead_id` under FOREIGN KEYS:
```python
    user_id = Column(UUID(as_uuid=True), ForeignKey("simplificapsi.users.id", ondelete="CASCADE"), nullable=True, index=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("simplificapsi.leads.id", ondelete="CASCADE"), nullable=True, index=True)
```

Add the `lead` relationship under RELATIONSHIPS (next to `user`):
```python
    lead = relationship("Lead", back_populates="chat_sessions")
```

- [ ] **Step 5: Apply migration and run the test**

Run: `uv run alembic upgrade head && uv run pytest tests/unit/test_chat_session_owner.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/0013_chat_sessions_owner.py app/models/chat_session.py tests/unit/test_chat_session_owner.py
git commit -m "feat(memory): owner-agnostic chat_sessions (user or lead)"
```

---

### Task 4: LeadService (get/update/convert)

**Files:**
- Create: `app/services/lead_service.py`
- Test: `tests/unit/test_lead_service.py`

**Interfaces:**
- Consumes: `Lead` (Task 2), `User.access_expires_at` (Task 1), `settings.LEAD_TRIAL_DAYS`, `ConflictError` (`app/core/exceptions.py`), `normalize_phone` (`app/channels/phone.py`).
- Produces:
  - `LeadService(db).get_or_create_lead(phone: str) -> Lead`
  - `LeadService(db).get_lead(lead_id: UUID) -> Lead | None`
  - `LeadService(db).update_lead(lead, *, name=None, email=None, notes=None, status=None) -> Lead`
  - `LeadService(db).convert_to_account(lead, name: str, email: str, trial_days: int) -> tuple[User, bool]` — returns `(user, created)`; idempotent on existing phone; raises `ConflictError` on e-mail conflict.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_lead_service.py
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import ConflictError
from app.models.lead import Lead
from app.models.user import User
from app.services.lead_service import LeadService

TZ = ZoneInfo(settings.TIMEZONE)


def _cleanup(db, phone, email):
    db.query(Lead).filter(Lead.phone == phone).delete()
    db.query(User).filter(User.email == email).delete()
    db.commit()


def test_get_or_create_lead_is_idempotent():
    db = SessionLocal()
    phone = "5551900000020"
    try:
        svc = LeadService(db)
        a = svc.get_or_create_lead(phone)
        b = svc.get_or_create_lead(phone)
        assert a.id == b.id
    finally:
        _cleanup(db, phone, "x@x")
        db.close()


def test_convert_creates_user_in_trial_and_marks_lead():
    db = SessionLocal()
    phone = "5551900000021"
    email = "lead-convert-test@simplificapsi.test"
    try:
        svc = LeadService(db)
        lead = svc.get_or_create_lead(phone)
        user, created = svc.convert_to_account(lead, "Carla Nova", email, trial_days=7)
        assert created is True
        assert user.access_expires_at is not None
        assert user.access_expires_at > datetime.now(TZ)
        db.refresh(lead)
        assert lead.status == "converted"
        assert lead.user_id == user.id
    finally:
        _cleanup(db, phone, email)
        db.close()


def test_convert_is_idempotent_on_existing_phone():
    db = SessionLocal()
    phone = "5551900000022"
    email = "lead-convert-twice@simplificapsi.test"
    try:
        svc = LeadService(db)
        lead = svc.get_or_create_lead(phone)
        user1, created1 = svc.convert_to_account(lead, "Bia Dup", email, trial_days=7)
        user2, created2 = svc.convert_to_account(lead, "Bia Dup", email, trial_days=7)
        assert created1 is True and created2 is False
        assert user1.id == user2.id
    finally:
        _cleanup(db, phone, email)
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_lead_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.lead_service'`.

- [ ] **Step 3: Write the service**

```python
# app/services/lead_service.py
"""Lead persistence + qualification funnel operations."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.channels.phone import normalize_phone
from app.core.config import settings
from app.core.exceptions import ConflictError
from app.models.lead import Lead
from app.models.user import User


class LeadService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_lead(self, phone: str) -> Lead:
        lead = self.db.query(Lead).filter(Lead.phone == phone).first()
        if lead is not None:
            return lead
        lead = Lead(phone=phone, status="new")
        self.db.add(lead)
        try:
            self.db.commit()
        except IntegrityError:  # concurrent insert on the unique phone
            self.db.rollback()
            return self.db.query(Lead).filter(Lead.phone == phone).first()
        self.db.refresh(lead)
        return lead

    def get_lead(self, lead_id: UUID) -> Lead | None:
        return self.db.get(Lead, lead_id)

    def update_lead(
        self, lead: Lead, *, name=None, email=None, notes=None, status=None
    ) -> Lead:
        if name is not None:
            lead.name = name
        if email is not None:
            lead.email = email
        if notes is not None:
            lead.notes = notes
        if status is not None:
            lead.status = status
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def convert_to_account(
        self, lead: Lead, name: str, email: str, trial_days: int
    ) -> tuple[User, bool]:
        """Create the professional's trial account from a lead. Idempotent on phone."""
        normalized = normalize_phone(lead.phone)
        existing = (
            self.db.query(User).filter(User.phone_normalized == normalized).first()
            if normalized
            else None
        )
        if existing is not None:
            self._mark_converted(lead, existing.id)
            return existing, False

        expires = datetime.now(ZoneInfo(settings.TIMEZONE)) + timedelta(days=trial_days)
        user = User(name=name, email=email, phone=lead.phone, access_expires_at=expires)
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = (
                self.db.query(User).filter(User.phone_normalized == normalized).first()
                if normalized
                else None
            )
            if existing is not None:
                self._mark_converted(lead, existing.id)
                return existing, False
            raise ConflictError("Já existe uma conta com esse e-mail.")
        self.db.refresh(user)
        self._mark_converted(lead, user.id)
        return user, True

    def _mark_converted(self, lead: Lead, user_id: UUID) -> None:
        lead.status = "converted"
        lead.user_id = user_id
        self.db.commit()
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/unit/test_lead_service.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/lead_service.py tests/unit/test_lead_service.py
git commit -m "feat(lead): LeadService (get/update/convert-to-trial-account)"
```

---

### Task 5: Product knowledge + product_help tool on SimplificaAgent

**Files:**
- Create: `app/agents/knowledge/__init__.py`, `app/agents/knowledge/product_faq.py`, `app/agents/tools/help_tools.py`
- Modify: `app/agents/simplifica_agent.py` (register the help tool)
- Test: `tests/unit/test_product_help.py`

**Interfaces:**
- Produces:
  - `app.agents.knowledge.product_faq.PRODUCT_SUMMARY: str`
  - `app.agents.knowledge.product_faq.lookup(topic: str | None = None) -> str`
  - `app.agents.tools.help_tools.register_help_tools(agent) -> None` (adds async tool `product_help(topic: str | None = None) -> dict`)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_product_help.py
from app.agents.knowledge.product_faq import PRODUCT_SUMMARY, lookup


def test_lookup_no_topic_returns_summary():
    assert lookup() == PRODUCT_SUMMARY


def test_lookup_known_topic_returns_specific_guidance():
    msg = lookup("agenda")
    assert "recorrente" in msg.lower()


def test_lookup_unknown_topic_falls_back_to_summary():
    assert lookup("xpto-desconhecido") == PRODUCT_SUMMARY


def test_help_tool_registered_on_simplifica_agent():
    from app.agents.simplifica_agent import build_simplifica_agent

    agent = build_simplifica_agent()
    tool_names = set(agent._function_toolset.tools.keys())
    assert "product_help" in tool_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_product_help.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.knowledge'`.

- [ ] **Step 3: Write the knowledge module**

```python
# app/agents/knowledge/__init__.py
```
(empty file)

```python
# app/agents/knowledge/product_faq.py
"""Single source of product knowledge (PT-BR), shared by lead + help."""

PRODUCT_SUMMARY = (
    "O Simplifica Psi é seu assistente no WhatsApp para gerenciar seu consultório: "
    "cadastro de clientes, agenda (sessões únicas e recorrentes) e controle de cobrança. "
    "Você fala em linguagem natural e eu cuido do resto."
)

FAQ = {
    "cadastro": (
        "Para cadastrar um cliente eu preciso de nome e sobrenome, telefone, "
        "dia de cobrança e o valor da consulta."
    ),
    "agenda": (
        "Na agenda eu marco sessões únicas e recorrentes, listo por período "
        "(hoje, amanhã, esta semana, próxima semana, este mês) e cancelo quando precisar."
    ),
    "cobranca": (
        "No controle de cobrança eu registro o que foi pago, mostro quem está com "
        "pendência e ajudo a acompanhar os recebimentos."
    ),
    "preco": (
        "Você começa com um período de teste gratuito. Depois eu te envio o link "
        "de pagamento para continuar usando."
    ),
    "comecar": (
        "Para começar é simples: me diga seu nome e um e-mail que eu crio sua conta "
        "de teste na hora."
    ),
}


def lookup(topic: str | None = None) -> str:
    """Return guidance for a topic, or the product summary when unknown/absent."""
    if not topic:
        return PRODUCT_SUMMARY
    key = topic.strip().lower()
    for name, answer in FAQ.items():
        if name in key or key in name:
            return answer
    return PRODUCT_SUMMARY
```

- [ ] **Step 4: Write the help tool and register it**

```python
# app/agents/tools/help_tools.py
"""Help/FAQ tool for the professional agent (how to use Simplifica Psi)."""

from app.agents.deps import AgentDeps
from app.agents.knowledge.product_faq import lookup


def register_help_tools(agent) -> None:
    from pydantic_ai import RunContext

    @agent.tool
    async def product_help(ctx: RunContext[AgentDeps], topic: str | None = None) -> dict:
        """Explica como usar o Simplifica Psi (cadastro de clientes, agenda, cobrança)."""
        return {"success": True, "data": None, "message": lookup(topic)}
```

In `app/agents/simplifica_agent.py`, add the import and the registration call inside `build_simplifica_agent` (right after `register_calendar_tools(agent)`):

```python
from app.agents.tools.help_tools import register_help_tools
```
```python
    register_client_tools(agent)
    register_calendar_tools(agent)
    register_help_tools(agent)
    return agent
```

- [ ] **Step 5: Run the test**

Run: `uv run pytest tests/unit/test_product_help.py -v`
Expected: PASS (4 tests). The `_function_toolset.tools.keys()` accessor is the same one used in `tests/unit/test_agent_agenda_wiring.py`.

- [ ] **Step 6: Commit**

```bash
git add app/agents/knowledge/__init__.py app/agents/knowledge/product_faq.py app/agents/tools/help_tools.py app/agents/simplifica_agent.py tests/unit/test_product_help.py
git commit -m "feat(help): product_faq knowledge + product_help tool on SimplificaAgent"
```

---

### Task 6: LeadAgent + lead tools

**Files:**
- Create: `app/agents/lead_agent.py`, `app/agents/tools/lead_tools.py`
- Modify: `app/agents/deps.py` (add `LeadAgentDeps`)
- Test: `tests/unit/test_lead_tools.py`

**Interfaces:**
- Consumes: `LeadService` (Task 4), `lookup` (Task 5), `get_llm_model` (`app/agents/foundation`), `settings.LEAD_AGENT_MODEL`/`LEAD_TRIAL_DAYS`, `ConflictError`.
- Produces:
  - `LeadAgentDeps` dataclass: `db, lead_id, lead_name, lead_phone, current_datetime, timezone, history_summary, lead_service, trial_days`.
  - `app.agents.tools.lead_tools.update_lead_info_impl(deps, name=None, email=None, notes=None, status=None) -> dict`
  - `app.agents.tools.lead_tools.create_professional_account_impl(deps, name, email) -> dict`
  - `app.agents.tools.lead_tools.register_lead_tools(agent) -> None`
  - `app.agents.lead_agent.build_lead_agent() -> Agent[LeadAgentDeps, str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_lead_tools.py
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agents.deps import LeadAgentDeps
from app.agents.tools.lead_tools import (
    create_professional_account_impl,
    update_lead_info_impl,
)
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.lead import Lead
from app.models.user import User
from app.services.lead_service import LeadService

TZ = ZoneInfo(settings.TIMEZONE)


def _deps(db, lead):
    return LeadAgentDeps(
        db=db, lead_id=lead.id, lead_name=lead.name, lead_phone=lead.phone,
        current_datetime=datetime.now(TZ), timezone=settings.TIMEZONE,
        history_summary=None, lead_service=LeadService(db), trial_days=7,
    )


def _cleanup(db, phone, email):
    db.query(Lead).filter(Lead.phone == phone).delete()
    db.query(User).filter(User.email == email).delete()
    db.commit()


async def test_update_lead_info_persists():
    db = SessionLocal()
    phone = "5551900000030"
    try:
        lead = LeadService(db).get_or_create_lead(phone)
        out = await update_lead_info_impl(_deps(db, lead), name="Rafa Lead", status="qualified")
        assert out["success"] is True
        db.refresh(lead)
        assert lead.name == "Rafa Lead" and lead.status == "qualified"
    finally:
        _cleanup(db, phone, "x@x")
        db.close()


async def test_create_account_requires_email():
    db = SessionLocal()
    phone = "5551900000031"
    try:
        lead = LeadService(db).get_or_create_lead(phone)
        out = await create_professional_account_impl(_deps(db, lead), name="Sem Email", email=None)
        assert out["success"] is False
    finally:
        _cleanup(db, phone, "x@x")
        db.close()


async def test_create_account_success_then_idempotent():
    db = SessionLocal()
    phone = "5551900000032"
    email = "lead-tool-acct@simplificapsi.test"
    try:
        lead = LeadService(db).get_or_create_lead(phone)
        out1 = await create_professional_account_impl(_deps(db, lead), name="Nova Conta", email=email)
        assert out1["success"] is True
        out2 = await create_professional_account_impl(_deps(db, lead), name="Nova Conta", email=email)
        assert out2["success"] is True  # idempotent, friendly "já tem conta"
        # message must not leak IDs/URLs
        assert "http" not in out1["message"].lower()
    finally:
        _cleanup(db, phone, email)
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_lead_tools.py -v`
Expected: FAIL — `ImportError: cannot import name 'LeadAgentDeps'`.

- [ ] **Step 3: Add LeadAgentDeps**

In `app/agents/deps.py`, add under the existing `AgentDeps` (and extend the `TYPE_CHECKING` block):

```python
if TYPE_CHECKING:
    from app.services.event_service import EventService
    from app.services.google_calendar_service import GoogleCalendarService
    from app.services.lead_service import LeadService


@dataclass
class LeadAgentDeps:
    db: Session
    lead_id: UUID
    lead_name: str | None
    lead_phone: str
    current_datetime: datetime
    timezone: str
    history_summary: str | None
    lead_service: "LeadService"
    trial_days: int
```

- [ ] **Step 4: Write the lead tools**

```python
# app/agents/tools/lead_tools.py
"""Lead agent tools: pure impls + thin @agent.tool wrappers."""

from app.agents.deps import LeadAgentDeps
from app.agents.knowledge.product_faq import lookup
from app.core.exceptions import ConflictError

_VALID_STATUS = {"new", "engaged", "qualified", "converted"}


async def update_lead_info_impl(
    deps: LeadAgentDeps, name=None, email=None, notes=None, status=None
) -> dict:
    lead = deps.lead_service.get_lead(deps.lead_id)
    if lead is None:
        return {"success": False, "data": None, "message": "Não consegui localizar seu cadastro."}
    if status is not None and status not in _VALID_STATUS:
        status = None
    deps.lead_service.update_lead(lead, name=name, email=email, notes=notes, status=status)
    return {"success": True, "data": {"name": lead.name}, "message": "Anotado!"}


async def create_professional_account_impl(deps: LeadAgentDeps, name=None, email=None) -> dict:
    if not name or not email:
        return {
            "success": False, "data": None,
            "message": "Para criar sua conta eu preciso do seu nome completo e de um e-mail.",
        }
    lead = deps.lead_service.get_lead(deps.lead_id)
    if lead is None:
        return {"success": False, "data": None, "message": "Não consegui localizar seu cadastro."}
    try:
        user, created = deps.lead_service.convert_to_account(lead, name, email, deps.trial_days)
    except ConflictError as exc:
        return {"success": False, "data": None, "message": str(exc)}

    first = (user.name or name).split()[0]
    if not created:
        return {
            "success": True, "data": {"name": user.name},
            "message": f"{first}, você já tem uma conta com a gente. É só me chamar que eu te ajudo.",
        }
    return {
        "success": True, "data": {"name": user.name},
        "message": (
            f"Pronto, {first}! Criei sua conta de teste, válida por {deps.trial_days} dias. "
            f"Daqui a pouco te envio o link de pagamento para ativar de vez."
        ),
    }


def register_lead_tools(agent) -> None:
    from pydantic_ai import RunContext

    @agent.tool
    async def update_lead_info(
        ctx: RunContext[LeadAgentDeps],
        name: str | None = None, email: str | None = None,
        notes: str | None = None, status: str | None = None,
    ) -> dict:
        """Salva nome/e-mail/observações do interessado e atualiza o estágio do lead."""
        return await update_lead_info_impl(ctx.deps, name, email, notes, status)

    @agent.tool
    async def create_professional_account(
        ctx: RunContext[LeadAgentDeps], name: str, email: str
    ) -> dict:
        """Cria a conta de teste do profissional (precisa de nome completo e e-mail)."""
        return await create_professional_account_impl(ctx.deps, name, email)

    @agent.tool
    async def product_faq(ctx: RunContext[LeadAgentDeps], topic: str | None = None) -> dict:
        """Responde dúvidas sobre o Simplifica Psi (o que faz, preço, como começar)."""
        return {"success": True, "data": None, "message": lookup(topic)}
```

- [ ] **Step 5: Write the lead agent**

```python
# app/agents/lead_agent.py
"""LeadAgent: sales/onboarding agent for unknown WhatsApp numbers (prospects)."""

from pydantic_ai import Agent, RunContext

from app.agents.deps import LeadAgentDeps
from app.agents.foundation import get_llm_model
from app.agents.knowledge.product_faq import PRODUCT_SUMMARY
from app.agents.tools.lead_tools import register_lead_tools
from app.core.config import settings

LEAD_SYSTEM_PROMPT = f"""Você é o assistente de vendas do Simplifica Psi, falando no WhatsApp com
um possível novo cliente (um psicólogo ou terapeuta que ainda NÃO tem conta).

OBJETIVO:
- Apresentar o produto de forma acolhedora e objetiva, tirar dúvidas e conduzir a pessoa ao cadastro.
- Quando a pessoa demonstrar interesse em começar, colete o nome completo e um e-mail e crie a conta
  de teste usando a tool. NÃO invente conta sem nome e e-mail.

SOBRE O PRODUTO:
{PRODUCT_SUMMARY}

REGRAS DE RESPOSTA:
- Responda sempre em Português do Brasil, tom simpático e direto, mensagens curtas (é WhatsApp).
- NUNCA exponha IDs, códigos, JSON, links ou termos técnicos.
- Use as tools para salvar dados do interessado, responder dúvidas e criar a conta. Nunca invente dados.
- O período de teste é gratuito; o link de pagamento é enviado depois (não prometa nada além disso).
- Se a pessoa claramente já é cliente ou quer falar de uma conta existente, oriente que ela use o
  número já cadastrado.
"""


def build_lead_agent() -> Agent[LeadAgentDeps, str]:
    agent = Agent(
        get_llm_model(settings.LEAD_AGENT_MODEL, temperature=0.2, timeout=30),
        deps_type=LeadAgentDeps,
        output_type=str,
        system_prompt=LEAD_SYSTEM_PROMPT,
        retries=3,
    )

    @agent.system_prompt
    def add_runtime_context(ctx: RunContext[LeadAgentDeps]) -> str:
        d = ctx.deps
        when = d.current_datetime.strftime("%d/%m/%Y %H:%M") if d.current_datetime else "agora"
        lines = [
            f"Interessado: {d.lead_name or 'ainda sem nome'}",
            f"Data/hora atual: {when} ({d.timezone})",
        ]
        if d.history_summary:
            lines.append(f"Resumo da conversa até aqui: {d.history_summary}")
        return "\n".join(lines)

    register_lead_tools(agent)
    return agent
```

- [ ] **Step 6: Run the test**

Run: `uv run pytest tests/unit/test_lead_tools.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add app/agents/lead_agent.py app/agents/tools/lead_tools.py app/agents/deps.py tests/unit/test_lead_tools.py
git commit -m "feat(lead): LeadAgent + lead tools (qualify + create trial account)"
```

---

### Task 7: Outbound port + Evolution send adapter

**Files:**
- Create: `app/channels/outbound.py`, `app/channels/evolution_outbound.py`
- Test: `tests/unit/test_evolution_outbound.py`

**Interfaces:**
- Produces:
  - `app.channels.outbound.OutboundMessage(to_phone: str, text: str)` (frozen dataclass)
  - `app.channels.outbound.OutboundAdapter` Protocol (`provider: str`, `send(message) -> bool`)
  - `app.channels.evolution_outbound.EvolutionOutboundAdapter(settings)` with `send(message: OutboundMessage) -> bool` — best-effort, never raises; returns `False` when unconfigured or on error.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_evolution_outbound.py
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.channels.evolution_outbound import EvolutionOutboundAdapter
from app.channels.outbound import OutboundMessage


def _settings(**kw):
    base = dict(EVOLUTION_API_URL="https://evo.test", EVOLUTION_API_KEY="k", EVOLUTION_INSTANCE="inst")
    base.update(kw)
    return SimpleNamespace(**base)


def test_send_unconfigured_returns_false():
    adapter = EvolutionOutboundAdapter(_settings(EVOLUTION_API_URL=None))
    assert adapter.send(OutboundMessage(to_phone="5551999990000", text="oi")) is False


def test_send_posts_and_returns_true():
    adapter = EvolutionOutboundAdapter(_settings())
    with patch("app.channels.evolution_outbound.httpx.post") as post:
        post.return_value = MagicMock(status_code=201)
        ok = adapter.send(OutboundMessage(to_phone="5551999990000", text="olá"))
    assert ok is True
    url, kwargs = post.call_args[0][0], post.call_args[1]
    assert url == "https://evo.test/message/sendText/inst"
    assert kwargs["headers"]["apikey"] == "k"
    assert kwargs["json"]["number"] == "5551999990000"
    assert kwargs["json"]["text"] == "olá"


def test_send_swallows_errors_and_returns_false():
    adapter = EvolutionOutboundAdapter(_settings())
    with patch("app.channels.evolution_outbound.httpx.post", side_effect=RuntimeError("boom")):
        assert adapter.send(OutboundMessage(to_phone="5551999990000", text="x")) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_evolution_outbound.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.channels.outbound'`.

- [ ] **Step 3: Write the port**

```python
# app/channels/outbound.py
"""Provider-agnostic outbound message port (send a reply back to the user)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class OutboundMessage:
    to_phone: str  # normalized recipient
    text: str


@runtime_checkable
class OutboundAdapter(Protocol):
    provider: str

    def send(self, message: OutboundMessage) -> bool:
        """Best-effort send. Returns True if accepted, False otherwise. Never raises."""
        ...
```

- [ ] **Step 4: Write the Evolution adapter**

```python
# app/channels/evolution_outbound.py
"""Evolution API outbound adapter: send a text message (best-effort)."""

from __future__ import annotations

import httpx

from app.channels.outbound import OutboundMessage
from app.core.logging import get_logger

logger = get_logger(__name__)


class EvolutionOutboundAdapter:
    provider = "evolution"

    def __init__(self, settings):
        self._url = settings.EVOLUTION_API_URL
        self._key = settings.EVOLUTION_API_KEY
        self._instance = settings.EVOLUTION_INSTANCE

    def send(self, message: OutboundMessage) -> bool:
        if not (self._url and self._key and self._instance):
            logger.warning("evolution outbound not configured — dropping reply")
            return False
        try:
            resp = httpx.post(
                f"{self._url}/message/sendText/{self._instance}",
                headers={"apikey": self._key},
                json={"number": message.to_phone, "text": message.text},
                timeout=10,
            )
            return resp.status_code < 400
        except Exception:  # noqa: BLE001 - outbound is best-effort, never raise
            logger.warning("evolution outbound send failed", exc_info=True)
            return False
```

- [ ] **Step 5: Run the test**

Run: `uv run pytest tests/unit/test_evolution_outbound.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add app/channels/outbound.py app/channels/evolution_outbound.py tests/unit/test_evolution_outbound.py
git commit -m "feat(outbound): outbound port + Evolution send adapter (best-effort)"
```

---

### Task 8: Lead memory + agent_runner lead flow

**Files:**
- Modify: `app/services/chat_history_service.py` (add `get_or_create_lead_session`)
- Modify: `app/services/agent_runner.py` (extract `_run_with_memory`, add `build_lead_deps` + `process_lead_message`)
- Test: `tests/integration/test_lead_runner.py`

**Interfaces:**
- Consumes: `ChatSession.lead_id` (Task 3), `Lead`/`LeadService` (Tasks 2/4), `build_lead_agent` (Task 6).
- Produces:
  - `ChatHistoryService(db).get_or_create_lead_session(lead_id: UUID, phone_number: str) -> ChatSession`
  - `app.services.agent_runner.process_lead_message(db, agent, lead, text: str, phone: str) -> str`
  - (refactor) `app.services.agent_runner._run_with_memory(db, agent, session, deps, text) -> str` used by both professional and lead paths.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_lead_runner.py
from unittest.mock import patch

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.core.database import SessionLocal
from app.models.chat_session import ChatMessage, ChatSession
from app.models.lead import Lead
from app.services.agent_runner import process_lead_message
from app.services.lead_service import LeadService

LEAD_PHONE = "5551900000040"


def _reply_model(text):
    async def fn(messages, info):
        return ModelResponse(parts=[TextPart(text)])
    return FunctionModel(fn)


def _build_lead_agent_with_noop():
    with patch("app.agents.lead_agent.get_llm_model", return_value=_reply_model("noop")):
        from app.agents.lead_agent import build_lead_agent
        return build_lead_agent()


def _cleanup(db):
    leads = db.query(Lead).filter(Lead.phone == LEAD_PHONE).all()
    for lead in leads:
        for s in db.query(ChatSession).filter(ChatSession.lead_id == lead.id):
            db.query(ChatMessage).filter(ChatMessage.session_id == s.id).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.lead_id == lead.id).delete(synchronize_session=False)
    db.query(Lead).filter(Lead.phone == LEAD_PHONE).delete(synchronize_session=False)
    db.commit()


async def test_process_lead_message_persists_turn_in_lead_session():
    db = SessionLocal()
    try:
        _cleanup(db)
        lead = LeadService(db).get_or_create_lead(LEAD_PHONE)
        agent = _build_lead_agent_with_noop()
        with agent.override(model=_reply_model("Oi! Posso te explicar o Simplifica Psi.")):
            reply = await process_lead_message(db, agent, lead, "o que é isso?", LEAD_PHONE)
        assert "Simplifica" in reply
        session = db.query(ChatSession).filter(ChatSession.lead_id == lead.id).first()
        assert session is not None and session.user_id is None
        msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).count()
        assert msgs == 2  # user + assistant
    finally:
        _cleanup(db)
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_lead_runner.py -v`
Expected: FAIL — `ImportError: cannot import name 'process_lead_message'`.

- [ ] **Step 3: Add `get_or_create_lead_session`**

In `app/services/chat_history_service.py`, add (mirroring `get_or_create_session`, owner = lead):

```python
    def get_or_create_lead_session(self, lead_id: UUID, phone_number: str) -> ChatSession:
        existing = (
            self.db.query(ChatSession)
            .filter(
                and_(
                    ChatSession.lead_id == lead_id,
                    ChatSession.phone_number == phone_number,
                    ChatSession.is_active == True,  # noqa: E712
                )
            )
            .order_by(ChatSession.updated_at.desc())
            .first()
        )
        if existing is not None:
            return existing
        session = ChatSession(
            lead_id=lead_id,
            session_id=str(uuid.uuid4()),
            phone_number=phone_number,
            is_active=True,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session
```

- [ ] **Step 4: Refactor agent_runner and add the lead flow**

In `app/services/agent_runner.py`, extract the shared core and add the lead path. Replace the body of `process_professional_message` to delegate to `_run_with_memory`, and add `build_lead_deps` + `process_lead_message`:

```python
async def _run_with_memory(db: Session, agent, session, deps, text: str) -> str:
    """Replay history -> run agent -> persist turn -> fold summary. Owner-agnostic."""
    history = ChatHistoryService(db)
    message_history = to_model_messages(history.recent_messages(session, RAW_HISTORY_LIMIT))
    result = await agent.run(text, deps=deps, message_history=message_history)
    if _persist_turn(db, history, session, text, result.output):
        await _maybe_update_summary(history, session)
    return result.output


async def process_professional_message(db: Session, agent, user, text: str, phone: str) -> str:
    """Run the full memory flow for a known professional and return the reply text."""
    history = ChatHistoryService(db)
    session = history.get_or_create_session(user.id, phone or DEV_PHONE)
    deps = build_agent_deps(db, user, history_summary=session.summary)
    return await _run_with_memory(db, agent, session, deps, text)


def build_lead_deps(db: Session, lead, history_summary: str | None = None):
    from app.agents.deps import LeadAgentDeps
    from app.services.lead_service import LeadService

    return LeadAgentDeps(
        db=db,
        lead_id=lead.id,
        lead_name=lead.name,
        lead_phone=lead.phone,
        current_datetime=datetime.now(ZoneInfo(settings.TIMEZONE)),
        timezone=settings.TIMEZONE,
        history_summary=history_summary,
        lead_service=LeadService(db),
        trial_days=settings.LEAD_TRIAL_DAYS,
    )


async def process_lead_message(db: Session, agent, lead, text: str, phone: str) -> str:
    """Run the full memory flow for a lead (owner = lead) and return the reply text."""
    history = ChatHistoryService(db)
    session = history.get_or_create_lead_session(lead.id, phone or DEV_PHONE)
    deps = build_lead_deps(db, lead, history_summary=session.summary)
    return await _run_with_memory(db, agent, session, deps, text)
```

Note: `process_professional_message`'s observable behavior is unchanged — `tests/integration/test_ingestion_service.py` must still pass.

- [ ] **Step 5: Run the test (and the professional-path regression)**

Run: `uv run pytest tests/integration/test_lead_runner.py tests/integration/test_ingestion_service.py -v`
Expected: PASS (new lead test + existing professional tests still green).

- [ ] **Step 6: Commit**

```bash
git add app/services/chat_history_service.py app/services/agent_runner.py tests/integration/test_lead_runner.py
git commit -m "feat(lead): lead-owned session memory + process_lead_message"
```

---

### Task 9: Route inbound leads to the lead agent (+ outbound)

**Files:**
- Modify: `app/services/ingestion_service.py` (add `dispatch_lead_run`)
- Modify: `app/api/webhook_routes.py` (schedule `dispatch_lead_run` for leads)
- Test: `tests/integration/test_lead_ingestion.py`

**Interfaces:**
- Consumes: `process_lead_message` (Task 8), `LeadService` (Task 4), `build_lead_agent` (Task 6), `EvolutionOutboundAdapter`/`OutboundMessage` (Task 7), `InboundMessageRecord.agent_run_at`.
- Produces: `app.services.ingestion_service.dispatch_lead_run(inbound: InboundMessage, record_id: UUID) -> None` (atomic claim → run lead agent → send outbound; best-effort).

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_lead_ingestion.py
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.channels.inbound import InboundMessage
from app.core.database import SessionLocal
from app.models.chat_session import ChatMessage, ChatSession
from app.models.inbound_message import InboundMessageRecord
from app.models.lead import Lead
from app.services import ingestion_service
from app.services.ingestion_service import IngestionService, dispatch_lead_run

LEAD_PHONE = "5551900000050"
MSG_ID = "lead-ingest-msg-1"


def _inbound():
    return InboundMessage(
        provider="evolution", sender_phone=LEAD_PHONE, text="oi, o que é o simplifica?",
        provider_message_id=MSG_ID, timestamp=datetime(2026, 6, 22, 12, 0, tzinfo=UTC),
        recipient_phone=None, raw={"event": "messages.upsert"},
    )


def _noop(messages, info):
    return ModelResponse(parts=[TextPart("noop")])


def _build_lead_agent_with_noop():
    # Build with a FunctionModel so construction needs no real LLM creds; the actual
    # scripted reply is supplied per-call via agent.override(...).
    with patch("app.agents.lead_agent.get_llm_model", return_value=FunctionModel(_noop)):
        from app.agents.lead_agent import build_lead_agent
        return build_lead_agent()


def _scripted(text):
    async def fn(messages, info):
        return ModelResponse(parts=[TextPart(text)])
    return FunctionModel(fn)


def _cleanup(db):
    db.query(InboundMessageRecord).filter(
        InboundMessageRecord.provider_message_id == MSG_ID
    ).delete(synchronize_session=False)
    for lead in db.query(Lead).filter(Lead.phone == LEAD_PHONE).all():
        for s in db.query(ChatSession).filter(ChatSession.lead_id == lead.id):
            db.query(ChatMessage).filter(ChatMessage.session_id == s.id).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.lead_id == lead.id).delete(synchronize_session=False)
    db.query(Lead).filter(Lead.phone == LEAD_PHONE).delete(synchronize_session=False)
    db.commit()


async def test_lead_inbound_runs_agent_creates_lead_and_sends_reply(monkeypatch):
    db = SessionLocal()
    try:
        _cleanup(db)
        result = IngestionService(db).handle(_inbound())
        assert result.status == "lead" and result.record_id is not None
        record_id = result.record_id
    finally:
        db.close()

    agent = _build_lead_agent_with_noop()
    monkeypatch.setattr(ingestion_service, "build_lead_agent", lambda: agent)
    sender = MagicMock()
    sender.send.return_value = True
    monkeypatch.setattr(ingestion_service, "EvolutionOutboundAdapter", lambda settings: sender)

    with agent.override(model=_scripted("Oi! O Simplifica Psi te ajuda no consultório.")):
        await dispatch_lead_run(_inbound(), record_id)

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.phone == LEAD_PHONE).first()
        assert lead is not None
        session = db.query(ChatSession).filter(ChatSession.lead_id == lead.id).first()
        assert session is not None and session.user_id is None
        sender.send.assert_called_once()
        sent = sender.send.call_args[0][0]
        assert sent.to_phone == LEAD_PHONE and "Simplifica" in sent.text
    finally:
        _cleanup(db)
        db.close()


async def test_lead_dispatch_is_claimed_once(monkeypatch):
    db = SessionLocal()
    try:
        _cleanup(db)
        result = IngestionService(db).handle(_inbound())
        record_id = result.record_id
    finally:
        db.close()

    agent = _build_lead_agent_with_noop()
    monkeypatch.setattr(ingestion_service, "build_lead_agent", lambda: agent)
    monkeypatch.setattr(
        ingestion_service, "EvolutionOutboundAdapter",
        lambda settings: MagicMock(send=MagicMock(return_value=True)),
    )

    with agent.override(model=_scripted("ok")):
        await dispatch_lead_run(_inbound(), record_id)
        await dispatch_lead_run(_inbound(), record_id)  # second claims nothing

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.phone == LEAD_PHONE).first()
        session = db.query(ChatSession).filter(ChatSession.lead_id == lead.id).first()
        msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).count()
        assert msgs == 2
    finally:
        _cleanup(db)
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_lead_ingestion.py -v`
Expected: FAIL — `ImportError: cannot import name 'dispatch_lead_run'`.

- [ ] **Step 3: Add `dispatch_lead_run` to ingestion_service**

In `app/services/ingestion_service.py`, add module-scope imports (so tests can monkeypatch them) near `build_simplifica_agent`:

```python
from app.agents.lead_agent import build_lead_agent
from app.channels.evolution_outbound import EvolutionOutboundAdapter
from app.channels.outbound import OutboundMessage
from app.services.agent_runner import process_lead_message, process_professional_message
from app.services.lead_service import LeadService
```

Add the dispatcher (mirrors `dispatch_agent_run`'s atomic claim):

```python
async def dispatch_lead_run(inbound: InboundMessage, record_id: UUID) -> None:
    """Run the lead agent for an already-recorded lead message, exactly once, then
    send the reply back over WhatsApp (best-effort). Same atomic-claim guard as the
    professional path: UPDATE ... WHERE agent_run_at IS NULL wins for exactly one caller.
    """
    db = SessionLocal()
    try:
        claimed = (
            db.query(InboundMessageRecord)
            .filter(
                InboundMessageRecord.id == record_id,
                InboundMessageRecord.agent_run_at.is_(None),
            )
            .update(
                {InboundMessageRecord.agent_run_at: datetime.now(ZoneInfo(settings.TIMEZONE))},
                synchronize_session=False,
            )
        )
        db.commit()
        if not claimed:
            return
        lead = LeadService(db).get_or_create_lead(inbound.sender_phone)
        agent = build_lead_agent()
        reply = await process_lead_message(db, agent, lead, inbound.text, inbound.sender_phone)
        EvolutionOutboundAdapter(settings).send(
            OutboundMessage(to_phone=inbound.sender_phone, text=reply)
        )
    except Exception:  # noqa: BLE001 - background work must never raise
        logger.warning("lead run for inbound message failed", exc_info=True)
    finally:
        db.close()
```

- [ ] **Step 4: Wire the webhook route**

In `app/api/webhook_routes.py`, import `dispatch_lead_run`:

```python
from app.services.ingestion_service import (
    IngestionService,
    build_inbound_from_record,
    dispatch_agent_run,
    dispatch_lead_run,
    find_orphan_professional_messages,
)
```

In `_ingest_and_maybe_schedule`, add the lead branch after the professional one:

```python
    if result.status == "professional" and result.user_id is not None:
        background.add_task(dispatch_agent_run, inbound, result.user_id, result.record_id)
    elif result.status == "lead" and result.record_id is not None:
        background.add_task(dispatch_lead_run, inbound, result.record_id)
```

- [ ] **Step 5: Run the test (+ webhook regression)**

Run: `uv run pytest tests/integration/test_lead_ingestion.py tests/integration/test_ingestion_service.py -v`
Expected: PASS (lead ingestion + existing professional ingestion).

- [ ] **Step 6: Full suite + commit**

Run: `uv run pytest -q`
Expected: all green (non-live).

```bash
git add app/services/ingestion_service.py app/api/webhook_routes.py tests/integration/test_lead_ingestion.py
git commit -m "feat(lead): route inbound leads to LeadAgent + send reply (Evolution outbound)"
```

---

## Live verification (deferred, no Google required)

Não há dependência de Google nesta fatia. Quando rodarmos a bateria live (com LLM real e
outbound mockado), os cenários a habilitar/escrever são:
- conversa de lead (apresentação + FAQ) → resposta coerente;
- criação de conta de teste (nome + e-mail) → `User` em trial, lead `converted`;
- profissional cadastrado pergunta "como uso X?" → `SimplificaAgent` chama `product_help`.

Os cenários de cobrança/agenda existentes em `tests/live/test_agent_live_scenarios.py` não
mudam.

## Out of scope (deferred — documented)

- Link de pagamento / billing de ativação ("veremos depois").
- Outbound do profissional (resposta segue persistida, não enviada).
- Onboarding Google (calendário) da conta recém-criada.
- Meta outbound (só Evolution send neste slice).
- Orphan-sweep de leads (o claim atômico já impede double-run; varredura fica como follow-up).
