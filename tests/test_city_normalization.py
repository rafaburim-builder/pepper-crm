"""
test_city_normalization.py — NORMALIZACAO DE CIDADE + MORTOS por praca
                              (builder, iteracao 15).

Por que existe:
  As iteracoes 13/14 mostraram que a contactabilidade da base e' um problema
  TERRITORIAL (WhatsApp e' praticamente SP-only; cada praca fora de SP e' um
  lote de importacao sem telefone). O proximo passo natural para gerente/captador
  e' um PAINEL POR CIDADE. Antes de construi-lo, esta iteracao auditou, SOMENTE
  LEITURA, se o campo `cidade` da base de producao (1.825 clientes, 01/06/2026)
  esta' limpo o bastante para agrupar por praca sem que a mesma cidade apareca
  em varias linhas (acento/caixa divergentes dividiriam o dashboard).

  ACHADO CIDADE-NORM (a manchete da noite — e' uma BOA noticia, rara aqui):
    A higiene de `cidade` e' BOA. 389 valores crus distintos colapsam em apenas
    383 cidades canonicas (maiusculas + sem acento + espacos normalizados).
    So' 6 grupos fragmentam em mais de uma variante crua, somando apenas
    7 registros "stray" (minoria a recolher):
        CEILANDIA            : "Ceilandia"(1)            | "Ceilandia"[ac](1)
        BRASILIA             : "Brasilia"[ac](45)        | "Brasilia"(2)
        PORTO FERREIRA       : "Porto Ferreira"(678)     | "Porto ferreira"(1)
        SANTA RITA P. QUATRO : "...do Passa Quatro"(9)   | "...Do Passa Quatro"(1)
        CAMPOS DO JORDAO     : "Campos do Jordao"[ac](4) | "Campos Do Jordao"[ac](1)
        FEIRA DE SANTANA     : "Feira De Santana"(3)     | "Feira de Santana"(1)
    Ou seja: o painel por cidade pode ser construido com seguranca; basta uma
    fina camada de normalizacao de exibicao (ou recolher 7 registros), NAO uma
    migracao em massa. 13 clientes tem `cidade` vazia (bucket "(sem cidade)").

  ACHADO-2 (revalida licao da Iter-11 — o "�" e' artefato de CONSOLE):
    Ao varrer, o console do PowerShell mostra "Bras�lia"/"Jord�o", mas a
    checagem por codepoint deu 0 ocorrencias de U+FFFD em cidade, nome ou email.
    O arquivo e' UTF-8 valido ("Brasilia"/"Jordao" acentuados corretos). A
    fragmentacao acima e' acento-vs-sem-acento e caixa de preposicao (de/do/Do),
    NAO corrupcao. Confirma de novo: validar CONTEUDO (codepoint), nao a tela.

  ACHADO-3 (entrega o backlog GEO-2 da Iter-13 — lista de MORTOS por praca):
    Os 18 MORTOS (sem WhatsApp E sem e-mail valido) por praca, prontos para o
    captador sanear 1-a-1:
        SP: (sem cidade) 3, Sao Paulo 3, Porto Ferreira 1, Guarulhos 1,
            Sertaozinho 1            -> 9
        DF: Brasilia 1, (sem cidade) 1                 -> 2
        SC: (sem cidade) 1, Lages 1                    -> 2
        MG: Juiz de Fora 1, Divinopolis 1              -> 2
        RJ: Rio de Janeiro 1 | RN: Natal 1 | AC: (sem cidade) 1
    18/1825 = 1,0% da base. Note que 5 dos 18 nem cidade tem.

ESCOPO E SEGURANCA:
  Apenas funcoes PURAS — norm_city / city_dashboard_report / mortos_by_praca
  sobre base SINTETICA em memoria. Reusa normalize_phone (modules.marketing).
  NAO chama load/save/import sobre dados reais. Guard de mtime confirma que
  data/client_map.json de PRODUCAO nao e' tocado pela suite.
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import re
import sys
import unicodedata
import unittest
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.marketing import normalize_phone          # noqa: E402
from modules import client_map as cm                    # noqa: E402

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(e):
    """True se o e-mail tem FORMATO valido (mesmo criterio das Iter 9/13)."""
    return bool(_EMAIL_RE.match((e or "").strip()))


def norm_city(s):
    """Chave canonica de cidade: sem acento, MAIUSCULA, espacos colapsados.

    Duas grafias da mesma praca ("Brasilia"/"Brasilia"-acentuada, "Porto
    Ferreira"/"Porto ferreira") colapsam na MESMA chave -> uma linha so' no
    painel por cidade. String vazia/None -> "".
    """
    s = (s or "").strip()
    if not s:
        return ""
    s2 = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", s2).upper().strip()


def city_dashboard_report(cmap):
    """Metrica PURA de fragmentacao de cidade — quanto um painel por cidade
    se dividiria por causa de variantes de acento/caixa.

    Retorna dict:
      {
        "total": int,
        "vazias": int,                  # clientes com cidade em branco
        "variantes_cruas": int,         # grafias distintas (como digitadas)
        "canonicas": int,               # cidades distintas apos normalizar
        "grupos_fragmentados": int,     # canonicas com >1 variante crua
        "stray": int,                   # registros na variante minoritaria
        "fragmentos": { canonica: {"dominante": (txt, n),
                                    "stray": [(txt, n), ...]} },
      }
    """
    total = len(cmap)
    vazias = 0
    groups = defaultdict(lambda: defaultdict(int))
    for v in cmap.values():
        c = ((v or {}).get("cidade") or "").strip()
        if not c:
            vazias += 1
            continue
        groups[norm_city(c)][c] += 1

    variantes_cruas = sum(len(vs) for vs in groups.values())
    fragmentos = {}
    stray = 0
    for k, vs in groups.items():
        if len(vs) > 1:
            ordered = sorted(vs.items(), key=lambda x: (-x[1], x[0]))
            dom, rest = ordered[0], ordered[1:]
            stray += sum(n for _, n in rest)
            fragmentos[k] = {"dominante": dom, "stray": rest}

    return {
        "total": total,
        "vazias": vazias,
        "variantes_cruas": variantes_cruas,
        "canonicas": len(groups),
        "grupos_fragmentados": len(fragmentos),
        "stray": stray,
        "fragmentos": fragmentos,
    }


def mortos_by_praca(cmap, default_ddd=""):
    """Lista os MORTOS (sem WhatsApp normalizavel E sem e-mail valido)
    agrupados por (uf, cidade) — entrega o backlog GEO-2 ao captador.

    Retorna (total_mortos, { (uf, cidade): n }).
    """
    by_praca = defaultdict(int)
    total = 0
    for v in cmap.values():
        v = v or {}
        phone = bool(normalize_phone(v.get("fone", ""), default_ddd))
        email = is_valid_email(v.get("email", ""))
        if not phone and not email:
            uf = (v.get("uf") or "").strip().upper()
            cidade = (v.get("cidade") or "").strip()
            by_praca[(uf, cidade)] += 1
            total += 1
    return total, dict(by_praca)


class _ClientMapGuard(unittest.TestCase):
    """Garante que a base de clientes de producao nunca e' tocada pela suite."""

    @classmethod
    def setUpClass(cls):
        cls._prod = cm._FILE
        cls._mtime = os.path.getmtime(cls._prod) if os.path.exists(cls._prod) else None

    @classmethod
    def tearDownClass(cls):
        if cls._mtime is not None:
            assert os.path.exists(cls._prod), "client_map.json de producao sumiu!"
            assert os.path.getmtime(cls._prod) == cls._mtime, (
                "client_map.json de producao foi modificado pela suite de teste!"
            )


class TestNormCity(_ClientMapGuard):
    def test_acento_colapsa(self):
        self.assertEqual(norm_city("Brasília"), norm_city("Brasilia"))
        self.assertEqual(norm_city("Brasília"), "BRASILIA")

    def test_caixa_colapsa(self):
        self.assertEqual(norm_city("Porto Ferreira"), norm_city("Porto ferreira"))
        self.assertEqual(
            norm_city("Santa Rita do Passa Quatro"),
            norm_city("Santa Rita Do Passa Quatro"),
        )

    def test_espacos_colapsam(self):
        self.assertEqual(norm_city("  São   Paulo  "), "SAO PAULO")

    def test_vazio_e_none(self):
        self.assertEqual(norm_city(""), "")
        self.assertEqual(norm_city(None), "")
        self.assertEqual(norm_city("   "), "")


class TestCityDashboardReport(_ClientMapGuard):
    """Reproduz o padrao real de producao: uma praca grande consistente,
    alguns grupos com 1 variante minoritaria (stray), e cidades vazias."""

    def _base(self):
        return {
            # praca grande, consistente (so' 1 stray de caixa)
            "1": {"cidade": "Porto Ferreira", "uf": "SP"},
            "2": {"cidade": "Porto Ferreira", "uf": "SP"},
            "3": {"cidade": "Porto Ferreira", "uf": "SP"},
            "4": {"cidade": "Porto ferreira", "uf": "SP"},   # stray (caixa)
            # acento divergente
            "5": {"cidade": "Brasília", "uf": "DF"},
            "6": {"cidade": "Brasília", "uf": "DF"},
            "7": {"cidade": "Brasilia", "uf": "DF"},          # stray (sem acento)
            # cidade limpa, sem fragmentacao
            "8": {"cidade": "Campinas", "uf": "SP"},
            # vazias
            "9": {"cidade": "", "uf": "SP"},
            "10": {"cidade": "   ", "uf": "SP"},
        }

    def test_totais_e_vazias(self):
        r = city_dashboard_report(self._base())
        self.assertEqual(r["total"], 10)
        self.assertEqual(r["vazias"], 2)

    def test_canonicas_menor_que_cruas(self):
        r = city_dashboard_report(self._base())
        # cruas: "Porto Ferreira","Porto ferreira","Brasília","Brasilia","Campinas" = 5
        self.assertEqual(r["variantes_cruas"], 5)
        # canonicas: PORTO FERREIRA, BRASILIA, CAMPINAS = 3
        self.assertEqual(r["canonicas"], 3)

    def test_grupos_fragmentados_e_stray(self):
        r = city_dashboard_report(self._base())
        self.assertEqual(r["grupos_fragmentados"], 2)   # PORTO FERREIRA, BRASILIA
        self.assertEqual(r["stray"], 2)                  # 1 + 1

    def test_dominante_e_stray_corretos(self):
        r = city_dashboard_report(self._base())
        pf = r["fragmentos"]["PORTO FERREIRA"]
        self.assertEqual(pf["dominante"], ("Porto Ferreira", 3))
        self.assertEqual(pf["stray"], [("Porto ferreira", 1)])

    def test_cidade_limpa_nao_fragmenta(self):
        r = city_dashboard_report(self._base())
        self.assertNotIn("CAMPINAS", r["fragmentos"])

    def test_base_vazia_nao_quebra(self):
        r = city_dashboard_report({})
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["canonicas"], 0)
        self.assertEqual(r["grupos_fragmentados"], 0)


class TestMortosByPraca(_ClientMapGuard):
    """A lista de mortos por praca (GEO-2) — sem WhatsApp e sem e-mail valido."""

    def _base(self):
        return {
            # vivo por WhatsApp
            "1": {"uf": "SP", "cidade": "São Paulo",
                  "fone": "(11)91234-5678", "email": ""},
            # vivo por e-mail
            "2": {"uf": "SP", "cidade": "São Paulo",
                  "fone": "", "email": "a@x.com"},
            # MORTO (nem fone nem email valido)
            "3": {"uf": "SP", "cidade": "São Paulo",
                  "fone": "", "email": "naoehemail"},
            # MORTO, sem cidade
            "4": {"uf": "DF", "cidade": "", "fone": "", "email": ""},
            # MORTO, outra praca
            "5": {"uf": "MG", "cidade": "Juiz de Fora",
                  "fone": "telefone", "email": ""},
        }

    def test_total_mortos(self):
        total, _ = mortos_by_praca(self._base())
        self.assertEqual(total, 3)

    def test_agrupa_por_praca(self):
        _, by = mortos_by_praca(self._base())
        self.assertEqual(by[("SP", "São Paulo")], 1)
        self.assertEqual(by[("DF", "")], 1)
        self.assertEqual(by[("MG", "Juiz de Fora")], 1)

    def test_vivos_nao_entram(self):
        _, by = mortos_by_praca(self._base())
        # nenhum bucket pode somar os clientes vivos 1 e 2
        self.assertEqual(sum(by.values()), 3)

    def test_base_vazia(self):
        total, by = mortos_by_praca({})
        self.assertEqual(total, 0)
        self.assertEqual(by, {})


if __name__ == "__main__":
    unittest.main()
