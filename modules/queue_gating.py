"""
queue_gating.py — peças PURAS para corrigir a régua de pós-venda na fila de e-mail.

Motivo de existir
-----------------
A régua de pós-venda (modules/pos_venda.py) cria 4 toques por venda
(D+1 / D+7 / D+30 / D+90) e os empurra para a fila (modules/email_queue.py).
Hoje isso NÃO funciona, por dois bugs latentes da mesma origem — a fila não
tem noção de "quando enviar":

  * POSVENDA-1 (email_queue.push_to_queue): a dedupe é só por e-mail
        emails_ja = {i["email"] for i in fila}
    Como os 4 toques compartilham o MESMO e-mail, D+7/D+30/D+90 entram como
    "duplicados" e são descartados — só o D+1 sobra na fila.

  * POSVENDA-3 (email_queue.process_queue): o disparo das 02h percorre a fila
    INTEIRA de uma vez. Não existe campo "enviar_em", então mesmo que os 4
    toques entrassem, todos sairiam no próximo job das 02h — o D+7/D+30/D+90
    nunca respeitaria a data prevista.

Este módulo centraliza, em STDLIB pura (reusando modules.dateutils), a lógica
que os dois fixes precisam:

  1. uma IDENTIDADE de deduplicação correta — (e-mail, segmento, data de envio)
     em vez de só o e-mail (resolve POSVENDA-1);
  2. um portão por DATA DE ENVIO — separa a fila entre "vence hoje" e "fica para
     depois" (resolve POSVENDA-3);
  3. um carimbo de data de envio D+N para a régua marcar cada toque.

Importante: módulo PURO — sem I/O, sem rede, sem estado global. NÃO é importado
pelo app; é uma peça pronta para ligar quando o app estiver parado. Seguro de
adicionar a qualquer momento. As instruções de fiação estão no relatório noturno.

Campo de fila proposto
----------------------
Cada item da fila ganha um campo opcional "enviar_em" (texto "DD/MM/AAAA").
Itens legados sem o campo são tratados como "vence agora" (compatível com o
comportamento atual), então ligar isto não trava nenhuma fila existente.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Optional

from . import dateutils as du

# Nome do campo de data de envio na fila (texto "DD/MM/AAAA").
SEND_FIELD = "enviar_em"


def _email_norm(item: dict) -> str:
    return str(item.get("email", "")).strip().lower()


def due_key(item: dict) -> tuple:
    """
    Identidade de deduplicação CORRETA de um item de fila.

    Usa (e-mail normalizado, segmento, data-de-envio-ISO). É o que resolve o
    POSVENDA-1: os 4 toques da régua têm o mesmo e-mail mas segmentos
    ("pos_venda_D+1".."D+90") e datas de envio diferentes — com esta chave eles
    deixam de colidir entre si, mas um re-scan da MESMA venda continua sendo
    deduplicado (mesmo e-mail+segmento+data => mesma chave).
    """
    return (_email_norm(item), str(item.get("segmento", "")),
            du.to_iso(item.get(SEND_FIELD, "")))


def dedupe_new(existing: Iterable[dict], new: Iterable[dict]) -> list:
    """
    Filtra `new`, devolvendo só os itens cuja due_key ainda não aparece em
    `existing` nem antes na própria leva `new`. Itens sem e-mail são ignorados.

    Substituto direto da lógica de dedupe de push_to_queue (que hoje usa só o
    e-mail). Não toca arquivo — o chamador é quem persiste.
    """
    vistos = {due_key(i) for i in existing if _email_norm(i)}
    saida = []
    for it in new:
        if not _email_norm(it):
            continue
        k = due_key(it)
        if k in vistos:
            continue
        vistos.add(k)
        saida.append(it)
    return saida


def is_due(item: dict, today: Optional[date] = None) -> bool:
    """
    True se o item deve ser enviado HOJE (ou já está atrasado).

    Sem "enviar_em" (ou valor inválido) => considera vencido AGORA, preservando
    o comportamento atual da fila para itens legados/reativação.
    """
    today = today or date.today()
    raw = item.get(SEND_FIELD, "")
    if not str(raw).strip():
        return True
    d = du.parse_br_date(raw)
    if d is None:
        return True
    return d <= today


def partition_due(fila: Iterable[dict], today: Optional[date] = None) -> tuple:
    """
    Separa a fila em (vencidos, pendentes) pela data de envio.

    É o portão que o process_queue precisa (POSVENDA-3): disparar só os
    `vencidos` e regravar os `pendentes` de volta na fila para outro dia.
    """
    today = today or date.today()
    vencidos, pendentes = [], []
    for it in fila:
        (vencidos if is_due(it, today) else pendentes).append(it)
    return vencidos, pendentes


def stamp_send_date(base, offset_days: int) -> str:
    """
    Data de envio "DD/MM/AAAA" = base + offset_days. base aceita date ou texto BR.
    "" se a base for inválida. Para a régua marcar cada toque (D+1/7/30/90).
    """
    if isinstance(base, date):
        b = base
    else:
        b = du.parse_br_date(base)
    if b is None:
        return ""
    return (b + timedelta(days=offset_days)).strftime("%d/%m/%Y")
