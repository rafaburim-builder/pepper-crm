"""
prescricao.py — Prescrição ótica por cliente.

Armazena em data/prescricoes.json:
  {codigo_cliente: [lista de receitas, mais recente primeiro]}

Cada receita:
  {
    "od": {"esferico": float, "cilindrico": float, "eixo": int},
    "oe": {"esferico": float, "cilindrico": float, "eixo": int},
    "adicao": float,          # para progressivas / multifocais
    "data_receita": "DD/MM/AAAA",
    "validade_meses": 12,     # padrão: 1 ano (CFO)
    "optometrista": str,
    "observacoes": str,
    "registrado_em": "DD/MM/AAAA HH:MM",
  }
"""
import json, os
from datetime import date, timedelta, datetime
from typing import Optional

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(ROOT, "data", "prescricoes.json")


def _load() -> dict:
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


def get_ultima_receita(codigo: str) -> Optional[dict]:
    """Retorna a receita mais recente do cliente ou None."""
    data = _load()
    receitas = data.get(str(codigo), [])
    return receitas[0] if receitas else None


def save_prescricao(
    codigo: str,
    od_esf: float, od_cil: float, od_eix: int,
    oe_esf: float, oe_cil: float, oe_eix: int,
    adicao: float = 0.0,
    data_receita: str = "",
    validade_meses: int = 12,
    optometrista: str = "",
    observacoes: str = "",
) -> None:
    """Salva nova prescrição como a mais recente do cliente."""
    data = _load()
    historico = data.get(str(codigo), [])
    nova = {
        "od": {"esferico": round(od_esf, 2), "cilindrico": round(od_cil, 2), "eixo": int(od_eix)},
        "oe": {"esferico": round(oe_esf, 2), "cilindrico": round(oe_cil, 2), "eixo": int(oe_eix)},
        "adicao":          round(adicao, 2),
        "data_receita":    data_receita or date.today().strftime("%d/%m/%Y"),
        "validade_meses":  validade_meses,
        "optometrista":    optometrista,
        "observacoes":     observacoes,
        "registrado_em":   datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    data[str(codigo)] = [nova] + historico  # mais recente primeiro
    _save(data)


def dias_para_vencer(codigo: str) -> Optional[int]:
    """Dias até a receita vencer. Negativo = já venceu. None = sem receita."""
    rec = get_ultima_receita(str(codigo))
    if not rec:
        return None
    try:
        dt_rec = datetime.strptime(rec["data_receita"], "%d/%m/%Y").date()
        dt_venc = dt_rec + timedelta(days=rec.get("validade_meses", 12) * 30)
        return (dt_venc - date.today()).days
    except Exception:
        return None


def data_vencimento(codigo: str) -> Optional[date]:
    rec = get_ultima_receita(str(codigo))
    if not rec:
        return None
    try:
        dt_rec = datetime.strptime(rec["data_receita"], "%d/%m/%Y").date()
        return dt_rec + timedelta(days=rec.get("validade_meses", 12) * 30)
    except Exception:
        return None


def format_grau(grau_dict: dict) -> str:
    """Ex: -2,50 / -0,75 × 90"""
    esf = grau_dict.get("esferico", 0)
    cil = grau_dict.get("cilindrico", 0)
    eix = grau_dict.get("eixo", 0)
    esf_s = f"{esf:+.2f}".replace(".", ",")
    cil_s = f"{cil:+.2f}".replace(".", ",") if cil else "plano"
    return f"{esf_s} / {cil_s} × {eix}°"


def count_total() -> int:
    return len(_load())
