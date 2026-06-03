"""
Testes de modules/dateutils.py — utilitários puros de data BR.

Cobre a semântica dia-primeiro, placeholders, ISO, e os DOIS predicados que
existem para corrigir bugs reais:
  * in_range / to_iso  -> fix do FUNIL-1 (comparação cronológica de período)
  * parse_br_date dia-primeiro -> fix do POSVENDA-2 (DD/MM ambíguo, dia<=12)

Inclui um teste de REGRESSÃO que demonstra o bug do FUNIL-1 (comparar strings
"DD/MM/AAAA") e prova que to_iso/in_range o resolvem — "o teste vira o checklist
do fix" (padrão Iter-19).

Módulo puro: nenhum I/O, nenhum dado de produção tocado.
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules import dateutils as du


class TestParseBrDate(unittest.TestCase):
    def test_ddmmaaaa(self):
        self.assertEqual(du.parse_br_date("02/06/2026"), date(2026, 6, 2))

    def test_dia_primeiro_dia_menor_que_12(self):
        # POSVENDA-2: "06/02/2026" deve ser 6 de FEVEREIRO, não 2 de junho.
        self.assertEqual(du.parse_br_date("06/02/2026"), date(2026, 2, 6))

    def test_dia_maior_que_12_inequivoco(self):
        self.assertEqual(du.parse_br_date("25/12/2025"), date(2025, 12, 25))

    def test_separador_traco(self):
        self.assertEqual(du.parse_br_date("02-06-2026"), date(2026, 6, 2))

    def test_iso(self):
        self.assertEqual(du.parse_br_date("2026-06-02"), date(2026, 6, 2))

    def test_iso_com_horario(self):
        self.assertEqual(du.parse_br_date("2026-06-02T14:30:00"), date(2026, 6, 2))
        self.assertEqual(du.parse_br_date("2026-06-02 14:30"), date(2026, 6, 2))

    def test_ano_2_digitos_pivot(self):
        self.assertEqual(du.parse_br_date("02/06/26"), date(2026, 6, 2))
        self.assertEqual(du.parse_br_date("02/06/85"), date(1985, 6, 2))

    def test_objetos_date_datetime(self):
        self.assertEqual(du.parse_br_date(date(2026, 6, 2)), date(2026, 6, 2))
        from datetime import datetime
        self.assertEqual(du.parse_br_date(datetime(2026, 6, 2, 9, 0)), date(2026, 6, 2))

    def test_placeholders_viram_none(self):
        for p in ["", " ", "-", "—", "00/00/0000", "0000-00-00", None, "nan", "NaT"]:
            self.assertIsNone(du.parse_br_date(p), f"placeholder {p!r} deveria virar None")

    def test_lixo_vira_none(self):
        for p in ["abc", "32/13/2026", "00/06/2026", "02/13/2026", "2026/06", "//", "1/2"]:
            self.assertIsNone(du.parse_br_date(p), f"{p!r} deveria virar None")

    def test_nunca_levanta(self):
        # robustez: qualquer entrada exótica -> None, sem exceção
        for p in [[], {}, 3.14, object()]:
            try:
                self.assertIsNone(du.parse_br_date(p))
            except Exception as e:  # pragma: no cover
                self.fail(f"parse_br_date levantou para {p!r}: {e}")


class TestToIso(unittest.TestCase):
    def test_ordenavel(self):
        self.assertEqual(du.to_iso("02/06/2026"), "2026-06-02")

    def test_invalida_vira_vazio(self):
        self.assertEqual(du.to_iso("-"), "")
        self.assertEqual(du.to_iso("lixo"), "")


class TestFunil1Regressao(unittest.TestCase):
    """Prova o bug FUNIL-1 e prova que to_iso/in_range o resolvem."""

    def test_string_compare_de_ddmmaaaa_eh_errado(self):
        # Bug original: comparar "DD/MM/AAAA" como texto.
        # 05/01/2026 (jan/2026) é DEPOIS de 10/12/2025 (dez/2025) no calendário,
        # mas como STRING "05/01/2026" < "10/12/2025" -> resultado errado.
        depois, antes = "05/01/2026", "10/12/2025"
        self.assertTrue(depois < antes)  # string compare: ERRADO (latente no funil)
        # to_iso conserta: a comparação passa a ser cronológica.
        self.assertTrue(du.to_iso(depois) > du.to_iso(antes))

    def test_in_range_filtra_periodo_corretamente(self):
        # Replica resumo_funil: visitas filtradas por [dt_ini, dt_fim] inclusivo.
        visitas = ["10/12/2025", "05/01/2026", "31/01/2026", "02/06/2026"]
        dentro = [v for v in visitas if du.in_range(v, "01/01/2026", "31/01/2026")]
        # com string-compare ingênuo "05/01/2026" cairia fora; aqui entra certo.
        self.assertEqual(dentro, ["05/01/2026", "31/01/2026"])

    def test_in_range_limites_inclusivos(self):
        self.assertTrue(du.in_range("01/01/2026", "01/01/2026", "01/01/2026"))

    def test_in_range_limites_abertos(self):
        self.assertTrue(du.in_range("02/06/2026", "", ""))
        self.assertTrue(du.in_range("02/06/2026", "01/01/2020", ""))
        self.assertFalse(du.in_range("02/06/2019", "01/01/2020", ""))

    def test_in_range_data_invalida_falsa(self):
        self.assertFalse(du.in_range("-", "01/01/2026", "31/12/2026"))


class TestCmpEDays(unittest.TestCase):
    def test_cmp(self):
        self.assertEqual(du.cmp_br("01/01/2026", "02/01/2026"), -1)
        self.assertEqual(du.cmp_br("02/01/2026", "01/01/2026"), 1)
        self.assertEqual(du.cmp_br("01/01/2026", "01/01/2026"), 0)

    def test_cmp_none_ordena_antes(self):
        self.assertEqual(du.cmp_br("-", "01/01/2026"), -1)
        self.assertEqual(du.cmp_br("01/01/2026", "-"), 1)
        self.assertEqual(du.cmp_br("-", "-"), 0)

    def test_days_between(self):
        self.assertEqual(du.days_between("01/01/2026", "31/01/2026"), 30)
        self.assertEqual(du.days_between("31/01/2026", "01/01/2026"), -30)

    def test_days_between_invalida(self):
        self.assertIsNone(du.days_between("-", "01/01/2026"))


class TestToBr(unittest.TestCase):
    def test_normaliza(self):
        self.assertEqual(du.to_br("2026-06-02"), "02/06/2026")
        self.assertEqual(du.to_br("2/6/26"), "02/06/2026")

    def test_invalida_vazio(self):
        self.assertEqual(du.to_br("lixo"), "")


if __name__ == "__main__":
    unittest.main()
