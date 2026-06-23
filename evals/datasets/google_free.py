"""Google-free eval cases: Lead onboarding, Cliente CRUD, Formato."""

from __future__ import annotations

from pydantic_evals import Case, Dataset

from evals.evaluators import DbState, NoLeakage, ToolSelected
from evals.harness import CaseInputs

_REGISTERED_MARIA = {"clients": [
    {"name": "Maria Silva", "phone": "+5551999990000", "invoice_day": 10, "consult_price": 200},
]}
_TWO_MARIAS = {"clients": [
    {"name": "Maria Silva", "phone": "+5551999990000", "invoice_day": 10, "consult_price": 200},
    {"name": "Maria Santos", "phone": "+5551988887777", "invoice_day": 5, "consult_price": 180},
]}


def build_google_free_dataset() -> Dataset:
    cases = [
        # ---- Lead / onboarding ----
        Case(
            name="lead_duvida_produto",
            inputs=CaseInputs(agent="lead", messages=["oi, o que é o simplifica psi?"]),
            evaluators=[NoLeakage()],
        ),
        Case(
            name="lead_cria_conta",
            inputs=CaseInputs(agent="lead", messages=[
                "quero começar a usar",
                "meu nome é Ramon Schmidt",
                "meu email é ramon@exemplo.com",
            ]),
            evaluators=[ToolSelected(tool="create_professional_account"),
                        DbState(check={"lead_converted": True}), NoLeakage()],
        ),
        # ---- Cliente CRUD ----
        Case(
            name="cliente_criar_uma_msg",
            inputs=CaseInputs(agent="pro", messages=[
                "cadastra a Ana Souza, telefone 51 98765-4321, dia de cobrança 15, consulta 220 reais",
            ]),
            evaluators=[ToolSelected(tool="create_client"),
                        DbState(check={"client_named": "Ana", "client_price": ["Ana", 220]}),
                        NoLeakage()],
        ),
        Case(
            name="cliente_slot_filling",  # REGRESSÃO do bug de coleta fragmentada
            inputs=CaseInputs(agent="pro", messages=[
                "quero cadastrar um cliente",
                "51 98132-1543",
                "joao silva",
                "10",
                "200",
            ]),
            evaluators=[ToolSelected(tool="create_client"),
                        DbState(check={"client_named": "Joao"}), NoLeakage()],
        ),
        Case(
            name="cliente_mudar_preco",
            inputs=CaseInputs(agent="pro", setup=_REGISTERED_MARIA,
                              messages=["muda o valor da consulta da Maria Silva para 250 reais"]),
            evaluators=[ToolSelected(tool="update_client"),
                        DbState(check={"client_price": ["Maria Silva", 250]}), NoLeakage()],
        ),
        Case(
            name="cliente_telefone_duplicado",
            inputs=CaseInputs(agent="pro", setup=_REGISTERED_MARIA, messages=[
                "cadastra o João Teste, telefone 51 99999-0000, dia 5, consulta 100 reais",
            ]),
            evaluators=[ToolSelected(tool="create_client", success=False), NoLeakage()],
        ),
        Case(
            name="cliente_homonimo_pede_telefone",
            inputs=CaseInputs(agent="pro", setup=_TWO_MARIAS,
                              messages=["agenda a Maria amanhã às 11h"]),
            # agent must NOT create an event/client blindly; it asks for the phone.
            evaluators=[NoLeakage()],
        ),
        # ---- Formato / segurança ----
        Case(
            name="formato_sem_markdown_url",
            inputs=CaseInputs(agent="lead", messages=["me explica os recursos e o preço"]),
            evaluators=[NoLeakage()],
        ),
    ]
    return Dataset(name="google_free", cases=cases)
