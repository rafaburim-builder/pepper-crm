"""
Testes da lógica de RFM (modules/rfm.py).

Cobrem: tabelas de score R/F/M, atribuição de segmento (ordem das regras)
e a função integradora score_rfm (agregação por cliente, percentis de M,
enriquecimento via client_map e ordenação por rfm_score).

Rodar (a partir da raiz do projeto):
    venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import pandas as pd

# Garante a raiz do projeto no sys.path (para importar `modules.*`)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import rfm  # noqa: E402


class TestScoreTables(unittest.TestCase):
    def test_r_score_faixas(self):
        self.assertEqual(rfm._r_score(0), 5)
        self.assertEqual(rfm._r_score(90), 5)
        self.assertEqual(rfm._r_score(91), 4)
        self.assertEqual(rfm._r_score(180), 4)
        self.assertEqual(rfm._r_score(181), 3)
        self.assertEqual(rfm._r_score(365), 3)
        self.assertEqual(rfm._r_score(366), 2)
        self.assertEqual(rfm._r_score(730), 2)
        self.assertEqual(rfm._r_score(731), 1)

    def test_f_score_faixas(self):
        self.assertEqual(rfm._f_score(0), 1)
        self.assertEqual(rfm._f_score(1), 1)
        self.assertEqual(rfm._f_score(2), 2)
        self.assertEqual(rfm._f_score(3), 3)
        self.assertEqual(rfm._f_score(4), 4)
        self.assertEqual(rfm._f_score(5), 4)
        self.assertEqual(rfm._f_score(6), 5)
        self.assertEqual(rfm._f_score(100), 5)

    def test_m_score_percentis(self):
        # p20=10, p40=20, p60=30, p80=40
        self.assertEqual(rfm._m_score(5,  10, 20, 30, 40), 1)
        self.assertEqual(rfm._m_score(10, 10, 20, 30, 40), 2)
        self.assertEqual(rfm._m_score(25, 10, 20, 30, 40), 3)
        self.assertEqual(rfm._m_score(35, 10, 20, 30, 40), 4)
        self.assertEqual(rfm._m_score(40, 10, 20, 30, 40), 5)
        self.assertEqual(rfm._m_score(999, 10, 20, 30, 40), 5)


class TestSegmentos(unittest.TestCase):
    def test_campeoes(self):
        self.assertEqual(rfm._get_segment(5, 5, 5), "🏆 Campeões")
        self.assertEqual(rfm._get_segment(4, 4, 4), "🏆 Campeões")

    def test_fieis(self):
        # f>=4 e r>=3, mas não campeão (m<4)
        self.assertEqual(rfm._get_segment(3, 4, 2), "💎 Fiéis")

    def test_potenciais_fieis(self):
        # r>=4 e f in [2,3], não cai em campeão/fiéis
        self.assertEqual(rfm._get_segment(4, 2, 1), "🌱 Potenciais Fiéis")

    def test_em_risco(self):
        self.assertEqual(rfm._get_segment(2, 3, 1), "⚠️ Em Risco")

    def test_hibernando(self):
        self.assertEqual(rfm._get_segment(2, 2, 2), "🌙 Hibernando")

    def test_perdidos(self):
        # r==1 e não casa nas regras anteriores
        self.assertEqual(rfm._get_segment(1, 1, 1), "❄️ Perdidos")

    def test_regular_fallback(self):
        self.assertEqual(rfm._get_segment(3, 1, 1), "👤 Regular")

    def test_ordem_das_regras_campeao_antes_de_fieis(self):
        # (5,5,5) satisfaz tanto Campeões quanto Fiéis; a 1ª regra deve ganhar
        self.assertEqual(rfm._get_segment(5, 5, 5), "🏆 Campeões")

    def test_todo_segmento_tem_cor_e_prioridade(self):
        for label in rfm.SEGMENT_PRIORITY:
            self.assertIn(label, rfm.SEGMENT_COLORS)


class TestScoreRfmIntegracao(unittest.TestCase):
    def setUp(self):
        self.today = pd.Timestamp("2026-01-01")
        self.df = pd.DataFrame({
            "codigo_cliente":    [1, 2, 3],
            "ultima_compra":     ["2025-12-22", "2024-01-01", "2025-10-01"],
            "categoria":         ["LV", "OC", "LE"],
            "vlr_ultima_compra": [1000.0, 100.0, 400.0],
            "frequencia":        [8, 1, 2],
            "valor_total":       [5000.0, 100.0, 800.0],
        })
        self.client_map = {
            "1": {"nome": "Ana Campeã",  "fone": "11999990001"},
            "2": {"nome": "Bruno Perdido", "fone": "11999990002"},
        }

    def test_df_vazio_retorna_vazio(self):
        self.assertTrue(rfm.score_rfm(pd.DataFrame(), {}).empty)
        self.assertTrue(rfm.score_rfm(None, {}).empty)

    def test_colunas_de_saida(self):
        out = rfm.score_rfm(self.df, self.client_map, today=self.today)
        for col in ["codigo_cliente", "nome", "fone", "R_dias", "F_compras",
                    "M_total", "R_score", "F_score", "M_score", "rfm_score",
                    "segmento"]:
            self.assertIn(col, out.columns)

    def test_recencia_em_dias(self):
        out = rfm.score_rfm(self.df, self.client_map, today=self.today)
        cli1 = out[out["codigo_cliente"] == 1].iloc[0]
        self.assertEqual(int(cli1["R_dias"]), 10)  # 2025-12-22 -> 2026-01-01

    def test_segmento_campeao_e_perdido(self):
        out = rfm.score_rfm(self.df, self.client_map, today=self.today)
        cli1 = out[out["codigo_cliente"] == 1].iloc[0]
        cli2 = out[out["codigo_cliente"] == 2].iloc[0]
        self.assertEqual(cli1["segmento"], "🏆 Campeões")
        self.assertEqual(cli2["segmento"], "❄️ Perdidos")

    def test_ordenado_por_rfm_desc(self):
        out = rfm.score_rfm(self.df, self.client_map, today=self.today)
        scores = list(out["rfm_score"])
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_enriquecimento_nome_e_fallback(self):
        out = rfm.score_rfm(self.df, self.client_map, today=self.today)
        cli1 = out[out["codigo_cliente"] == 1].iloc[0]
        cli3 = out[out["codigo_cliente"] == 3].iloc[0]
        self.assertEqual(cli1["nome"], "Ana Campeã")
        # cliente 3 não está no client_map -> nome fallback
        self.assertEqual(cli3["nome"], "Cliente #3")
        self.assertEqual(cli3["fone"], "")

    def test_summary_nao_vazio(self):
        out = rfm.score_rfm(self.df, self.client_map, today=self.today)
        resumo = rfm.segment_summary(out)
        self.assertFalse(resumo.empty)
        self.assertIn("Segmento", resumo.columns)


if __name__ == "__main__":
    unittest.main()
