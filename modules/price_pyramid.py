from typing import Dict, List

import pandas as pd


def classify_tiers(df: pd.DataFrame, tiers: List[Dict]) -> pd.DataFrame:
    """Classifica cada linha na faixa de preço pelo preço original (tabela).
    Usa 'preco_original' quando disponível; caso contrário usa 'vlr_unitario'.
    """
    df = df.copy()
    # Coluna de preço para classificação: preço original de tabela, não o preço de venda
    price_col = "preco_original" if "preco_original" in df.columns else "vlr_unitario"
    df["faixa"]       = "Outros"
    df["faixa_ordem"] = len(tiers)
    for i, t in enumerate(tiers):
        is_last = (i == len(tiers) - 1)
        if is_last:
            mask = df[price_col] >= t["min"]
        else:
            mask = (df[price_col] >= t["min"]) & (df[price_col] < t["max"])
        df.loc[mask, "faixa"]       = t["label"]
        df.loc[mask, "faixa_ordem"] = i
    return df


def build_pyramid_summary(df: pd.DataFrame, tiers: List[Dict]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["categoria", "faixa", "faixa_ordem", "receita", "volume"])
    df = classify_tiers(df, tiers)
    grouped = df.groupby(["categoria", "faixa", "faixa_ordem"], as_index=False).agg(
        receita=("vlr_total",    "sum"),
        volume =("quantidade",   "sum"),
    )
    return grouped.sort_values(["categoria", "faixa_ordem"])


def build_category_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["categoria", "receita", "volume", "ticket_medio"])
    grouped = df.groupby("categoria", as_index=False).agg(
        receita     =("vlr_total",    "sum"),
        volume      =("quantidade",   "sum"),
        ticket_medio=("vlr_unitario", "mean"),
    )
    return grouped.sort_values("receita", ascending=False)


def pyramid_from_data(df: pd.DataFrame, tiers: List[Dict]) -> Dict[str, float]:
    """Return {tier_label: pct_of_revenue} from actual sales data."""
    if not tiers:
        return {}
    even = round(100 / len(tiers), 1)
    if df.empty:
        return {t["label"]: even for t in tiers}
    df = classify_tiers(df, tiers)
    agg = df.groupby("faixa")["vlr_total"].sum()
    total = agg.sum()
    if total <= 0:
        return {t["label"]: even for t in tiers}
    return {
        t["label"]: round(float(agg.get(t["label"], 0)) / total * 100, 1)
        for t in tiers
    }
