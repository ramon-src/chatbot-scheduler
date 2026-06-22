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
