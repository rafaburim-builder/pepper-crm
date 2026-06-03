"""
test_client_map_coverage.py — ALCANCE (reach) da base de clientes (builder, iteração 8).

Por que existe:
  Numa varredura SOMENTE-LEITURA da base de produção (1.825 clientes, 30/05/2026)
  medimos o alcance REAL dos canais de relacionamento do Pepper. Achados concretos:

    Canal WhatsApp (único canal ativo de reativação/aniversário):
      - 757/1825 = 41,5% têm telefone NORMALIZÁVEL (normalize_phone != "")
      - desses, 749 são CELULAR (11 díg.) e só 8 são FIXO (10 díg.)
      - => 58,4% da base NÃO é alcançável pelo WhatsApp hoje.

    Canal e-mail (NÃO existe no app hoje):
      - 1799/1825 = 98,6% têm e-mail preenchido.
      - => maior oportunidade de alcance: um canal de e-mail dobraria+ o alcance.

    Aniversário (campanha de aniversário usa o campo `aniversario` = mês 1-12):
      - 689/1825 = 37,8% têm `aniversario`. Quando presente, bate 100% com o mês
        de `nascimento` (689/689 conferidos).
      - Os 1136 sem `aniversario` têm `nascimento == "-"` (placeholder), NÃO uma data.
        Logo o limite de 37,8% é de QUALIDADE DE DADO de origem (export Microvix),
        não um bug de código — NÃO dá para recuperar via código. Vide tarefa
        DADOS-1 no relatório do builder.

    DDD padrão: config.ddd_padrao está vazio. Hoje custa +0 de alcance (nenhum
      telefone da base está sem DDD), mas é uma trava PREVENTIVA: se uma futura
      importação trouxer celulares de 9 díg. sem DDD, TODOS seriam descartados.
      Vide tarefa DADOS-2 (usar o botão "Detectar DDD automático" já existente).

ESCOPO E SEGURANÇA:
  Só funções PURAS — normalize_phone (modules.marketing) e _parse_month
  (modules.client_map) — e a métrica de alcance sobre uma base SINTÉTICA em memória.
  NÃO chama load/save/import sobre dados reais. Guard de mtime confirma que
  data/client_map.json de PRODUÇÃO não é tocado.
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.marketing import normalize_phone          # noqa: E402
from modules.client_map import _parse_month            # noqa: E402
from modules import client_map as cm                    # noqa: E402


def reachability_report(cmap, default_ddd=""):
    """Métrica PURA de alcance da base de clientes.

    Dado um mapa cod->entrada, mede o alcance de cada canal SEM escrever nada.
    Espelha exatamente como as campanhas decidem alcançar o cliente:
      - WhatsApp: make_whatsapp_link → normalize_phone(fone, ddd) != ""
      - E-mail  : campo 'email' não-vazio
      - Aniversário: campo 'aniversario' (mês 1-12) preenchido

    Retorna dict com contagens e percentuais.
    """
    total = len(cmap)

    def _pct(n):
        return (100.0 * n / total) if total else 0.0

    wa = 0
    wa_celular = 0
    wa_fixo = 0
    email = 0
    aniv = 0
    nasc_placeholder = 0  # nascimento preenchido mas não é data (ex.: "-")
    for v in cmap.values():
        v = v or {}
        phone = normalize_phone(v.get("fone", ""), default_ddd)
        if phone:
            wa += 1
            if len(phone) == 11:
                wa_celular += 1
            elif len(phone) == 10:
                wa_fixo += 1
        if (v.get("email") or "").strip():
            email += 1
        if v.get("aniversario"):
            aniv += 1
        nasc = (v.get("nascimento") or "").strip()
        if nasc and _parse_month(nasc) is None:
            nasc_placeholder += 1

    return {
        "total": total,
        "whatsapp": wa,
        "whatsapp_celular": wa_celular,
        "whatsapp_fixo": wa_fixo,
        "email": email,
        "aniversario": aniv,
        "nascimento_placeholder": nasc_placeholder,
        "pct_whatsapp": _pct(wa),
        "pct_email": _pct(email),
        "pct_aniversario": _pct(aniv),
    }


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
                "client_map.json de produção foi modificado pela suíte de teste!"
            )


class TestReachabilityMetric(_ClientMapGuard):
    """A métrica de alcance usada para auditar a base (sobre dados sintéticos)."""

    def _base(self):
        return {
            "1": {"nome": "A", "fone": "(11)91234-5678", "email": "a@x.com",
                  "aniversario": 7, "nascimento": "03/07/1982"},
            "2": {"nome": "B", "fone": "(61)8124-3666", "email": "",
                  "aniversario": 4, "nascimento": "11/04/1985"},   # fixo 10 díg.
            "3": {"nome": "C", "fone": "", "email": "c@x.com",
                  "aniversario": "", "nascimento": "-"},            # sem fone, placeholder
            "4": {"nome": "D", "fone": "telefone invalido", "email": "d@x.com",
                  "aniversario": "", "nascimento": "-"},            # fone inutilizável
        }

    def test_contagens_basicas(self):
        r = reachability_report(self._base())
        self.assertEqual(r["total"], 4)
        self.assertEqual(r["whatsapp"], 2)          # cliente 1 (cel) + 2 (fixo)
        self.assertEqual(r["whatsapp_celular"], 1)
        self.assertEqual(r["whatsapp_fixo"], 1)
        self.assertEqual(r["email"], 3)             # 1,3,4
        self.assertEqual(r["aniversario"], 2)       # 1,2
        self.assertEqual(r["nascimento_placeholder"], 2)  # clientes 3 e 4 ("-")

    def test_percentuais(self):
        r = reachability_report(self._base())
        self.assertAlmostEqual(r["pct_whatsapp"], 50.0)
        self.assertAlmostEqual(r["pct_email"], 75.0)
        self.assertAlmostEqual(r["pct_aniversario"], 50.0)

    def test_email_supera_whatsapp_neste_recorte(self):
        # Documenta o achado central: e-mail alcança mais que WhatsApp.
        r = reachability_report(self._base())
        self.assertGreater(r["email"], r["whatsapp"])

    def test_base_vazia_nao_divide_por_zero(self):
        r = reachability_report({})
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["pct_whatsapp"], 0.0)
        self.assertEqual(r["pct_email"], 0.0)


class TestDDDPreventivo(_ClientMapGuard):
    """Regressão do efeito do ddd_padrao: celular de 9 díg. sem DDD só vira
    alcançável SE houver DDD padrão configurado (config.ddd_padrao hoje vazio)."""

    def test_celular_9_digitos_sem_ddd_padrao_eh_descartado(self):
        cmap = {"1": {"fone": "91234-5678", "email": "", "aniversario": ""}}
        r = reachability_report(cmap, default_ddd="")
        self.assertEqual(r["whatsapp"], 0)

    def test_celular_9_digitos_com_ddd_padrao_eh_recuperado(self):
        cmap = {"1": {"fone": "91234-5678", "email": "", "aniversario": ""}}
        r = reachability_report(cmap, default_ddd="61")
        self.assertEqual(r["whatsapp"], 1)
        self.assertEqual(r["whatsapp_celular"], 1)


class TestNascimentoPlaceholder(_ClientMapGuard):
    """Regressão do achado de qualidade de dado: nascimento '-' NÃO é uma data,
    então o mês de aniversário não pode ser derivado dele (limite de origem)."""

    def test_placeholder_traco_nao_vira_mes(self):
        self.assertIsNone(_parse_month("-"))

    def test_data_real_vira_mes(self):
        self.assertEqual(_parse_month("03/07/1982"), 7)
        self.assertEqual(_parse_month("1982-07-03"), 7)


if __name__ == "__main__":
    unittest.main()
