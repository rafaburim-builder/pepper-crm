"""
test_client_map.py — Testes dos helpers PUROS de modules/client_map.py.

ESCOPO (importante):
  Só testamos funções SEM efeito colateral: _norm_key, _title_case,
  _parse_month, _parse_date_str. NÃO chamamos import_from_csv /
  import_from_api_data / save_clients porque eles ESCREVEM em
  data/client_map.json e data/client_meta.json (dados reais do app em
  produção). Esses fluxos com escrita devem ser testados só depois que o
  app.py for modularizado e os caminhos de dados forem injetáveis.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import client_map  # noqa: E402


class TestNormKey(unittest.TestCase):

    def test_remove_acentos(self):
        self.assertEqual(client_map._norm_key("Razão Social"), "razao social")

    def test_minusculas_e_strip(self):
        self.assertEqual(client_map._norm_key("  COD  "), "cod")

    def test_cidade_acentuada(self):
        self.assertEqual(client_map._norm_key("São Paulo"), "sao paulo")


class TestTitleCase(unittest.TestCase):

    def test_tudo_maiusculo_vira_title(self):
        self.assertEqual(client_map._title_case("JOAO DA SILVA"), "Joao Da Silva")

    def test_tudo_minusculo_vira_title(self):
        self.assertEqual(client_map._title_case("maria souza"), "Maria Souza")

    def test_misto_preservado(self):
        # nome já com capitalização mista não deve ser alterado
        self.assertEqual(client_map._title_case("McDonald's"), "McDonald's")

    def test_vazio(self):
        self.assertEqual(client_map._title_case(""), "")


class TestParseMonth(unittest.TestCase):

    def test_formato_br(self):
        self.assertEqual(client_map._parse_month("25/12/1990"), 12)

    def test_formato_iso(self):
        self.assertEqual(client_map._parse_month("1990-07-15"), 7)

    def test_ano_curto(self):
        self.assertEqual(client_map._parse_month("03/02/90"), 2)

    def test_invalida_retorna_none(self):
        self.assertIsNone(client_map._parse_month("data ruim"))

    def test_vazia_retorna_none(self):
        self.assertIsNone(client_map._parse_month(""))

    def test_mes_no_intervalo_valido(self):
        m = client_map._parse_month("01/01/2000")
        self.assertTrue(1 <= m <= 12)


class TestParseDateStr(unittest.TestCase):

    def test_normaliza_iso_para_br(self):
        self.assertEqual(client_map._parse_date_str("1990-07-15"), "15/07/1990")

    def test_mantem_br(self):
        self.assertEqual(client_map._parse_date_str("15/07/1990"), "15/07/1990")

    def test_ano_curto_expande(self):
        self.assertEqual(client_map._parse_date_str("03/02/90"), "03/02/1990")

    def test_vazia(self):
        self.assertEqual(client_map._parse_date_str(""), "")

    def test_nao_reconhecida_retorna_original_stripado(self):
        self.assertEqual(client_map._parse_date_str("  sem data  "), "sem data")


if __name__ == "__main__":
    unittest.main(verbosity=2)
