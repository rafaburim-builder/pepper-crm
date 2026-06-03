"""
test_manager_coverage.py — painel de COBERTURA por território p/ o gerente
(builder, iteração 17).

Por que existe:
  A Iter 17 consolidou em `modules/manager_coverage.py` a lógica de cobertura por
  UF/cidade/canal/lote/mortos que, até a Iter 16, vivia espalhada em três arquivos
  de TESTE (test_geo_reach, test_uf_batch_roi, test_city_normalization) e que o app
  não conseguia importar. Esta suíte trava o CONTRATO da função unificada
  `manager_coverage_report` (e de `mortos_list`) sobre base SINTÉTICA, e faz uma
  passada SOMENTE-LEITURA na base de produção para registrar o número real (sem
  escrever nada).

ESCOPO E SEGURANÇA:
  Só funções PURAS sobre base sintética em memória + uma leitura read-only do
  client_map de produção. NÃO chama save/import. Guard de mtime confirma que
  data/client_map.json de PRODUÇÃO não é tocado.
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import manager_coverage as mc                # noqa: E402
from modules import client_map as cm                       # noqa: E402


class _ClientMapGuard(unittest.TestCase):
    """Garante que a base de clientes de produção nunca é tocada pela suíte."""

    @classmethod
    def setUpClass(cls):
        cls._prod = cm._FILE
        cls._mtime = os.path.getmtime(cls._prod) if os.path.exists(cls._prod) else None

    @classmethod
    def tearDownClass(cls):
        if cls._mtime is not None:
            assert os.path.exists(cls._prod), "client_map.json de produção sumiu!"
            assert os.path.getmtime(cls._prod) == cls._mtime, (
                "client_map.json de produção foi modificado pela suíte!"
            )


class TestHelpersPuros(unittest.TestCase):
    def test_is_valid_email(self):
        self.assertTrue(mc.is_valid_email("a@b.com"))
        self.assertTrue(mc.is_valid_email("  joao@x.com.br  "))
        for e in ["", None, "a@b", "sem", "a@@b.com"]:
            self.assertFalse(mc.is_valid_email(e))

    def test_norm_city_colapsa_acento_e_caixa(self):
        self.assertEqual(mc.norm_city("Brasília"), mc.norm_city("Brasilia"))
        self.assertEqual(mc.norm_city("Porto Ferreira"), mc.norm_city("porto  ferreira"))
        self.assertEqual(mc.norm_city("São Paulo"), "SAO PAULO")
        self.assertEqual(mc.norm_city(""), "")
        self.assertEqual(mc.norm_city(None), "")

    def test_is_batch_client(self):
        self.assertTrue(mc.is_batch_client({"cliente_desde": "15/05/2026"}))
        self.assertFalse(mc.is_batch_client({"cliente_desde": "22/07/2007"}))
        self.assertFalse(mc.is_batch_client({"cliente_desde": "-"}))
        self.assertFalse(mc.is_batch_client({}))
        self.assertTrue(mc.is_batch_client(
            {"cliente_desde": "01/01/2020"}, stamp=datetime.date(2020, 1, 1)))


class TestManagerCoverageReport(_ClientMapGuard):
    def _base(self):
        # SP: praça nativa de PDV — WhatsApp forte (2 fone + 1 só-email nativo)
        #     + 1 do lote sem fone
        # MG: PURO-LOTE — 2 do lote, ambos sem fone (só e-mail)
        # BA: 1 MORTO (sem nenhum canal)
        return {
            "1": {"uf": "SP", "cidade": "São Paulo", "nome": "Ana",
                  "fone": "(11)91234-5678", "email": "a@x.com",
                  "cliente_desde": "10/01/2020"},
            "2": {"uf": "sp", "cidade": "Campinas", "nome": "Beto",
                  "fone": "(11)98888-7777", "email": "b@x.com",
                  "cliente_desde": "05/06/2019"},
            "3": {"uf": "SP", "cidade": "Santos", "nome": "Caio",
                  "fone": "", "email": "c@x.com", "cliente_desde": "01/01/2015"},
            "4": {"uf": "SP", "cidade": "São Paulo", "nome": "Dora",
                  "fone": "", "email": "d@x.com", "cliente_desde": "15/05/2026"},
            "5": {"uf": "MG", "cidade": "Belo Horizonte", "nome": "Edu",
                  "fone": "", "email": "e@x.com", "cliente_desde": "15/05/2026"},
            "6": {"uf": "MG", "cidade": "Uberlândia", "nome": "Fil",
                  "fone": "tel invalido", "email": "f@x.com",
                  "cliente_desde": "15/05/2026"},
            "7": {"uf": "BA", "cidade": "Salvador", "nome": "Gal",
                  "fone": "", "email": "naoehemail", "cliente_desde": "15/05/2026"},
        }

    def test_totais_de_base(self):
        r = mc.manager_coverage_report(self._base())
        self.assertEqual(r["total"], 7)
        self.assertEqual(r["mortos"], 1)            # só o cliente 7 (BA)
        self.assertEqual(r["batch_total"], 4)       # 4,5,6,7
        self.assertEqual(r["wa_alcance"], 2)        # 1 e 2
        self.assertEqual(r["email_alcance"], 6)     # todos menos 7

    def test_uf_normalizado_e_agrupado(self):
        r = mc.manager_coverage_report(self._base())
        self.assertIn("SP", r["por_uf"])
        self.assertNotIn("sp", r["por_uf"])
        self.assertEqual(r["por_uf"]["SP"]["total"], 4)

    def test_whatsapp_concentrado_em_sp(self):
        r = mc.manager_coverage_report(self._base())
        self.assertEqual(r["wa_top_uf"], "SP")
        self.assertAlmostEqual(r["wa_top_uf_share"], 100.0)
        self.assertEqual(r["por_uf"]["MG"]["wa"], 0)
        self.assertEqual(r["por_uf"]["BA"]["wa"], 0)

    def test_puro_lote_e_status(self):
        r = mc.manager_coverage_report(self._base())
        self.assertTrue(r["por_uf"]["MG"]["puro_lote"])
        self.assertTrue(r["por_uf"]["BA"]["puro_lote"])   # 1 cli, lote, sem nativo
        self.assertFalse(r["por_uf"]["SP"]["puro_lote"])  # tem nativos
        # MG e BA são 100% lote → 2 praças puro-lote (BA é tb 'morta', ver status)
        self.assertEqual(r["ufs_puro_lote"], 2)
        self.assertEqual(r["por_uf"]["MG"]["status"], "PURO-LOTE / SO E-MAIL")
        self.assertEqual(r["por_uf"]["SP"]["status"], "WHATSAPP OK")
        self.assertEqual(r["por_uf"]["BA"]["status"], "SEM CANAL")

    def test_roi_ranking_e_total(self):
        r = mc.manager_coverage_report(self._base())
        # batch sem fone: SP #4(1), MG #5,#6(2), BA #7(1) = 4
        self.assertEqual(r["roi_total"], 4)
        self.assertEqual(r["roi_ranking"][0], ("MG", 2))   # maior ROI primeiro
        vals = [n for _, n in r["roi_ranking"]]
        self.assertEqual(vals, sorted(vals, reverse=True))

    def test_cidades_canonicas_nao_fragmenta(self):
        # "São Paulo" aparece em 2 registros (1 e 4) -> conta como 1 cidade em SP
        r = mc.manager_coverage_report(self._base())
        self.assertEqual(r["por_uf"]["SP"]["cidades"], 3)   # SP, Campinas, Santos
        # global: SP(3) + MG(2) + BA(1) = 6 praças distintas
        self.assertEqual(r["cidades_canonicas"], 6)

    def test_uf_ordenado_por_total_desc(self):
        r = mc.manager_coverage_report(self._base())
        self.assertEqual(r["uf_ordenado"][0], "SP")        # 4 > 2 > 1

    def test_ddd_padrao_recupera_wa(self):
        # celular 9 díg sem DDD numa praça nova: 0 sem ddd_padrao, 1 com ele
        cmap = {"1": {"uf": "AM", "fone": "91234-5678", "email": "",
                      "cliente_desde": "15/05/2026"}}
        self.assertEqual(
            mc.manager_coverage_report(cmap, default_ddd="")["por_uf"]["AM"]["wa"], 0)
        self.assertEqual(
            mc.manager_coverage_report(cmap, default_ddd="92")["por_uf"]["AM"]["wa"], 1)

    def test_base_vazia_nao_quebra(self):
        r = mc.manager_coverage_report({})
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["mortos"], 0)
        self.assertIsNone(r["wa_top_uf"])
        self.assertEqual(r["roi_ranking"], [])
        self.assertEqual(r["uf_ordenado"], [])


class TestMortosList(_ClientMapGuard):
    def test_lista_mortos_ordenada(self):
        cmap = {
            "1": {"uf": "SP", "cidade": "Santos", "nome": "Zeca",
                  "fone": "", "email": "x"},          # morto
            "2": {"uf": "SP", "cidade": "Santos", "nome": "Ana",
                  "fone": "", "email": ""},           # morto
            "3": {"uf": "SP", "cidade": "Santos", "nome": "Bia",
                  "fone": "(11)91234-5678", "email": ""},  # tem WA -> não é morto
        }
        out = mc.mortos_list(cmap)
        self.assertEqual([m["nome"] for m in out], ["Ana", "Zeca"])  # ordenado
        self.assertTrue(all(m["uf"] == "SP" for m in out))


class TestProducaoSomenteLeitura(_ClientMapGuard):
    """Roda a métrica sobre a base REAL (read-only) só para imprimir o número e
    garantir que não quebra com dados de produção. NÃO escreve nada."""

    def test_relatorio_prod_nao_quebra(self):
        cmap = cm.load_clients()
        r = mc.manager_coverage_report(cmap)
        self.assertEqual(r["total"], len(cmap))
        self.assertGreaterEqual(r["mortos"], 0)
        self.assertLessEqual(r["wa_alcance"], r["total"])
        print(
            f"\n[PROD manager_coverage] base={r['total']} "
            f"wa_alcance={r['wa_alcance']} email_alcance={r['email_alcance']} "
            f"mortos={r['mortos']} ufs_puro_lote={r['ufs_puro_lote']} "
            f"roi_total={r['roi_total']} wa_top_uf={r['wa_top_uf']}"
            f"({r['wa_top_uf_share']:.1f}%) cidades={r['cidades_canonicas']}"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
