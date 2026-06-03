"""
test_prescricao.py — Prescrição ótica por cliente (builder, iteração 19).

Por que existe:
  modules/prescricao.py foi criado pelo usuário em 01/06/2026 (receita por
  cliente + validade CFO de 1 ano + alerta de vencimento — base para a régua de
  recompra de lentes de grau). A regra de VENCIMENTO (validade_meses*30 dias) é
  lógica de negócio que aciona reativação; precisa estar travada por teste.

ESCOPO E SEGURANÇA:
  100% ISOLADO — prescricao._PATH aponta para tempfile; o data/prescricoes.json
  de produção (hoje inexistente) NÃO é criado nem tocado (guard confirma).
  Datas de vencimento são calculadas no próprio teste (sem depender do "hoje").
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import prescricao as rx  # noqa: E402


class _RxIsolated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._prod_path = rx._PATH
        cls._prod_existia = os.path.exists(cls._prod_path)
        cls._prod_mtime = (
            os.path.getmtime(cls._prod_path) if cls._prod_existia else None
        )

    @classmethod
    def tearDownClass(cls):
        if cls._prod_existia:
            assert os.path.getmtime(cls._prod_path) == cls._prod_mtime, (
                "prescricoes.json de produção foi modificado pela suíte!"
            )
        else:
            assert not os.path.exists(cls._prod_path), (
                "a suíte criou um prescricoes.json de produção indevidamente!"
            )

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        self._tmp = tmp.name
        self._orig = rx._PATH
        rx._PATH = self._tmp

    def tearDown(self):
        rx._PATH = self._orig
        if os.path.exists(self._tmp):
            os.unlink(self._tmp)

    @staticmethod
    def _data_str(d: date) -> str:
        return d.strftime("%d/%m/%Y")


class TestSaveEGet(_RxIsolated):
    def test_sem_receita_retorna_none(self):
        self.assertIsNone(rx.get_ultima_receita("999"))
        self.assertEqual(rx.count_total(), 0)

    def test_save_e_get_ultima(self):
        rx.save_prescricao("1", -2.5, -0.75, 90, -2.0, -0.5, 85, adicao=1.25)
        rec = rx.get_ultima_receita("1")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["od"]["esferico"], -2.5)
        self.assertEqual(rec["od"]["cilindrico"], -0.75)
        self.assertEqual(rec["od"]["eixo"], 90)
        self.assertEqual(rec["adicao"], 1.25)
        self.assertEqual(rec["validade_meses"], 12)

    def test_save_arredonda_e_coage_eixo_int(self):
        rx.save_prescricao("1", -2.567, -0.751, 90.9, 0, 0, 0)
        rec = rx.get_ultima_receita("1")
        self.assertEqual(rec["od"]["esferico"], -2.57)
        self.assertEqual(rec["od"]["cilindrico"], -0.75)
        self.assertEqual(rec["od"]["eixo"], 90)  # int(90.9) == 90

    def test_data_receita_default_e_hoje(self):
        rx.save_prescricao("1", 0, 0, 0, 0, 0, 0)
        rec = rx.get_ultima_receita("1")
        self.assertEqual(rec["data_receita"], date.today().strftime("%d/%m/%Y"))

    def test_mais_recente_primeiro(self):
        rx.save_prescricao("1", -1, 0, 0, -1, 0, 0, data_receita="01/01/2024")
        rx.save_prescricao("1", -2, 0, 0, -2, 0, 0, data_receita="01/01/2025")
        rec = rx.get_ultima_receita("1")
        self.assertEqual(rec["data_receita"], "01/01/2025")
        self.assertEqual(rec["od"]["esferico"], -2)
        self.assertEqual(rx.count_total(), 1)  # 1 cliente, 2 receitas

    def test_coercao_codigo_str(self):
        rx.save_prescricao(7, 0, 0, 0, 0, 0, 0)
        self.assertIsNotNone(rx.get_ultima_receita("7"))
        self.assertIsNotNone(rx.get_ultima_receita(7))


class TestVencimento(_RxIsolated):
    def test_dias_para_vencer_sem_receita(self):
        self.assertIsNone(rx.dias_para_vencer("999"))
        self.assertIsNone(rx.data_vencimento("999"))

    def test_dias_para_vencer_futuro(self):
        # receita de hoje, validade 12 meses (12*30 = 360 dias) → ~360 dias
        rx.save_prescricao("1", 0, 0, 0, 0, 0, 0,
                           data_receita=self._data_str(date.today()))
        self.assertEqual(rx.dias_para_vencer("1"), 360)

    def test_receita_vencida_da_negativo(self):
        antiga = date.today() - timedelta(days=400)  # 400 > 360
        rx.save_prescricao("1", 0, 0, 0, 0, 0, 0,
                           data_receita=self._data_str(antiga))
        self.assertLess(rx.dias_para_vencer("1"), 0)

    def test_data_vencimento_calculada(self):
        rec_dia = date(2026, 1, 1)
        rx.save_prescricao("1", 0, 0, 0, 0, 0, 0,
                           data_receita="01/01/2026", validade_meses=6)
        esperado = rec_dia + timedelta(days=6 * 30)
        self.assertEqual(rx.data_vencimento("1"), esperado)

    def test_data_receita_invalida_retorna_none(self):
        rx.save_prescricao("1", 0, 0, 0, 0, 0, 0, data_receita="data-ruim")
        self.assertIsNone(rx.dias_para_vencer("1"))
        self.assertIsNone(rx.data_vencimento("1"))


class TestFormatGrau(_RxIsolated):
    """format_grau é puro — não usa I/O."""

    def test_format_com_cilindrico(self):
        s = rx.format_grau({"esferico": -2.5, "cilindrico": -0.75, "eixo": 90})
        self.assertEqual(s, "-2,50 / -0,75 × 90°")

    def test_format_positivo_tem_sinal(self):
        s = rx.format_grau({"esferico": 1.25, "cilindrico": 0, "eixo": 0})
        self.assertTrue(s.startswith("+1,25"))

    def test_cilindrico_zero_vira_plano(self):
        s = rx.format_grau({"esferico": -1.0, "cilindrico": 0, "eixo": 0})
        self.assertIn("plano", s)

    def test_usa_virgula_decimal(self):
        s = rx.format_grau({"esferico": -3.0, "cilindrico": -1.5, "eixo": 45})
        self.assertNotIn(".", s)
        self.assertIn(",", s)


if __name__ == "__main__":
    unittest.main()
