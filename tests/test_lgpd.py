"""
test_lgpd.py — Consentimento / opt-out LGPD (builder, iteração 19).

Por que existe:
  modules/lgpd.py foi criado pelo usuário em 01/06/2026 (item P2.1 do backlog —
  opt-out por cliente, prazo 24h). É a trava de COMPLIANCE que impede enviar
  mensagem a quem pediu para sair da base. Estava SEM teste.

ESCOPO E SEGURANÇA:
  100% ISOLADO — lgpd._PATH aponta para tempfile; o data/lgpd_optout.json de
  produção (hoje inexistente) NÃO é criado nem tocado pela suíte (guard confirma).
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import lgpd  # noqa: E402


class _LgpdIsolated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._prod_path = lgpd._PATH
        cls._prod_existia = os.path.exists(cls._prod_path)
        cls._prod_mtime = (
            os.path.getmtime(cls._prod_path) if cls._prod_existia else None
        )

    @classmethod
    def tearDownClass(cls):
        if cls._prod_existia:
            assert os.path.getmtime(cls._prod_path) == cls._prod_mtime, (
                "lgpd_optout.json de produção foi modificado pela suíte!"
            )
        else:
            assert not os.path.exists(cls._prod_path), (
                "a suíte criou um lgpd_optout.json de produção indevidamente!"
            )

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        self._tmp = tmp.name
        self._orig = lgpd._PATH
        lgpd._PATH = self._tmp

    def tearDown(self):
        lgpd._PATH = self._orig
        if os.path.exists(self._tmp):
            os.unlink(self._tmp)


class TestOptout(_LgpdIsolated):
    def test_base_vazia(self):
        self.assertEqual(lgpd.load_optout(), {})
        self.assertEqual(lgpd.optout_count(), 0)
        self.assertFalse(lgpd.is_optout("123"))

    def test_set_e_is_optout(self):
        lgpd.set_optout("123", nome="Cliente X", motivo="não quero")
        self.assertTrue(lgpd.is_optout("123"))
        self.assertEqual(lgpd.optout_count(), 1)

    def test_set_optout_grava_data_de_hoje_e_prazo(self):
        lgpd.set_optout("123")
        reg = lgpd.load_optout()["123"]
        self.assertEqual(reg["data"], date.today().strftime("%d/%m/%Y"))
        self.assertIn("24h", reg["prazo"])

    def test_codigo_coercao_para_string(self):
        # set com int, consulta com str e vice-versa devem casar.
        lgpd.set_optout(456)
        self.assertTrue(lgpd.is_optout("456"))
        self.assertTrue(lgpd.is_optout(456))

    def test_remove_optout(self):
        lgpd.set_optout("123")
        lgpd.remove_optout("123")
        self.assertFalse(lgpd.is_optout("123"))
        self.assertEqual(lgpd.optout_count(), 0)

    def test_remove_inexistente_nao_quebra(self):
        lgpd.remove_optout("naoexiste")  # não deve lançar
        self.assertEqual(lgpd.optout_count(), 0)

    def test_filter_optout_remove_quem_pediu_saida(self):
        lgpd.set_optout("2")
        lgpd.set_optout("4")
        restantes = lgpd.filter_optout(["1", "2", "3", "4", "5"])
        self.assertEqual(restantes, ["1", "3", "5"])

    def test_filter_optout_coercao_str(self):
        lgpd.set_optout("2")
        # lista com ints; o opt-out foi gravado como "2"
        self.assertEqual(lgpd.filter_optout([1, 2, 3]), [1, 3])

    def test_arquivo_corrompido_retorna_vazio(self):
        with open(self._tmp, "w", encoding="utf-8") as f:
            f.write("{ isto não é json")
        self.assertEqual(lgpd.load_optout(), {})
        self.assertFalse(lgpd.is_optout("1"))


if __name__ == "__main__":
    unittest.main()
