"""
Product catalogue mapping: cod_produto → {referencia, categoria}
Populated via CSV import in Settings; stored in data/produto_map.json.

╔══════════════════════════════════════════════════════════════════════════════╗
║  MÓDULO BLOQUEADO — BASE FUNDAMENTAL DO PROGRAMA                           ║
║  Autorizado por: Gestor TI Chilli Beans                                    ║
║                                                                              ║
║  Este módulo NÃO deve ser alterado sem autorização expressa do gestor.      ║
║  Toda modificação de lógica de importação, mapeamento de categorias ou      ║
║  política de persistência requer aprovação explícita antes de qualquer      ║
║  alteração no código.                                                        ║
║                                                                              ║
║  POLÍTICA DE IMPORTAÇÃO — IMUTÁVEL:                                         ║
║  • Importações são SEMPRE ADITIVAS por padrão (merge=True).                 ║
║  • Entradas já catalogadas NUNCA são sobrescritas — nem pelo código,        ║
║    nem por importações futuras — a menos que force_overwrite=True seja      ║
║    passado explicitamente E o gestor confirme na interface.                 ║
║  • Metadados (data da última importação, histórico) salvos em               ║
║    produto_map_meta.json — histórico mantém as últimas 20 importações.      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import json
import os
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAP_PATH  = os.path.join(ROOT, "data", "produto_map.json")
_META_PATH = os.path.join(ROOT, "data", "produto_map_meta.json")

# Prefix → category  (longer prefixes checked first to avoid false matches)
# LV = Armações de Grau | OC = Óculos Solar | ML = Armações Multi
# LE = Lentes           | LC = Lentes de Contato | AC = Acessórios/Brindes
_PREFIX_RULES = [
    # ── Armações de Grau ──
    ("LV.IJ", "LV"),
    ("LV.MT", "LV"),
    ("LV.AL", "LV"),
    ("LV.AC", "LV"),
    ("LV.MU", "ML"),
    ("LV.KD", "LV"),   # Kids Grau   — autorizado 01/06/2026
    ("LV.TN", "LV"),   # Teen Grau   — autorizado 01/06/2026
    # ── Óculos Solar ──
    ("OC.AL", "OC"),
    ("OC.CL", "OC"),
    ("OC.MT", "OC"),
    ("OC.KD", "OC"),   # Kids Solar  — autorizado 01/06/2026
    ("OC.TN", "OC"),   # Teen Solar  — autorizado 01/06/2026
    # ── Armações Multi (2-char — após regras mais longas) ──
    ("ML",    "ML"),
    # ── Lentes de Contato (LE.CO / LE.CT — antes de LE.VI/LE.VA) ──
    ("LE.CO", "LC"),
    ("LE.CT", "LC"),
    # ── Lentes (LE.VI / LE.VA) ──
    ("LE.VI", "LE"),
    ("LE.VA", "LE"),
    # ── Acessórios / Brindes ──
    ("AC",    "AC"),
    # ── Relógios ──
    ("RE",    "RE"),
    # ── Outros (produtos variados MA.*) ──
    ("MA",    "OT"),
]


def ref_to_category(ref: str) -> Optional[str]:
    r = str(ref).upper().strip()
    for prefix, cat in _PREFIX_RULES:
        if r.startswith(prefix):
            return cat
    return None


def load_map() -> Dict[str, dict]:
    if not os.path.exists(_MAP_PATH):
        return {}
    try:
        with open(_MAP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_meta() -> dict:
    """Retorna metadados do catálogo: last_import, total, historico."""
    if not os.path.exists(_META_PATH):
        return {}
    try:
        with open(_META_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_map(mapping: Dict[str, dict]) -> None:
    os.makedirs(os.path.dirname(_MAP_PATH), exist_ok=True)
    with open(_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def _save_meta(mapping: Dict[str, dict], added: int, skipped: int, source: str) -> None:
    """Persiste metadados de importação."""
    os.makedirs(os.path.dirname(_META_PATH), exist_ok=True)
    meta = load_meta()
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    entry = {
        "data": now_str,
        "source": source,
        "adicionados": added,
        "ignorados": skipped,
        "total_catalogo": len(mapping),
    }
    meta["last_import"] = now_str
    meta["total"] = len(mapping)
    meta["historico"] = ([entry] + meta.get("historico", []))[:20]  # mantém últimas 20
    with open(_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def import_from_df(
    df: pd.DataFrame,
    merge: bool = True,
    source: str = "CSV",
    force_overwrite: bool = False,
) -> Dict[str, dict]:
    """
    Constrói e persiste o mapa de produtos a partir de um DataFrame.

    POLÍTICA IMUTÁVEL:
    - merge=True  (padrão): ADITIVO — adiciona novos produtos, preserva existentes.
    - merge=False + force_overwrite=True: substitui catálogo (requer autorização explícita do gestor).
    - merge=False sem force_overwrite=True: ignorado — comportamento aditivo é mantido por segurança.

    Espera colunas com 'cod' + 'produto' e 'refer'.
    Captura também: preço (preco_venda / preco / valor) e descrição.
    Retorna o mapa final persistido.
    """
    # Guarda de segurança: merge=False só é respeitado com force_overwrite=True explícito.
    # Isso garante que nenhuma chamada acidental possa apagar o catálogo.
    if not merge and not force_overwrite:
        merge = True  # forçado de volta para modo aditivo
    col_cod = next(
        (c for c in df.columns if "cod" in c.lower() and "produto" in c.lower()), None
    )
    col_ref = next((c for c in df.columns if "refer" in c.lower()), None)

    # Fallback: coluna auxiliar (Cód. Auxiliar) como referência se 'refer' não encontrado
    if col_ref is None:
        col_ref = next(
            (c for c in df.columns if "auxiliar" in c.lower() or "aux" in c.lower()), None
        )

    if col_cod is None or col_ref is None:
        raise ValueError(
            f"Planilha deve ter colunas 'Cod.Produto' e 'Referência' (ou 'Cód. Auxiliar'). "
            f"Colunas encontradas: {list(df.columns)}"
        )

    # Coluna de preço
    _price_candidates = ["preco_venda", "preco_cheio", "preco_tabela", "preco", "valor_venda", "valor"]
    col_price = next(
        (c for c in df.columns if c.lower().strip() in _price_candidates), None
    )
    if col_price is None:
        col_price = next(
            (c for c in df.columns
             if ("preco" in c.lower() or "valor" in c.lower() or "venda" in c.lower())
             and "mark" not in c.lower() and "up" not in c.lower()),
            None,
        )

    # Coluna de descrição
    _desc_candidates = ["descricao", "descrição", "nome", "nome_produto", "descr", "produto", "descrição"]
    col_desc = next(
        (c for c in df.columns if c.lower().strip() in _desc_candidates), None
    )
    if col_desc is None:
        col_desc = next(
            (c for c in df.columns if "descr" in c.lower() or "nome" in c.lower()), None
        )

    def _to_float(v) -> Optional[float]:
        try:
            return float(str(v).replace(".", "").replace(",", "."))
        except Exception:
            return None

    # Carrega mapa existente para merge
    existing: Dict[str, dict] = load_map() if merge else {}

    new_entries: Dict[str, dict] = {}
    for _, row in df.iterrows():
        cod = str(row[col_cod]).strip()
        if not cod or cod.lower() in ("nan", "none", ""):
            continue
        ref = str(row[col_ref]).strip()
        cat = ref_to_category(ref)
        if not cat:
            continue
        if cod in existing:
            continue  # ← preserva entrada já catalogada
        entry: dict = {"referencia": ref, "categoria": cat}
        if col_price is not None:
            preco = _to_float(row[col_price])
            if preco is not None and preco > 0:
                entry["preco_original"] = preco
        if col_desc is not None:
            desc = str(row[col_desc]).strip()
            if desc and desc.lower() not in ("nan", "none", ""):
                entry["descricao"] = desc
        new_entries[cod] = entry

    merged = {**existing, **new_entries}
    save_map(merged)
    _save_meta(merged, added=len(new_entries), skipped=len(df) - len(new_entries), source=source)
    return merged


def import_from_api_data(df: pd.DataFrame) -> Dict[str, dict]:
    """Constrói o mapa a partir do DataFrame retornado por LinxProdutos (aditivo)."""
    return import_from_df(df, merge=True, source="API LinxProdutos")


def get_entry(cod_produto: str, mapping: Dict[str, dict]) -> Optional[dict]:
    return mapping.get(str(cod_produto).strip())
