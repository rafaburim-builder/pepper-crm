"""
rfm.py — RFM (Recency, Frequency, Monetary) scoring for Pepper.

Scores each client 1–5 in three dimensions:
  R (Recency)   — tempo desde a última compra
  F (Frequency) — total de compras no período
  M (Monetary)  — valor total gasto

Segmentos (em PT-BR):
  🏆 Campeões         R≥4 AND F≥4 AND M≥4
  💎 Fiéis            F≥4 AND R≥3
  🌱 Potenciais Fiéis R≥4 AND F∈[2,3]
  ⚠️ Em Risco         R≤2 AND F≥3
  🌙 Hibernando       R≤2 AND F≤2 AND M≥2
  ❄️ Perdidos         R=1
  👤 Regular          (todos os demais)
"""
from datetime import datetime

import pandas as pd


# ── Tabelas de scoring ────────────────────────────────────────────────────────

def _r_score(days: int) -> int:
    """Recency: quanto mais recente, maior o score."""
    if days <= 90:   return 5   # ≤ 3 meses
    if days <= 180:  return 4   # 3–6 meses
    if days <= 365:  return 3   # 6–12 meses
    if days <= 730:  return 2   # 12–24 meses
    return 1                    # > 24 meses


def _f_score(count: int) -> int:
    """Frequency: quanto mais compras, maior o score."""
    if count >= 6:  return 5
    if count >= 4:  return 4
    if count == 3:  return 3
    if count == 2:  return 2
    return 1


def _m_score(value: float, p20: float, p40: float, p60: float, p80: float) -> int:
    """Monetary: baseado em percentis da distribuição de gasto total."""
    if value >= p80:  return 5
    if value >= p60:  return 4
    if value >= p40:  return 3
    if value >= p20:  return 2
    return 1


# ── Segmentos ─────────────────────────────────────────────────────────────────

_SEGMENT_RULES = [
    # (label, cor_hex, condição)  — primeira correspondência ganha
    ("🏆 Campeões",          "#D4002A", lambda r, f, m: r >= 4 and f >= 4 and m >= 4),
    ("💎 Fiéis",             "#E84300", lambda r, f, m: f >= 4 and r >= 3),
    ("🌱 Potenciais Fiéis",  "#F5A07A", lambda r, f, m: r >= 4 and f >= 2),
    ("⚠️ Em Risco",          "#F59E0B", lambda r, f, m: r <= 2 and f >= 3),
    ("🌙 Hibernando",        "#6B7280", lambda r, f, m: r <= 2 and f <= 2 and m >= 2),
    ("❄️ Perdidos",          "#94A3B8", lambda r, f, m: r == 1),
    ("👤 Regular",           "#C4B5A0", lambda r, f, m: True),   # fallback
]

SEGMENT_COLORS = {label: cor for label, cor, _ in _SEGMENT_RULES}

SEGMENT_PRIORITY = {
    "🏆 Campeões":         1,
    "💎 Fiéis":            2,
    "🌱 Potenciais Fiéis": 3,
    "⚠️ Em Risco":         4,
    "🌙 Hibernando":       5,
    "❄️ Perdidos":         6,
    "👤 Regular":          7,
}


def _get_segment(r: int, f: int, m: int) -> str:
    for label, _, cond in _SEGMENT_RULES:
        if cond(r, f, m):
            return label
    return "👤 Regular"


# ── Função principal ──────────────────────────────────────────────────────────

def score_rfm(
    df_retorno: pd.DataFrame,
    client_map: dict,
    today=None,
) -> pd.DataFrame:
    """
    Calcula scores RFM por cliente a partir do df_retorno.

    df_retorno esperado:
        codigo_cliente, ultima_compra, categoria, vlr_ultima_compra
        + opcionais: frequencia (int), valor_total (float)

    Retorna DataFrame ordenado por rfm_score DESC:
        codigo_cliente, nome, fone, R_dias, F_compras, M_total,
        R_score, F_score, M_score, rfm_score, segmento
    """
    if df_retorno is None or df_retorno.empty:
        return pd.DataFrame()

    if today is None:
        today = pd.Timestamp(datetime.now())

    df = df_retorno.copy()
    df["dias_desde"] = (today - pd.to_datetime(df["ultima_compra"])).dt.days.clip(lower=0)

    has_freq  = "frequencia"  in df.columns
    has_total = "valor_total" in df.columns

    # Agrega por cliente (soma todas as categorias)
    agg_dict: dict = {"R_dias": ("dias_desde", "min")}
    if has_freq:
        agg_dict["F_compras"] = ("frequencia", "sum")
    else:
        agg_dict["F_compras"] = ("dias_desde", "count")  # proxy: nº de categorias
    if has_total:
        agg_dict["M_total"] = ("valor_total", "sum")
    else:
        agg_dict["M_total"] = ("vlr_ultima_compra", "sum")

    agg = df.groupby("codigo_cliente").agg(**agg_dict).reset_index()
    agg["F_compras"] = agg["F_compras"].astype(int)

    # Percentis de M
    m_vals = agg["M_total"]
    p20 = float(m_vals.quantile(0.20))
    p40 = float(m_vals.quantile(0.40))
    p60 = float(m_vals.quantile(0.60))
    p80 = float(m_vals.quantile(0.80))

    agg["R_score"]  = agg["R_dias"].apply(_r_score)
    agg["F_score"]  = agg["F_compras"].apply(_f_score)
    agg["M_score"]  = agg["M_total"].apply(lambda x: _m_score(x, p20, p40, p60, p80))
    agg["rfm_score"] = agg["R_score"] + agg["F_score"] + agg["M_score"]
    agg["segmento"] = agg.apply(
        lambda row: _get_segment(row["R_score"], row["F_score"], row["M_score"]),
        axis=1,
    )

    # Enriquece com dados do client_map
    agg["nome"] = agg["codigo_cliente"].apply(
        lambda c: client_map.get(str(c), {}).get("nome", f"Cliente #{c}")
    )
    agg["fone"] = agg["codigo_cliente"].apply(
        lambda c: client_map.get(str(c), {}).get("fone", "")
    )

    cols = [
        "codigo_cliente", "nome", "fone",
        "R_dias", "F_compras", "M_total",
        "R_score", "F_score", "M_score", "rfm_score", "segmento",
    ]
    return agg[cols].sort_values("rfm_score", ascending=False).reset_index(drop=True)


def segment_summary(df_rfm: pd.DataFrame) -> pd.DataFrame:
    """Resumo por segmento: contagem e score médio."""
    if df_rfm.empty:
        return pd.DataFrame()
    return (
        df_rfm.groupby("segmento")
        .agg(
            Clientes=("codigo_cliente", "count"),
            Score_Médio=("rfm_score", "mean"),
            M_Médio=("M_total", "mean"),
        )
        .reset_index()
        .sort_values("Score_Médio", ascending=False)
        .rename(columns={"segmento": "Segmento"})
        .reset_index(drop=True)
    )
