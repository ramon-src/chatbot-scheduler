"""Billing eval cases: mark paid, list pending, reminder (fake outbound)."""

from __future__ import annotations

from pydantic_evals import Case, Dataset

from evals.evaluators import DbState, NoLeakage, ToolSelected
from evals.harness import CaseInputs

_MONTHLY = {
    "clients": [{"name": "Maria Silva", "phone": "+5551999990000", "invoice_day": 10,
                 "consult_price": 200, "billing_mode": "monthly"}],
    "events": [{"client": "Maria Silva", "start": "2026-06-10T10:00:00-03:00", "duration": 60,
                "payment_status": "pending", "billable": True},
               {"client": "Maria Silva", "start": "2026-06-17T10:00:00-03:00", "duration": 60,
                "payment_status": "pending", "billable": True}],
}
_PER_SESSION = {
    "clients": [{"name": "Carla Dias", "phone": "+5551988887777", "invoice_day": 5,
                 "consult_price": 180, "billing_mode": "per_session"}],
    "events": [{"client": "Carla Dias", "start": "2026-06-24T09:00:00-03:00", "duration": 60,
                "payment_status": "pending", "billable": True}],
}


def build_billing_dataset() -> Dataset:
    cases = [
        Case(
            name="billing_marca_pago_mensal",
            inputs=CaseInputs(agent="pro", setup=_MONTHLY,
                              messages=["a Maria Silva pagou o mês"]),
            evaluators=[ToolSelected(tool="mark_paid"),
                        DbState(check={"session_paid_for_client": "Maria"}), NoLeakage()],
        ),
        Case(
            name="billing_lista_pendentes",
            inputs=CaseInputs(agent="pro", setup=_MONTHLY,
                              messages=["quem está com pagamento em aberto?"]),
            evaluators=[ToolSelected(tool="list_pending_payments"), NoLeakage()],
        ),
        Case(
            name="billing_lembrete",
            inputs=CaseInputs(agent="pro", setup=_MONTHLY,
                              messages=["manda um lembrete de pagamento pra Maria Silva"]),
            evaluators=[ToolSelected(tool="send_payment_reminder"), NoLeakage()],
        ),
        Case(
            name="billing_marca_pago_por_sessao",
            inputs=CaseInputs(agent="pro", setup=_PER_SESSION,
                              messages=["a Carla Dias pagou a consulta do dia 24 de junho"]),
            evaluators=[ToolSelected(tool="mark_paid"),
                        DbState(check={"session_paid_for_client": "Carla"}), NoLeakage()],
        ),
    ]
    return Dataset(name="billing", cases=cases)
