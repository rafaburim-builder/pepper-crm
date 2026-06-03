"""
email_queue.py — Fila de e-mails agendados para disparo no job das 02h.

Fluxo:
  1. RFM identifica clientes Em Risco / Hibernando com e-mail cadastrado.
  2. push_to_queue() adiciona cada um à fila em data/email_queue.json.
  3. O job _auto_update.py (02:00) chama process_queue() que envia via Brevo
     e move os registros para email_queue_history.json (últimos 500).

Estrutura de cada item da fila:
  {
    "id":         str,        # codigo_cliente
    "nome":       str,
    "email":      str,
    "assunto":    str,
    "mensagem":   str,        # texto plano (links wa.me já removidos)
    "segmento":   str,        # "Em Risco" | "Hibernando" | etc.
    "agendado_em": str,       # "DD/MM/YYYY HH:MM"
    "tentativas": int,
  }
"""
import json
import os
from datetime import datetime
from typing import List

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE     = os.path.join(ROOT, "data", "email_queue.json")
HISTORY   = os.path.join(ROOT, "data", "email_queue_history.json")
MAX_HIST  = 500
MAX_TRIES = 3


def _load(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(path: str, data: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def queue_size() -> int:
    return len(_load(QUEUE))


def push_to_queue(items: List[dict]) -> int:
    """Adiciona itens à fila. Ignora se o e-mail já estiver na fila.
    Retorna o número de novos itens adicionados."""
    fila = _load(QUEUE)
    emails_ja = {i["email"] for i in fila}
    novos = []
    now   = datetime.now().strftime("%d/%m/%Y %H:%M")
    for it in items:
        if it.get("email") and it["email"] not in emails_ja:
            novos.append({
                "id":          str(it.get("id", "")),
                "nome":        it.get("nome", ""),
                "email":       it["email"],
                "assunto":     it.get("assunto", ""),
                "mensagem":    it.get("mensagem", ""),
                "segmento":    it.get("segmento", ""),
                "agendado_em": now,
                "tentativas":  0,
            })
            emails_ja.add(it["email"])
    if novos:
        _save(QUEUE, fila + novos)
    return len(novos)


def process_queue() -> dict:
    """Envia todos os e-mails da fila via Brevo e arquiva o resultado.
    Deve ser chamado pelo job das 02h.
    Retorna {"enviados": int, "falhas": int, "erros": [str]}."""
    fila = _load(QUEUE)
    if not fila:
        return {"enviados": 0, "falhas": 0, "erros": []}

    from modules.email_sender import BrevoClient
    from modules.lgpd import is_optout
    client = BrevoClient.from_config()
    if not client:
        return {"enviados": 0, "falhas": len(fila),
                "erros": ["Brevo não configurado — verifique data/email_config.json"]}

    enviados, falhas, erros = 0, 0, []
    hist  = _load(HISTORY)
    nova_fila = []   # itens que não foram enviados mas ainda podem ser tentados

    for it in fila:
        # Backstop LGPD: se o cliente pediu opt-out DEPOIS de entrar na fila,
        # descarta no disparo — não envia nem reenfileira (prazo 24h da ANPD).
        if is_optout(it.get("id", "")):
            it["resultado"]     = "descartado: opt-out LGPD"
            it["processado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            hist.append(it)
            continue
        it["tentativas"] = it.get("tentativas", 0) + 1
        ok, msg = client.send_email(
            to_email  = it["email"],
            to_name   = it["nome"],
            subject   = it["assunto"],
            body_text = it["mensagem"],
        )
        it["resultado"]   = "enviado" if ok else f"falha: {msg}"
        it["processado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        hist.append(it)
        if ok:
            enviados += 1
        else:
            falhas += 1
            erros.append(f"{it['nome']} <{it['email']}>: {msg}")
            # Re-enfileira se ainda tem tentativas
            if it["tentativas"] < MAX_TRIES:
                nova_fila.append(it)

    _save(QUEUE, nova_fila)
    _save(HISTORY, hist[-MAX_HIST:])
    return {"enviados": enviados, "falhas": falhas, "erros": erros}


def get_history(limit: int = 50) -> list:
    return _load(HISTORY)[-limit:]
