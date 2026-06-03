"""
lgpd.py — Gerenciamento de consentimento LGPD por cliente.

Armazena opt-out em data/lgpd_optout.json: {codigo_cliente: {"optout": True, "data": "DD/MM/AAAA"}}
Opt-out subiu de 48h para 24h em 2026 — prazo máximo para remover da base após solicitação.

Uso:
  from modules.lgpd import is_optout, set_optout, load_optout
  if not is_optout(codigo):
      # pode enviar mensagem
"""
import json, os
from datetime import date

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH   = os.path.join(ROOT, "data", "lgpd_optout.json")


def load_optout() -> dict:
    if not os.path.exists(_PATH):
        return {}
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_optout(codigo: str) -> bool:
    return str(codigo) in load_optout()


def set_optout(codigo: str, nome: str = "", motivo: str = "") -> None:
    """Registra opt-out. Deve ser processado em até 24h."""
    data = load_optout()
    data[str(codigo)] = {
        "nome":    nome,
        "motivo":  motivo,
        "data":    date.today().strftime("%d/%m/%Y"),
        "prazo":   "24h — remover de todas as listas de contato",
    }
    _save(data)


def remove_optout(codigo: str) -> None:
    """Remove opt-out (cliente re-consentiu)."""
    data = load_optout()
    data.pop(str(codigo), None)
    _save(data)


def filter_optout(codigos: list) -> list:
    """Retorna apenas os códigos que NÃO estão em opt-out."""
    optouts = load_optout()
    return [c for c in codigos if str(c) not in optouts]


def optout_count() -> int:
    return len(load_optout())
