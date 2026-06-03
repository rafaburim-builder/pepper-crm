"""
test_tenure_cohort.py — TEMPO DE BASE (cliente_desde) × alcance por canal, e
detecção de CARIMBO DE IMPORTAÇÃO em massa (builder, iteração 12).

Por que existe:
  O alvo planejado na Iter 11 era cruzar JANELA de reativação (J1..J5 dias-sem-
  comprar) × alcance por canal. Confirmado por inspeção: client_map.json NÃO tem
  data de última compra (campos: nome, fone, email, cidade, uf, aniversario,
  nascimento, cliente_desde) — a janela de recência depende do df_retorno VIVO
  do Microvix (SSL bloqueado à noite). Pivotamos para o análogo 100% offline e
  decisão-relevante: o campo `cliente_desde` (data de cadastro), que está 100%
  preenchido em DD/MM/AAAA, mede TEMPO DE BASE (proxy de coorte de aquisição).
  Pergunta de negócio: clientes recém-captados (lead novo de captador/vendedor)
  estão entrando COM um canal de contato usável? Se não, a contatabilidade vaza
  no ATO da captação — achado de PROCESSO de captador, não só limpeza de dados.

  Achados concretos (produção, 31/05/2026, client_map de 27/05 21:38, 1.825 cli):
    ALCANCE POR COORTE DE TEMPO DE BASE (WA = telefone normalizável;
    EMAIL = formato válido E não-placeholder; COMBIN = WA ou EMAIL):
      COORTE              N     WA%   EMAIL%  COMBIN%  MORTOS
      0-90d (novissimo) 1142    7.2%   94.0%   94.0%     68
      90d-1ano           355   99.4%   98.3%   99.7%      1
      1-3 anos           222   99.5%   99.5%  100.0%      0
      3-7 anos            37  100.0%  100.0%  100.0%      0
      7+ anos             69   92.8%   89.9%   95.7%      3

    >>> ACHADO PRINCIPAL — CARIMBO DE IMPORTAÇÃO sobrescreveu o tempo de base:
    1.060 clientes (58% de TODA a base) têm cliente_desde = 15/05/2026, UMA
    única data. Não é aquisição real — é a data em que um lote foi importado,
    apagando a data verdadeira de cadastro desses clientes. Logo:
      (a) qualquer análise de tempo de base / mensagem "cliente há X anos" está
          ERRADA para a maioria da base;
      (b) explica o mistério da Iter 8 (WhatsApp só 41,5% da base): esse lote de
          15/05 tem ~7% de telefone e ~94% de e-mail (origem rica em e-mail e
          pobre em telefone — provável export de NF-e / e-commerce), puxando o
          alcance de WhatsApp da base toda para baixo; os clientes "nativos" de
          PDV têm ~99% de WhatsApp;
      (c) reforça o CANAL-EMAIL por novo ângulo: o segmento MAIOR e mais novo é
          alcançável SÓ por e-mail (7% WA vs 94% e-mail). Sem canal de e-mail,
          58% da base — a fatia mais fresca — fica inalcançável pelo único canal
          de saída ativo hoje.

  Estes testes guardam o CONTRATO das funções puras (cohorte, alcance, detecção
  do carimbo) sobre base SINTÉTICA, para que uma futura correção do import
  (preservar cliente_desde real) ou do parser seja deliberada, e registram o
  achado em forma versionada. Tarefas para o humano: ver DADOS-7 no relatório.

ESCOPO E SEGURANÇA:
  Só funções PURAS sobre base SINTÉTICA em memória + normalize_phone
  (modules.marketing). NÃO chama load/save/import sobre dados reais. Guard de
  mtime confirma que data/client_map.json de PRODUÇÃO não é tocado (27/05 21:38).
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import datetime
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.marketing import normalize_phone          # noqa: E402

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLIENT_MAP = os.path.join(_BASE, "data", "client_map.json")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_PLACEHOLDER_LOCAL = re.compile(
    r"^(naotem|naotenho|notem|nao|naosei|naoinformado|naopossui|sememail|sem|"
    r"n|na|x+|teste|test|abc|aaa|email|nenhum|consumidor|cliente)$",
    re.I,
)


# ---------------------------------------------------------------- helpers puros
def parse_cliente_desde(raw):
    """date a partir de 'DD/MM/AAAA', ou None se vazio/'-'/inválido."""
    s = (raw or "").strip()
    if not s or s == "-":
        return None
    try:
        return datetime.datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        return None


def tenure_days(raw, today):
    """Dias de base; None se sem data válida; negativo se data futura."""
    d = parse_cliente_desde(raw)
    if d is None:
        return None
    return (today - d).days


def tenure_cohort(raw, today):
    """Rótulo de coorte por tempo de base."""
    days = tenure_days(raw, today)
    if days is None:
        return "SEM DATA"
    if days <= 90:
        return "0-90d"
    if days <= 365:
        return "90d-1ano"
    if days <= 3 * 365:
        return "1-3 anos"
    if days <= 7 * 365:
        return "3-7 anos"
    return "7+ anos"


def _valid_email(raw):
    em = (raw or "").strip()
    return bool(em and _EMAIL_RE.match(em))


def _usable_email(raw):
    """Formato válido E local-part não é marcador de 'não tem'."""
    if not _valid_email(raw):
        return False
    local = raw.strip().lower().rsplit("@", 1)[0]
    return not _PLACEHOLDER_LOCAL.match(local)


def cohort_reach_report(cmap, today, default_ddd=""):
    """{coorte: {n, wa, email, combinado, mortos}} — alcance por coorte.
    wa=telefone normalizável; email=usável; mortos=sem nenhum canal."""
    rep = {}
    for v in cmap.values():
        v = v or {}
        c = tenure_cohort(v.get("cliente_desde", ""), today)
        a = rep.setdefault(c, {"n": 0, "wa": 0, "email": 0,
                               "combinado": 0, "mortos": 0})
        a["n"] += 1
        wa = bool(normalize_phone(v.get("fone", ""), default_ddd))
        em = _usable_email(v.get("email", ""))
        if wa:
            a["wa"] += 1
        if em:
            a["email"] += 1
        if wa or em:
            a["combinado"] += 1
        if not wa and not em:
            a["mortos"] += 1
    return rep


def detect_bulk_import_stamp(cmap, threshold=0.30):
    """Detecta carimbo de importação: uma única data de cliente_desde
    compartilhada por >= threshold da base. Retorna (data_iso, n, fracao) da
    data mais frequente se ela cruzar o limiar, senão None. Aquisição real é
    pulverizada no tempo; um pico numa só data denuncia um lote importado."""
    counts = {}
    total = 0
    for v in cmap.values():
        d = parse_cliente_desde((v or {}).get("cliente_desde", ""))
        if d is None:
            continue
        total += 1
        counts[d] = counts.get(d, 0) + 1
    if total == 0:
        return None
    day, n = max(counts.items(), key=lambda kv: kv[1])
    frac = n / total
    return (day.isoformat(), n, frac) if frac >= threshold else None


# ----------------------------------------------------------------------- testes
class TestParseClienteDesde(unittest.TestCase):
    def test_valida(self):
        self.assertEqual(parse_cliente_desde("15/05/2026"),
                         datetime.date(2026, 5, 15))

    def test_strip(self):
        self.assertEqual(parse_cliente_desde("  22/07/2007 "),
                         datetime.date(2007, 7, 22))

    def test_vazio_e_traco(self):
        self.assertIsNone(parse_cliente_desde(""))
        self.assertIsNone(parse_cliente_desde("-"))
        self.assertIsNone(parse_cliente_desde("   "))
        self.assertIsNone(parse_cliente_desde(None))

    def test_formato_invalido(self):
        self.assertIsNone(parse_cliente_desde("2026-05-15"))   # ISO != DD/MM/AAAA
        self.assertIsNone(parse_cliente_desde("32/01/2026"))
        self.assertIsNone(parse_cliente_desde("15/13/2026"))
        self.assertIsNone(parse_cliente_desde("abc"))


class TestTenure(unittest.TestCase):
    TODAY = datetime.date(2026, 5, 31)

    def test_tenure_days(self):
        self.assertEqual(tenure_days("31/05/2026", self.TODAY), 0)
        self.assertEqual(tenure_days("01/05/2026", self.TODAY), 30)
        self.assertIsNone(tenure_days("-", self.TODAY))

    def test_data_futura_negativa(self):
        self.assertEqual(tenure_days("01/06/2026", self.TODAY), -1)

    def test_cohort_fronteiras(self):
        self.assertEqual(tenure_cohort("31/05/2026", self.TODAY), "0-90d")
        self.assertEqual(tenure_cohort("02/03/2026", self.TODAY), "0-90d")   # 90d
        self.assertEqual(tenure_cohort("01/03/2026", self.TODAY), "90d-1ano")  # 91d
        self.assertEqual(tenure_cohort("01/07/2025", self.TODAY), "90d-1ano")  # ~334d
        self.assertEqual(tenure_cohort("01/01/2025", self.TODAY), "1-3 anos")  # ~515d
        self.assertEqual(tenure_cohort("01/01/2024", self.TODAY), "1-3 anos")
        self.assertEqual(tenure_cohort("01/01/2021", self.TODAY), "3-7 anos")
        self.assertEqual(tenure_cohort("22/07/2007", self.TODAY), "7+ anos")

    def test_cohort_sem_data(self):
        self.assertEqual(tenure_cohort("-", self.TODAY), "SEM DATA")
        self.assertEqual(tenure_cohort("", self.TODAY), "SEM DATA")


class TestCohortReach(unittest.TestCase):
    TODAY = datetime.date(2026, 5, 31)

    def _cmap(self):
        return {
            # 2 novos: 1 só com e-mail usável, 1 só com WhatsApp
            "1": {"cliente_desde": "15/05/2026", "fone": "",
                  "email": "ana@gmail.com"},
            "2": {"cliente_desde": "15/05/2026", "fone": "(11) 98888-7777",
                  "email": ""},
            # novo MORTO: sem telefone e e-mail placeholder
            "3": {"cliente_desde": "15/05/2026", "fone": "",
                  "email": "naotem@gmail.com"},
            # antigo com ambos os canais
            "4": {"cliente_desde": "22/07/2007", "fone": "11977776666",
                  "email": "jose@uol.com.br"},
            # sem data
            "5": {"cliente_desde": "-", "fone": "11955554444",
                  "email": ""},
        }

    def test_contagens(self):
        rep = cohort_reach_report(self._cmap(), self.TODAY)
        self.assertEqual(rep["0-90d"]["n"], 3)
        self.assertEqual(rep["0-90d"]["wa"], 1)        # só o cod 2
        self.assertEqual(rep["0-90d"]["email"], 1)     # só o cod 1 (3 é placeholder)
        self.assertEqual(rep["0-90d"]["combinado"], 2) # cods 1 e 2
        self.assertEqual(rep["0-90d"]["mortos"], 1)    # cod 3
        self.assertEqual(rep["7+ anos"]["n"], 1)
        self.assertEqual(rep["7+ anos"]["combinado"], 1)
        self.assertEqual(rep["SEM DATA"]["n"], 1)
        self.assertEqual(rep["SEM DATA"]["wa"], 1)

    def test_placeholder_nao_conta_como_email(self):
        rep = cohort_reach_report(
            {"x": {"cliente_desde": "15/05/2026", "fone": "",
                   "email": "naotem@gmail.com"}}, self.TODAY)
        self.assertEqual(rep["0-90d"]["email"], 0)
        self.assertEqual(rep["0-90d"]["mortos"], 1)


class TestBulkImportStamp(unittest.TestCase):
    def test_detecta_pico(self):
        cmap = {str(i): {"cliente_desde": "15/05/2026"} for i in range(60)}
        cmap.update({"a": {"cliente_desde": "22/07/2007"},
                     "b": {"cliente_desde": "02/05/2016"}})
        res = detect_bulk_import_stamp(cmap, threshold=0.30)
        self.assertIsNotNone(res)
        iso, n, frac = res
        self.assertEqual(iso, "2026-05-15")
        self.assertEqual(n, 60)
        self.assertGreater(frac, 0.9)

    def test_aquisicao_pulverizada_nao_dispara(self):
        # 40 datas distintas, nenhuma cruza o limiar
        cmap = {str(i): {"cliente_desde": f"{(i % 28) + 1:02d}/0{(i % 9) + 1}/2025"}
                for i in range(40)}
        self.assertIsNone(detect_bulk_import_stamp(cmap, threshold=0.30))

    def test_base_vazia(self):
        self.assertIsNone(detect_bulk_import_stamp({}))
        self.assertIsNone(detect_bulk_import_stamp(
            {"x": {"cliente_desde": "-"}}))


class TestProdMtimeGuard(unittest.TestCase):
    """Confirma que a auditoria NÃO tocou o client_map de produção."""

    @classmethod
    def setUpClass(cls):
        cls._mtime = (os.path.getmtime(_CLIENT_MAP)
                      if os.path.exists(_CLIENT_MAP) else None)

    def test_client_map_intacto(self):
        if self._mtime is None:
            self.skipTest("client_map.json de produção ausente neste ambiente")
        self.assertEqual(os.path.getmtime(_CLIENT_MAP), self._mtime,
                         "client_map.json de PRODUÇÃO foi modificado — proibido")


if __name__ == "__main__":
    unittest.main(verbosity=2)
