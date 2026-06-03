"""
test_product_map.py — Testes dos HELPERS PUROS / SOMENTE-LEITURA de modules/product_map.py.

Por que existe (builder, iteração 6):
  product_map.py é a BASE FUNDAMENTAL do programa (módulo BLOQUEADO por governança).
  A função ref_to_category() é o coração do catálogo: ela decide a CATEGORIA de cada
  produto a partir do prefixo da referência (LV/OC/ML/LE/LC/AC/RE/OT). A ordem das
  regras é sutil e crítica — prefixos mais longos vencem os mais curtos:
    • "LV.MU..." é ML (Armação Multi), NÃO LV.
    • "LE.CO/LE.CT" são Lentes de Contato (LC), NÃO Lentes (LE).
  Se essa lógica mudar silenciosamente, todo relatório de mix por categoria fica
  errado — risco comercial direto. Travamos o comportamento atual com regressão.

ESCOPO E SEGURANÇA (importante):
  Por respeito ao cabeçalho de GOVERNANÇA do módulo, estes testes:
    • NÃO chamam import_from_df / import_from_api_data / save_map / _save_meta
      (qualquer função que ESCREVE no catálogo de produção).
    • Exercitam apenas funções PURAS (ref_to_category, get_entry) e de LEITURA
      (load_map, load_meta), e estas últimas com os caminhos do módulo
      monkeypatchados para arquivos TEMPORÁRIOS.
  Um guard em setUpClass/tearDownClass confirma que o mtime de
  data/produto_map.json de PRODUÇÃO não mudou durante a suíte.
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import json
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import product_map as pm  # noqa: E402


class _ProdMapGuard(unittest.TestCase):
    """Garante que o catálogo de produção nunca é tocado pela suíte."""

    @classmethod
    def setUpClass(cls):
        cls._prod_map = pm._MAP_PATH
        cls._prod_meta = pm._META_PATH
        cls._map_mtime = (
            os.path.getmtime(cls._prod_map) if os.path.exists(cls._prod_map) else None
        )
        cls._meta_mtime = (
            os.path.getmtime(cls._prod_meta) if os.path.exists(cls._prod_meta) else None
        )

    @classmethod
    def tearDownClass(cls):
        if cls._map_mtime is not None:
            assert os.path.exists(cls._prod_map), "produto_map.json de produção sumiu!"
            assert os.path.getmtime(cls._prod_map) == cls._map_mtime, (
                "produto_map.json de produção foi modificado pela suíte de teste!"
            )
        if cls._meta_mtime is not None:
            assert os.path.getmtime(cls._prod_meta) == cls._meta_mtime, (
                "produto_map_meta.json de produção foi modificado pela suíte de teste!"
            )


class TestRefToCategory(_ProdMapGuard):
    """Mapeamento prefixo-da-referência → categoria (lógica imutável)."""

    def test_armacoes_de_grau_LV(self):
        for ref in ("LV.IJ123", "LV.MT001", "LV.AL999", "LV.AC050"):
            self.assertEqual(pm.ref_to_category(ref), "LV", ref)

    def test_LV_MU_eh_multi_nao_grau(self):
        # Regra mais longa (LV.MU) vence o prefixo curto LV → categoria ML.
        self.assertEqual(pm.ref_to_category("LV.MU777"), "ML")

    def test_oculos_solar_OC(self):
        for ref in ("OC.AL10", "OC.CL20", "OC.MT30"):
            self.assertEqual(pm.ref_to_category(ref), "OC", ref)

    def test_armacao_multi_ML(self):
        self.assertEqual(pm.ref_to_category("ML0001"), "ML")

    def test_lentes_de_contato_LC_antes_de_lentes(self):
        # LE.CO / LE.CT precisam ser avaliados ANTES de LE.VI / LE.VA.
        self.assertEqual(pm.ref_to_category("LE.CO99"), "LC")
        self.assertEqual(pm.ref_to_category("LE.CT99"), "LC")

    def test_lentes_LE(self):
        self.assertEqual(pm.ref_to_category("LE.VI01"), "LE")
        self.assertEqual(pm.ref_to_category("LE.VA02"), "LE")

    def test_acessorios_relogios_outros(self):
        self.assertEqual(pm.ref_to_category("AC123"), "AC")
        self.assertEqual(pm.ref_to_category("RE456"), "RE")
        self.assertEqual(pm.ref_to_category("MA789"), "OT")

    def test_desconhecido_retorna_none(self):
        self.assertIsNone(pm.ref_to_category("ZZ999"))
        self.assertIsNone(pm.ref_to_category(""))

    def test_case_insensitive(self):
        self.assertEqual(pm.ref_to_category("lv.ij123"), "LV")
        self.assertEqual(pm.ref_to_category("le.co1"), "LC")

    def test_strip_espacos(self):
        self.assertEqual(pm.ref_to_category("   OC.AL10  "), "OC")

    def test_entrada_nao_string_eh_coergida(self):
        # str() interno não deve quebrar com tipos não-string.
        self.assertIsNone(pm.ref_to_category(12345))
        self.assertIsNone(pm.ref_to_category(None))


class TestGetEntry(_ProdMapGuard):
    """Lookup puro cod_produto → entrada."""

    def setUp(self):
        self.mapping = {
            "1001": {"referencia": "OC.AL10", "categoria": "OC"},
            "1002": {"referencia": "LV.IJ20", "categoria": "LV"},
        }

    def test_encontra_existente(self):
        self.assertEqual(pm.get_entry("1001", self.mapping)["categoria"], "OC")

    def test_inexistente_retorna_none(self):
        self.assertIsNone(pm.get_entry("9999", self.mapping))

    def test_coercao_e_strip_do_codigo(self):
        self.assertEqual(pm.get_entry(1001, self.mapping)["referencia"], "OC.AL10")
        self.assertEqual(pm.get_entry("  1002  ", self.mapping)["categoria"], "LV")

    def test_mapa_vazio(self):
        self.assertIsNone(pm.get_entry("1001", {}))


class _LeituraIsolada(_ProdMapGuard):
    """Aponta _MAP_PATH/_META_PATH para arquivos temporários (somente leitura)."""

    def setUp(self):
        self._prev_map = pm._MAP_PATH
        self._prev_meta = pm._META_PATH
        self._tmp = tempfile.mkdtemp(prefix="pepper-pm-test-")
        pm._MAP_PATH = os.path.join(self._tmp, "produto_map.json")
        pm._META_PATH = os.path.join(self._tmp, "produto_map_meta.json")

    def tearDown(self):
        pm._MAP_PATH = self._prev_map
        pm._META_PATH = self._prev_meta
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestLoadMap(_LeituraIsolada):

    def test_arquivo_ausente_retorna_dict_vazio(self):
        self.assertEqual(pm.load_map(), {})

    def test_json_corrompido_retorna_dict_vazio(self):
        with open(pm._MAP_PATH, "w", encoding="utf-8") as f:
            f.write("{ nao eh json valido ]")
        self.assertEqual(pm.load_map(), {})

    def test_json_valido_eh_lido(self):
        data = {"1001": {"referencia": "OC.AL10", "categoria": "OC"}}
        with open(pm._MAP_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        self.assertEqual(pm.load_map(), data)


class TestLoadMeta(_LeituraIsolada):

    def test_arquivo_ausente_retorna_dict_vazio(self):
        self.assertEqual(pm.load_meta(), {})

    def test_json_corrompido_retorna_dict_vazio(self):
        with open(pm._META_PATH, "w", encoding="utf-8") as f:
            f.write("<<corrompido>>")
        self.assertEqual(pm.load_meta(), {})

    def test_json_valido_eh_lido(self):
        meta = {"last_import": "30/05/2026 02:00", "total": 42, "historico": []}
        with open(pm._META_PATH, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        self.assertEqual(pm.load_meta(), meta)


if __name__ == "__main__":
    unittest.main()
