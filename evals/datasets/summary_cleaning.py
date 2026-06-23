"""Summary-cleaning eval cases: junk removed, core facts kept.

NOTE: ExcludesAll/IncludesAll are case-insensitive SUBSTRING checks. Keep the
inputs free of collisions — a phone/date/price that contains an excluded token
(e.g. "200", "300") or a name that is a substring of another would silently
break an assertion. Choose distinctive tokens when adding cases.
"""

from __future__ import annotations

from pydantic_evals import Case, Dataset

from evals.evaluators import ExcludesAll, IncludesAll
from evals.harness import SummaryInputs


def build_summary_cleaning_dataset() -> Dataset:
    cases = [
        Case(
            name="limpa_fora_dominio",
            inputs=SummaryInputs(messages=[
                ("user", "cadastrei a Ana Souza, telefone 51 98765-4321, dia 15, 220 reais"),
                ("user", "me ajuda a escrever uma query SQL SELECT * FROM usuarios no postgres?"),
                ("assistant", "Desculpa, eu cuido só do seu consultório — clientes, agenda e cobrança."),
            ]),
            evaluators=[ExcludesAll(tokens=["SELECT", "SQL", "postgres"]),
                        IncludesAll(tokens=["Ana"])],
        ),
        Case(
            name="limpa_dado_substituido",
            inputs=SummaryInputs(
                existing_summary="Cliente Bruno Lima, consulta 200 reais, dia 10.",
                messages=[("user", "na verdade a consulta do Bruno passou pra 250")],
            ),
            evaluators=[ExcludesAll(tokens=["200"]), IncludesAll(tokens=["250", "Bruno"])],
        ),
        Case(
            name="limpa_fio_morto",
            inputs=SummaryInputs(messages=[
                ("user", "quero agendar um horario"),
                ("assistant", "Claro, para qual cliente e quando?"),
                ("user", "deixa pra la, esquece isso"),
                ("user", "muda o preço da Carla Dias para 300"),
            ]),
            evaluators=[ExcludesAll(tokens=["esquece", "deixa pra la"]),
                        IncludesAll(tokens=["Carla", "300"])],
        ),
        Case(
            name="limpa_vazamento_tecnico",
            inputs=SummaryInputs(messages=[
                ("user", "confirma o cadastro da Diana Reis"),
                ("assistant", "Cadastrei a Diana Reis (id 4f8c2a1e-9b7d-4c3a-8e21-aa1122334455) com sucesso"),
            ]),
            evaluators=[ExcludesAll(tokens=["4f8c2a1e"]), IncludesAll(tokens=["Diana"])],
        ),
        Case(
            name="preserva_pendencia_aberta",  # aggressive bias must NOT drop an open pendency
            inputs=SummaryInputs(messages=[
                ("user", "quero cadastrar a Ana Beatriz"),
                ("assistant", "Perfeito. Qual o telefone, o dia de cobrança e o valor da consulta da Ana Beatriz?"),
            ]),
            evaluators=[IncludesAll(tokens=["Ana Beatriz"])],
        ),
    ]
    return Dataset(name="summary_cleaning", cases=cases)
