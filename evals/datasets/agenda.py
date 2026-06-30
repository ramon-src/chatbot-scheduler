"""Agenda eval cases: schedule, list, cancel, reschedule, conflict-warn (fake calendar)."""

from __future__ import annotations

from pydantic_evals import Case, Dataset

from evals.evaluators import DbState, NoLeakage, ToolSelected
from evals.harness import CaseInputs

_MARIA = {"clients": [
    {"name": "Maria Silva", "phone": "+5551999990000", "invoice_day": 10, "consult_price": 200},
]}
_MARIA_WITH_EVENT = {
    "clients": _MARIA["clients"],
    "events": [{"client": "Maria Silva", "start": "2026-06-24T10:00:00-03:00", "duration": 60}],
}
_TWO = {"clients": [
    {"name": "Maria Silva", "phone": "+5551999990000", "invoice_day": 10, "consult_price": 200},
    {"name": "Joao Souza", "phone": "+5551988887777", "invoice_day": 5, "consult_price": 180},
]}


def build_agenda_dataset() -> Dataset:
    cases = [
        Case(
            name="agenda_marca_unico",
            inputs=CaseInputs(agent="pro", setup=_MARIA,
                              messages=["agenda a Maria Silva amanhã às 10h"]),
            evaluators=[ToolSelected(tool="create_event"),
                        DbState(check={"event_for_client": "Maria"}), NoLeakage()],
        ),
        Case(
            name="agenda_lista_periodo",
            inputs=CaseInputs(agent="pro", setup=_MARIA_WITH_EVENT,
                              messages=["o que tenho essa semana?"]),
            evaluators=[ToolSelected(tool="list_events"), NoLeakage()],
        ),
        Case(
            name="agenda_lista_vazia",
            inputs=CaseInputs(agent="pro", setup=_MARIA,
                              messages=["tenho algo agendado hoje?"]),
            evaluators=[ToolSelected(tool="list_events"), NoLeakage()],
        ),
        Case(
            name="agenda_cancela",
            inputs=CaseInputs(agent="pro", setup=_MARIA_WITH_EVENT,
                              messages=["cancela o compromisso da Maria Silva dessa semana"]),
            evaluators=[ToolSelected(tool="cancel_event"), NoLeakage()],
        ),
        Case(
            name="agenda_reagenda",
            inputs=CaseInputs(agent="pro", setup=_MARIA_WITH_EVENT,
                              messages=["muda o compromisso da Maria Silva dessa semana para as 15h"]),
            evaluators=[ToolSelected(tool="reschedule_event"), NoLeakage()],
        ),
        Case(
            name="agenda_conflito_avisa",  # warn-not-block: the 2nd event still gets created
            inputs=CaseInputs(agent="pro", setup=_MARIA_WITH_EVENT,
                              messages=["cadastra o João Souza, telefone 51 98888-7777, dia 5, 180 reais",
                                        "agenda o João Souza quarta que vem às 10h"]),
            evaluators=[ToolSelected(tool="create_event"),
                        DbState(check={"event_for_client": "João"}), NoLeakage()],
        ),
        Case(
            name="agenda_homonimo_pede_telefone",
            inputs=CaseInputs(agent="pro", setup=_TWO,
                              messages=["agenda a Maria amanhã às 11h"]),
            evaluators=[NoLeakage()],
        ),
    ]
    return Dataset(name="agenda", cases=cases)
