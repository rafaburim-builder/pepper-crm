"""
funil.py — Registro de visitas à loja (topo do funil de vendas).

Captura visitas que NÃO geraram venda — o dado mais importante para
calcular a taxa de conversão real do vendedor.

Armazena em data/funil.json: lista de visitas (mais recentes primeiro).

Cada visita:
  {
    "id":              str (uuid curto),
    "data":            "DD/MM/AAAA",
    "hora":            "HH:MM",
    "visitante_nome":  str (pode ser vazio),
    "categoria":       str (LV/OC/ML/LE/LC/AC/""),
    "resultado":       str (RESULTADOS abaixo),
    "notas":           str,
    "vendedor_login":  str,
    "vendedor_nome":   str,
  }
"""
import json, os, uuid
from datetime import date, datetime
from typing import Optional

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(ROOT, "data", "funil.json")

RESULTADOS = [
    "Comprou",
    "Volta amanhã",
    "Pede orçamento",
    "Aguarda convênio",
    "Não tinha o modelo",
    "Saiu sem comprar",
]

RESULTADO_ICONS = {
    "Comprou":             "✅",
    "Volta amanhã":        "🔄",
    "Pede orçamento":      "📋",
    "Aguarda convênio":    "🏥",
    "Não tinha o modelo":  "❌",
    "Saiu sem comprar":    "👋",
}


def _load() -> list:
    if not os.path.exists(_PATH):
        return []
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(data: list) -> None:
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_visita(
    visitante_nome: str = "",
    categoria: str = "",
    resultado: str = "",
    notas: str = "",
    vendedor_login: str = "",
    vendedor_nome: str = "",
) -> str:
    """Adiciona uma visita. Retorna o id gerado."""
    visitas = _load()
    _id = uuid.uuid4().hex[:8]
    visitas.insert(0, {
        "id":             _id,
        "data":           date.today().strftime("%d/%m/%Y"),
        "hora":           datetime.now().strftime("%H:%M"),
        "visitante_nome": visitante_nome.strip(),
        "categoria":      categoria,
        "resultado":      resultado,
        "notas":          notas.strip(),
        "vendedor_login": vendedor_login,
        "vendedor_nome":  vendedor_nome,
    })
    _save(visitas[:2000])  # mantém últimas 2000 visitas
    return _id


def get_visitas_hoje(vendedor_login: str = "") -> list:
    hoje = date.today().strftime("%d/%m/%Y")
    visitas = _load()
    result = [v for v in visitas if v.get("data") == hoje]
    if vendedor_login:
        result = [v for v in result if v.get("vendedor_login") == vendedor_login]
    return result


def resumo_funil(dt_ini: str = "", dt_fim: str = "", vendedor_login: str = "") -> dict:
    """
    Resumo do funil num período.
    dt_ini / dt_fim: "DD/MM/AAAA". Vazios = todo o histórico.
    """
    from .dateutils import in_range
    visitas = _load()
    if dt_ini or dt_fim:
        visitas = [v for v in visitas if in_range(v.get("data", ""), dt_ini, dt_fim)]
    if vendedor_login:
        visitas = [v for v in visitas if v.get("vendedor_login") == vendedor_login]

    total      = len(visitas)
    conversoes = sum(1 for v in visitas if v.get("resultado") == "Comprou")
    por_resultado = {}
    for v in visitas:
        r = v.get("resultado", "—")
        por_resultado[r] = por_resultado.get(r, 0) + 1

    return {
        "total":          total,
        "conversoes":     conversoes,
        "taxa_conversao": round(conversoes / total * 100, 1) if total > 0 else 0.0,
        "por_resultado":  por_resultado,
    }
