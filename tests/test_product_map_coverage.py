"""
test_product_map_coverage.py — COBERTURA DE CATEGORIA do catálogo (builder, iteração 7).

Por que existe:
  Numa varredura SOMENTE-LEITURA do catálogo de produção (56.342 produtos, 30/05/2026)
  descobrimos um GAP REAL na lógica de categorização de modules/product_map.py
  (módulo BLOQUEADO por governança). Estes prefixos de referência NÃO têm regra em
  `_PREFIX_RULES` e NÃO há fallback de 2 caracteres "OC"/"LV", então caem em None:

      OC.ES (27)  OC.KD (12)  OC.TN (3)   →  Óculos Solar variações (especial/kids/teen)
      LV.KD (7)   LV.TN (4)               →  Armação de Grau kids/teen

  Esses 53 produtos JÁ estão no catálogo com a categoria correta (foram importados sob
  um conjunto de regras anterior), mas numa RE-IMPORTAÇÃO seriam DESCARTADOS, porque
  import_from_df() pula entradas cujo ref_to_category()==None. Isso é uma armadilha
  silenciosa de perda de catálogo.

  Como o módulo é BLOQUEADO, NÃO corrigimos a regra aqui — apenas TRAVAMOS o
  comportamento atual com regressão e documentamos o gap. Quando o gestor de TI
  autorizar adicionar os fallbacks/regras, estes testes falharão de propósito e
  serão atualizados deliberadamente (o teste vira a checklist da correção).

ESCOPO E SEGURANÇA:
  Só funções PURAS (ref_to_category) e a métrica de cobertura sobre um catálogo
  SINTÉTICO em tempfile. NÃO chama import/save. Guard de mtime confirma que
  data/produto_map.json de PRODUÇÃO não é tocado.
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import product_map as pm  # noqa: E402


def category_coverage(mapping):
    """Métrica PURA de cobertura: dado um mapa cod->entrada, recalcula a categoria
    a partir da referência e conta quantos caem em None. Não escreve nada.
    Retorna {'total', 'sem_categoria', 'pct_sem_categoria', 'por_categoria'(Counter)}.
    """
    from collections import Counter
    por_cat = Counter()
    sem = 0
    for entry in mapping.values():
        ref = (entry or {}).get("referencia")
        cat = pm.ref_to_category(ref) if ref else None
        if cat is None:
            sem += 1
        por_cat[cat] += 1
    total = len(mapping)
    return {
        "total": total,
        "sem_categoria": sem,
        "pct_sem_categoria": (100.0 * sem / total) if total else 0.0,
        "por_categoria": por_cat,
    }


class _ProdMapGuard(unittest.TestCase):
    """Garante que o catálogo de produção nunca é tocado pela suíte."""

    @classmethod
    def setUpClass(cls):
        cls._prod_map = pm._MAP_PATH
        cls._map_mtime = (
            os.path.getmtime(cls._prod_map) if os.path.exists(cls._prod_map) else None
        )

    @classmethod
    def tearDownClass(cls):
        if cls._map_mtime is not None:
            assert os.path.exists(cls._prod_map), "produto_map.json de produção sumiu!"
            assert os.path.getmtime(cls._prod_map) == cls._map_mtime, (
                "produto_map.json de produção foi modificado pela suíte de teste!"
            )


class TestPrefixosNaoCategorizados(_ProdMapGuard):
    """REGRESSÃO dos prefixos de subtipo (módulo BLOQUEADO).

    HISTÓRICO:
      - Iter 7 (30/05) travou OC.ES, OC.KD, OC.TN, LV.KD, LV.TN como caindo em
        None, documentando o gap CATÁLOGO-1.
      - O gestor AUTORIZOU em 01/06/2026 adicionar 4 das 5 regras
        (OC.KD/OC.TN → OC ; LV.KD/LV.TN → LV) — vide comentários em
        _PREFIX_RULES de modules/product_map.py.
      - Iter 19 (02/06) atualizou estes testes DE PROPÓSITO para travar a nova
        realidade autorizada. OC.ES ficou de fora (gap remanescente CATÁLOGO-1b).

    Se o gestor autorizar criar a regra de OC.ES (ou um fallback), ATUALIZE estes
    testes de propósito — o teste é a checklist da correção.
    """

    # AINDA caem em None — regra não autorizada (gap remanescente CATÁLOGO-1b).
    GAP_PREFIXOS_AINDA_NONE = ("OC.ES1533", "OC.ES0001")
    # Autorizados em 01/06/2026 — agora categorizam.
    AUTORIZADOS_OC = ("OC.KD0918", "OC.TN0010")
    AUTORIZADOS_LV = ("LV.KD0001", "LV.TN0002")

    def test_oculos_solar_especial_ainda_cai_em_none(self):
        # OC.ES (27 SKUs) NÃO foi autorizado em 01/06 — segue caindo em None e
        # seria DESCARTADO numa re-importação. Trava o gap remanescente.
        for ref in self.GAP_PREFIXOS_AINDA_NONE:
            self.assertIsNone(
                pm.ref_to_category(ref),
                f"{ref}: OC.ES foi autorizado? Atualize este teste e o relatório.",
            )

    def test_subtipos_kids_teen_autorizados_categorizam(self):
        # Fix CATÁLOGO-1 (01/06/2026): kids/teen solar e grau agora categorizam.
        for ref in self.AUTORIZADOS_OC:
            self.assertEqual(pm.ref_to_category(ref), "OC", f"{ref} deveria ser OC")
        for ref in self.AUTORIZADOS_LV:
            self.assertEqual(pm.ref_to_category(ref), "LV", f"{ref} deveria ser LV")

    def test_nao_existe_fallback_curto_OC_LV(self):
        # Documenta que OC/LV "puros" (sem subtipo conhecido) NÃO são fallback.
        self.assertIsNone(pm.ref_to_category("OC.ZZ999"))
        self.assertIsNone(pm.ref_to_category("LV.ZZ999"))


class TestCategoryCoverage(_ProdMapGuard):
    """A métrica de cobertura usada para auditar o catálogo (sobre dados sintéticos)."""

    def test_catalogo_perfeito_zero_sem_categoria(self):
        mapping = {
            "1": {"referencia": "OC.AL01", "categoria": "OC"},
            "2": {"referencia": "LV.IJ02", "categoria": "LV"},
            "3": {"referencia": "LE.CO03", "categoria": "LC"},
        }
        r = category_coverage(mapping)
        self.assertEqual(r["total"], 3)
        self.assertEqual(r["sem_categoria"], 0)
        self.assertEqual(r["pct_sem_categoria"], 0.0)
        self.assertEqual(r["por_categoria"]["OC"], 1)

    def test_conta_os_que_caem_em_none(self):
        mapping = {
            "1": {"referencia": "OC.AL01", "categoria": "OC"},
            "2": {"referencia": "OC.ES99", "categoria": "OC"},   # gap remanescente → None
            "3": {"referencia": "LV.KD99", "categoria": "LV"},   # autorizado 01/06 → LV
            "4": {"referencia": "ZZ.ZZ99", "categoria": None},   # desconhecido → None
        }
        r = category_coverage(mapping)
        self.assertEqual(r["total"], 4)
        # Após o fix de 01/06, só OC.ES99 e ZZ.ZZ99 caem em None (LV.KD99 categoriza).
        self.assertEqual(r["sem_categoria"], 2)
        self.assertAlmostEqual(r["pct_sem_categoria"], 50.0)

    def test_entrada_sem_referencia_conta_como_sem_categoria(self):
        mapping = {"1": {"categoria": "OC"}, "2": {"referencia": "", "categoria": "OC"}}
        r = category_coverage(mapping)
        self.assertEqual(r["sem_categoria"], 2)

    def test_mapa_vazio_nao_divide_por_zero(self):
        r = category_coverage({})
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["pct_sem_categoria"], 0.0)


if __name__ == "__main__":
    unittest.main()
