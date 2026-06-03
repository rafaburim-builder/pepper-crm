"""
test_geo_reach.py — ALCANCE GEOGRÁFICO por UF/cidade (builder, iteração 13).

Por que existe:
  Numa varredura SOMENTE-LEITURA da base de produção (1.825 clientes, 31/05/2026)
  cruzamos o alcance dos canais com a GEOGRAFIA (uf, cidade). O objetivo é medir
  a contactabilidade por TERRITÓRIO — relevante para a dinâmica de óticas, onde
  captadores externos, vendedores e gerentes trabalham por praça.

  ACHADO-CHAVE (GEO-1, a manchete da noite):
    O WhatsApp — ÚNICO canal ativo de reativação/aniversário — é, na prática,
    um canal QUASE EXCLUSIVO DE SÃO PAULO. Alcance WhatsApp por UF:
        SP 70,4%  |  MG 2,6%  |  BA 1,6%  |  RJ 1,6%  |  DF 7,8%
        PR 0,0% · GO 2,2% · PA 0,0% · SC 0,0% · MT 0,0% · PE 0,0% · RS 0,0% ...
    Ou seja: fora de SP, a base é alcançável SOMENTE por e-mail (canal que o app
    ainda não tem). Um captador/vendedor de QUALQUER praça fora de SP não consegue
    usar a ferramenta de reativação por WhatsApp para praticamente todo o território.

  POR QUÊ (causa-raiz, conecta com DADOS-7 da iteração 12):
    O lote de importação de 15/05/2026 (1.060 clientes, 58% da base) é
    e-mail-rico / telefone-pobre e está espalhado por TODAS as UFs fora de SP —
    1.059 desses clientes não têm telefone normalizável. Eles formam ~100% das
    bases de MG/BA/RJ/PR/GO/PA/MT/PE/RS/ES, derrubando o WhatsApp dessas praças
    a ~0%. As praças "nativas" de PDV (concentradas em SP) é que sustentam o WA.

  ACHADO-2 (confirma Iter-9/10 com lente geográfica):
    MORTOS (sem NENHUM canal: nem WhatsApp nem e-mail VÁLIDO) = 18/1825 = 1,0%.
    O e-mail é o canal quase-universal: quem não tem WhatsApp quase sempre tem
    e-mail válido. Em % os mortos se concentram em praças pequenas (SC 5,0%,
    RN 4,3%, DF 3,9%) — bolsões a sanear, não um problema de massa.

  IMPLICAÇÃO COMERCIAL (vide GEO-1 no relatório):
    A reativação por WhatsApp é uma alavanca SP-only hoje. Para dar ferramenta de
    relacionamento aos captadores/vendedores fora de SP, CANAL-EMAIL deixa de ser
    "nice to have" e vira pré-requisito de cobertura territorial. Enquanto isso,
    o painel deveria sinalizar ao gerente quais praças estão "sem canal de WhatsApp".

ESCOPO E SEGURANÇA:
  Só funções PURAS — normalize_phone (modules.marketing), is_valid_email e a
  métrica geo_reach_report sobre base SINTÉTICA em memória. NÃO chama
  load/save/import sobre dados reais. Guard de mtime confirma que
  data/client_map.json de PRODUÇÃO não é tocado.
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.marketing import normalize_phone          # noqa: E402
from modules import client_map as cm                    # noqa: E402

# Mesmo critério de formato usado nas iterações 9/10 (regex simples de formato;
# NÃO valida entregabilidade — placeholders tipo naotem@gmail.com passam, e são
# tratados à parte em test_contact_dedup.py).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(e):
    """True se o e-mail tem FORMATO válido (não garante entrega)."""
    return bool(_EMAIL_RE.match((e or "").strip()))


def geo_reach_report(cmap, default_ddd=""):
    """Métrica PURA de alcance por UF — sem escrever nada.

    Para cada UF mede: total, alcance WhatsApp (telefone normalizável),
    alcance e-mail (formato válido) e MORTOS (sem nenhum dos dois).
    Também devolve agregados de base e o UF que concentra o WhatsApp.

    Retorna dict:
      {
        "total": int,
        "mortos": int,                 # base inteira sem canal
        "por_uf": { uf: {total, whatsapp, email, mortos,
                          pct_whatsapp, pct_email, pct_mortos} },
        "wa_top_uf": uf | None,        # UF com mais clientes alcançáveis por WA
        "wa_top_uf_share": float,      # % do alcance-WA total concentrado nesse UF
      }
    """
    total = len(cmap)
    por_uf = {}
    wa_total = 0
    for v in cmap.values():
        v = v or {}
        uf = (v.get("uf") or "").strip().upper() or "(vazio)"
        d = por_uf.setdefault(
            uf, {"total": 0, "whatsapp": 0, "email": 0, "mortos": 0}
        )
        d["total"] += 1
        phone = bool(normalize_phone(v.get("fone", ""), default_ddd))
        email = is_valid_email(v.get("email", ""))
        if phone:
            d["whatsapp"] += 1
            wa_total += 1
        if email:
            d["email"] += 1
        if not phone and not email:
            d["mortos"] += 1

    mortos = 0
    for uf, d in por_uf.items():
        t = d["total"]
        d["pct_whatsapp"] = (100.0 * d["whatsapp"] / t) if t else 0.0
        d["pct_email"] = (100.0 * d["email"] / t) if t else 0.0
        d["pct_mortos"] = (100.0 * d["mortos"] / t) if t else 0.0
        mortos += d["mortos"]

    wa_top_uf = None
    wa_top_uf_share = 0.0
    if wa_total:
        wa_top_uf = max(por_uf, key=lambda u: por_uf[u]["whatsapp"])
        wa_top_uf_share = 100.0 * por_uf[wa_top_uf]["whatsapp"] / wa_total

    return {
        "total": total,
        "mortos": mortos,
        "por_uf": por_uf,
        "wa_top_uf": wa_top_uf,
        "wa_top_uf_share": wa_top_uf_share,
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


class TestIsValidEmail(_ClientMapGuard):
    def test_validos(self):
        self.assertTrue(is_valid_email("a@b.com"))
        self.assertTrue(is_valid_email("  joao.silva@empresa.com.br  "))

    def test_invalidos(self):
        for e in ["", None, "  ", "sememail", "a@b", "a@@b.com", "a b@c.com"]:
            self.assertFalse(is_valid_email(e))


class TestGeoReachMetric(_ClientMapGuard):
    """A métrica geográfica usada para auditar a base (sobre dados sintéticos
    que reproduzem o padrão real: WhatsApp concentrado em uma praça, restante
    alcançável só por e-mail)."""

    def _base(self):
        return {
            # SP: praça "nativa" de PDV — WhatsApp forte
            "1": {"uf": "SP", "cidade": "São Paulo",
                  "fone": "(11)91234-5678", "email": "a@x.com"},
            "2": {"uf": "sp", "cidade": "Campinas",        # uf minúsculo -> normaliza
                  "fone": "(11)98888-7777", "email": "b@x.com"},
            "3": {"uf": "SP", "cidade": "Santos",
                  "fone": "", "email": "c@x.com"},          # só e-mail
            # MG: lote 15/05 — só e-mail
            "4": {"uf": "MG", "cidade": "Belo Horizonte",
                  "fone": "", "email": "d@x.com"},
            "5": {"uf": "MG", "cidade": "Uberlândia",
                  "fone": "telefone invalido", "email": "e@x.com"},
            # BA: um MORTO (sem canal nenhum)
            "6": {"uf": "BA", "cidade": "Salvador",
                  "fone": "", "email": "naoehemail"},
        }

    def test_total_e_mortos(self):
        r = geo_reach_report(self._base())
        self.assertEqual(r["total"], 6)
        self.assertEqual(r["mortos"], 1)               # só o cliente 6

    def test_uf_normalizado_e_agrupado(self):
        r = geo_reach_report(self._base())
        # "SP" e "sp" caem no mesmo bucket
        self.assertIn("SP", r["por_uf"])
        self.assertNotIn("sp", r["por_uf"])
        self.assertEqual(r["por_uf"]["SP"]["total"], 3)

    def test_whatsapp_concentrado_em_sp(self):
        r = geo_reach_report(self._base())
        self.assertEqual(r["por_uf"]["SP"]["whatsapp"], 2)
        self.assertEqual(r["por_uf"]["MG"]["whatsapp"], 0)   # lote só e-mail
        self.assertEqual(r["por_uf"]["BA"]["whatsapp"], 0)
        # o achado central: SP detém TODO o alcance de WhatsApp
        self.assertEqual(r["wa_top_uf"], "SP")
        self.assertAlmostEqual(r["wa_top_uf_share"], 100.0)

    def test_email_quase_universal(self):
        r = geo_reach_report(self._base())
        self.assertEqual(r["por_uf"]["SP"]["email"], 3)
        self.assertEqual(r["por_uf"]["MG"]["email"], 2)
        self.assertEqual(r["por_uf"]["BA"]["email"], 0)      # e-mail inválido

    def test_pct_mortos_por_uf(self):
        r = geo_reach_report(self._base())
        self.assertAlmostEqual(r["por_uf"]["BA"]["pct_mortos"], 100.0)
        self.assertAlmostEqual(r["por_uf"]["SP"]["pct_mortos"], 0.0)

    def test_uf_vazio_vira_bucket_proprio(self):
        cmap = {"1": {"uf": "", "fone": "", "email": "x@y.com"}}
        r = geo_reach_report(cmap)
        self.assertIn("(vazio)", r["por_uf"])

    def test_base_vazia_nao_quebra(self):
        r = geo_reach_report({})
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["mortos"], 0)
        self.assertIsNone(r["wa_top_uf"])
        self.assertEqual(r["wa_top_uf_share"], 0.0)


class TestDDDPreventivoGeo(_ClientMapGuard):
    """Mesma trava preventiva do ddd_padrao, agora na lente geográfica: um lote
    futuro de celulares de 9 díg. sem DDD numa praça nova ficaria 0% WhatsApp
    até configurar o DDD padrão."""

    def test_uf_nova_sem_ddd_fica_zero_wa(self):
        cmap = {"1": {"uf": "AM", "fone": "91234-5678", "email": ""}}
        self.assertEqual(geo_reach_report(cmap, default_ddd="")["por_uf"]["AM"]["whatsapp"], 0)

    def test_uf_nova_com_ddd_recupera_wa(self):
        cmap = {"1": {"uf": "AM", "fone": "91234-5678", "email": ""}}
        self.assertEqual(geo_reach_report(cmap, default_ddd="92")["por_uf"]["AM"]["whatsapp"], 1)


if __name__ == "__main__":
    unittest.main()
