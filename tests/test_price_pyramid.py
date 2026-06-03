"""
Testes da classificação por faixa de preço (modules/price_pyramid.py).

Verifica o uso de preco_original vs vlr_unitario, a regra de "última faixa
é aberta (>= min)", e os resumos/percentuais de pirâmide.
"""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import price_pyramid as pp  # noqa: E402

TIERS = [
    {"label": "Entrada",  "min": 0,   "max": 200},
    {"label": "Médio",    "min": 200, "max": 500},
    {"label": "Premium",  "min": 500, "max": 99999},  # última: aberta
]


class TestClassifyTiers(unittest.TestCase):
    def test_usa_preco_original_quando_existe(self):
        df = pd.DataFrame({
            "preco_original": [100, 300, 900],
            "vlr_unitario":   [999, 999, 999],  # deve ser ignorado
        })
        out = pp.classify_tiers(df, TIERS)
        self.assertEqual(list(out["faixa"]), ["Entrada", "Médio", "Premium"])
        self.assertEqual(list(out["faixa_ordem"]), [0, 1, 2])

    def test_fallback_para_vlr_unitario(self):
        df = pd.DataFrame({"vlr_unitario": [150, 600]})
        out = pp.classify_tiers(df, TIERS)
        self.assertEqual(list(out["faixa"]), ["Entrada", "Premium"])

    def test_ultima_faixa_e_aberta(self):
        df = pd.DataFrame({"preco_original": [500, 1_000_000]})
        out = pp.classify_tiers(df, TIERS)
        self.assertEqual(list(out["faixa"]), ["Premium", "Premium"])

    def test_limite_inferior_inclusivo_superior_exclusivo(self):
        # 200 cai em "Médio" (>=200), não em "Entrada" (<200)
        df = pd.DataFrame({"preco_original": [199, 200]})
        out = pp.classify_tiers(df, TIERS)
        self.assertEqual(list(out["faixa"]), ["Entrada", "Médio"])

    def test_nao_muta_dataframe_original(self):
        df = pd.DataFrame({"preco_original": [100]})
        pp.classify_tiers(df, TIERS)
        self.assertNotIn("faixa", df.columns)  # copy() preserva o original


class TestPyramidFromData(unittest.TestCase):
    def test_df_vazio_distribui_uniforme(self):
        out = pp.pyramid_from_data(pd.DataFrame(), TIERS)
        self.assertEqual(set(out.keys()), {"Entrada", "Médio", "Premium"})
        for v in out.values():
            self.assertAlmostEqual(v, round(100 / 3, 1))

    def test_sem_tiers_retorna_vazio(self):
        self.assertEqual(pp.pyramid_from_data(pd.DataFrame(), []), {})

    def test_percentuais_de_receita(self):
        df = pd.DataFrame({
            "preco_original": [100, 300, 700],
            "vlr_total":      [100, 300, 600],  # total 1000
        })
        out = pp.pyramid_from_data(df, TIERS)
        self.assertAlmostEqual(out["Entrada"], 10.0)
        self.assertAlmostEqual(out["Médio"], 30.0)
        self.assertAlmostEqual(out["Premium"], 60.0)


class TestSummaries(unittest.TestCase):
    def test_category_summary_vazio(self):
        out = pp.build_category_summary(pd.DataFrame())
        self.assertTrue(out.empty)
        self.assertIn("ticket_medio", out.columns)

    def test_pyramid_summary_agrupa(self):
        df = pd.DataFrame({
            "categoria":      ["LV", "LV", "OC"],
            "preco_original": [100, 600, 300],
            "vlr_total":      [100, 600, 300],
            "quantidade":     [1, 1, 1],
            "vlr_unitario":   [100, 600, 300],
        })
        out = pp.build_pyramid_summary(df, TIERS)
        self.assertFalse(out.empty)
        self.assertIn("receita", out.columns)
        self.assertIn("volume", out.columns)


if __name__ == "__main__":
    unittest.main()
