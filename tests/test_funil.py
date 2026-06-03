"""
test_funil.py — Funil de visitas / taxa de conversão (builder, iteração 19).

Por que existe:
  modules/funil.py foi criado pelo usuário em 01/06/2026 (item P1.3 do backlog —
  registro de visitas que NÃO viraram venda, base para a taxa de conversão real
  do vendedor/captador). É o maior valor comercial novo do app; sem teste.

  ⚠️ Esta suíte também DOCUMENTA um bug latente (FUNIL-1): resumo_funil() filtra
  o período comparando datas no formato "DD/MM/AAAA" como STRING — comparação
  lexicográfica que NÃO é cronológica entre meses/anos. Ver
  TestFunilDateRangeBugConhecido. Correção pendente (toca módulo importado pelo
  app → tarefa manual no relatório).

ESCOPO E SEGURANÇA:
  100% ISOLADO — funil._PATH aponta para tempfile; o data/funil.json de produção
  (hoje inexistente) NÃO é criado nem tocado (guard confirma).
  Datas controladas são gravadas direto no tempfile (add_visita carimba "hoje").
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import sys
import json
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import funil  # noqa: E402


class _FunilIsolated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._prod_path = funil._PATH
        cls._prod_existia = os.path.exists(cls._prod_path)
        cls._prod_mtime = (
            os.path.getmtime(cls._prod_path) if cls._prod_existia else None
        )

    @classmethod
    def tearDownClass(cls):
        if cls._prod_existia:
            assert os.path.getmtime(cls._prod_path) == cls._prod_mtime, (
                "funil.json de produção foi modificado pela suíte!"
            )
        else:
            assert not os.path.exists(cls._prod_path), (
                "a suíte criou um funil.json de produção indevidamente!"
            )

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        self._tmp = tmp.name
        self._orig = funil._PATH
        funil._PATH = self._tmp

    def tearDown(self):
        funil._PATH = self._orig
        if os.path.exists(self._tmp):
            os.unlink(self._tmp)

    def _seed(self, visitas):
        with open(self._tmp, "w", encoding="utf-8") as f:
            json.dump(visitas, f, ensure_ascii=False)


class TestAddVisita(_FunilIsolated):
    def test_add_retorna_id_e_persiste(self):
        _id = funil.add_visita(visitante_nome="  Ana  ", resultado="Comprou",
                               vendedor_login="joao")
        self.assertEqual(len(_id), 8)
        hoje = funil.get_visitas_hoje()
        self.assertEqual(len(hoje), 1)
        self.assertEqual(hoje[0]["id"], _id)
        self.assertEqual(hoje[0]["visitante_nome"], "Ana")  # strip aplicado
        self.assertEqual(hoje[0]["data"], date.today().strftime("%d/%m/%Y"))

    def test_mais_recente_primeiro(self):
        funil.add_visita(visitante_nome="primeiro")
        funil.add_visita(visitante_nome="segundo")
        visitas = funil.get_visitas_hoje()
        self.assertEqual(visitas[0]["visitante_nome"], "segundo")

    def test_get_visitas_hoje_filtra_vendedor(self):
        funil.add_visita(vendedor_login="joao")
        funil.add_visita(vendedor_login="maria")
        self.assertEqual(len(funil.get_visitas_hoje("joao")), 1)
        self.assertEqual(len(funil.get_visitas_hoje()), 2)

    def test_get_visitas_hoje_ignora_outros_dias(self):
        self._seed([{"data": "01/01/2020", "resultado": "Comprou",
                     "vendedor_login": "joao"}])
        self.assertEqual(funil.get_visitas_hoje(), [])


class TestResumoFunil(_FunilIsolated):
    def _v(self, data, resultado, vend="joao"):
        return {"data": data, "resultado": resultado, "vendedor_login": vend}

    def test_resumo_vazio_nao_divide_por_zero(self):
        r = funil.resumo_funil()
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["conversoes"], 0)
        self.assertEqual(r["taxa_conversao"], 0.0)

    def test_taxa_de_conversao(self):
        self._seed([
            self._v("01/06/2026", "Comprou"),
            self._v("01/06/2026", "Comprou"),
            self._v("01/06/2026", "Saiu sem comprar"),
            self._v("01/06/2026", "Pede orçamento"),
        ])
        r = funil.resumo_funil()
        self.assertEqual(r["total"], 4)
        self.assertEqual(r["conversoes"], 2)
        self.assertEqual(r["taxa_conversao"], 50.0)
        self.assertEqual(r["por_resultado"]["Comprou"], 2)
        self.assertEqual(r["por_resultado"]["Saiu sem comprar"], 1)

    def test_filtra_por_vendedor(self):
        self._seed([
            self._v("01/06/2026", "Comprou", "joao"),
            self._v("01/06/2026", "Comprou", "maria"),
        ])
        r = funil.resumo_funil(vendedor_login="joao")
        self.assertEqual(r["total"], 1)

    def test_filtra_periodo_mesmo_mes(self):
        # Dentro de um mesmo mês a comparação lexical coincide com a cronológica.
        self._seed([
            self._v("05/06/2026", "Comprou"),
            self._v("15/06/2026", "Comprou"),
            self._v("25/06/2026", "Saiu sem comprar"),
        ])
        r = funil.resumo_funil(dt_ini="10/06/2026", dt_fim="20/06/2026")
        self.assertEqual(r["total"], 1)  # só 15/06


class TestFunilDateRangeCronologico(_FunilIsolated):
    """FUNIL-1 (CORRIGIDO em v1.7.9): resumo_funil agora filtra cronologicamente
    via modules.dateutils.in_range. Antes comparava 'DD/MM/AAAA' como string e
    divergia entre meses/anos. Estes testes travam o comportamento correto.
    """

    def _v(self, data):
        return {"data": data, "resultado": "Comprou", "vendedor_login": "joao"}

    def test_visita_de_janeiro_entra_em_range_que_comeca_em_dezembro(self):
        # 02/01/2026 é cronologicamente DEPOIS de 10/12/2025, então deve entrar.
        self._seed([self._v("02/01/2026")])
        r = funil.resumo_funil(dt_ini="10/12/2025")
        self.assertEqual(r["total"], 1)

    def test_dentro_do_mesmo_ano_dias_altos_nao_passam_indevidamente(self):
        # 30/01/2026 (jan) vs dt_ini "15/06/2026" (jun): janeiro é antes de junho,
        # então deve ser EXCLUÍDO.
        self._seed([self._v("30/01/2026")])
        r = funil.resumo_funil(dt_ini="15/06/2026")
        self.assertEqual(r["total"], 0)

    def test_data_invalida_e_filtrada_fora(self):
        # Visita sem data válida não pode passar por filtro de período.
        self._seed([self._v(""), self._v("data-ruim"), self._v("10/06/2026")])
        r = funil.resumo_funil(dt_ini="01/06/2026", dt_fim="30/06/2026")
        self.assertEqual(r["total"], 1)


if __name__ == "__main__":
    unittest.main()
