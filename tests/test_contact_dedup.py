"""
test_contact_dedup.py — DUPLICATAS de contato, e-mails PLACEHOLDER e MOJIBAKE
de nome (builder, iteração 10).

Por que existe:
  A iteração 9 fechou o caso do CANAL-EMAIL com o título "1050 clientes de ganho
  incremental, alcance combinado 99,0%". Esse número validou FORMATO de e-mail,
  mas — repetindo a própria lição "formato válido ≠ entregável" um nível acima —
  NÃO removeu e-mails PLACEHOLDER ("não tem") nem e-mails COMPARTILHADOS por
  dezenas de clientes (e-mail da loja / do vendedor usado como fallback). Quando
  34 clientes têm o MESMO e-mail, ele não alcança 34 caixas — alcança uma só.

  Esta iteração faz a varredura SOMENTE-LEITURA da base de produção (1.825
  clientes, client_map.json de 27/05/2026) medindo: (a) duplicatas de telefone
  e e-mail (contas-família / números da loja → envios redundantes evitáveis);
  (b) e-mails placeholder/compartilhados que inflam o alcance; (c) nomes com
  mojibake que quebrariam a personalização da mensagem.

  Achados concretos (produção, 31/05/2026):
    DUPLICATAS DE TELEFONE: 23 grupos, 63 clientes, 40 ENVIOS REDUNDANTES de
      WhatsApp evitáveis. Maior grupo: 11 clientes no mesmo número (provável
      número da loja/placeholder), depois 5, 4, 3, 3...
    DUPLICATAS DE E-MAIL: 41 grupos, 150 clientes, 109 envios redundantes.
    E-MAIL PLACEHOLDER / COMPARTILHADO: 107 clientes têm e-mail de FORMATO
      válido que NÃO os alcança individualmente —
        unavailable@mail.com ×34, naotem@gmail.com ×22, n@gmail.com ×6,
        nao@gmail.com ×3, naosei@gmail.com ×4 (marcadores de "não tem");
        oticachillibeanspf@gmail.com ×7 (e-mail da PRÓPRIA loja);
        santosfrancielle159 ×4, alinegfalves ×3, deka517 ×3 (vendedor/fallback).
    CORREÇÃO DO TÍTULO DA ITER 9: ganho incremental real do CANAL-EMAIL
      1050 → 962 (88 superestimados); alcance combinado 99,0% → 94,2%.
      O caso do canal segue forte (962 clientes hoje inalcançáveis), mas o
      número honesto é 962, não 1050.
    MOJIBAKE: 0 nomes com U+FFFD ('�') ou bigramas de mojibake (Ã©, Ã£, Ã§...).
      A hipótese "Gusm�o" da Iter 9 NÃO se materializou — o import com
      utf-8-sig + fallbacks preserva os acentos. Não voltar a perseguir isto.

ESCOPO E SEGURANÇA:
  Só funções PURAS sobre base SINTÉTICA em memória + normalize_phone
  (modules.marketing). NÃO chama load/save/import sobre dados reais. Guard de
  mtime confirma que data/client_map.json de PRODUÇÃO não é tocado.
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.marketing import normalize_phone          # noqa: E402

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLIENT_MAP = os.path.join(_BASE, "data", "client_map.json")

# Mesmo formato "entregável" usado em test_email_reach.py.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# Local-parts que são marcadores de "cliente não informou e-mail" — passam no
# regex de formato mas não alcançam ninguém. Tudo minúsculo, match exato.
_PLACEHOLDER_LOCAL = re.compile(
    r"^(naotem|naotenho|notem|nao|naosei|naoinformado|naopossui|sememail|sem|"
    r"n|na|x+|teste|test|abc|aaa|email|nenhum|consumidor|cliente)$",
    re.I,
)

_REPLACEMENT = "�"   # '�' — falha definitiva de decodificação.
# Bigramas típicos de UTF-8 lido como Latin-1/CP1252. Um nome em UTF-8 correto
# tem "é", nunca "Ã©"; logo estas sequências são marcadores confiáveis.
_MOJIBAKE_SEQS = ("Ã©", "Ã£", "Ã§", "Ã³", "Ãª", "Ã­", "Ã¡", "Ãº", "Ã ",
                  "Ã‡", "Ã•", "Ãƒ", "Ã‰", "â€")


# ---------------------------------------------------------------- helpers puros
def is_valid_email(raw):
    em = (raw or "").strip()
    return bool(em and _EMAIL_RE.match(em))


def email_local(raw):
    """Local-part minúsculo de um e-mail válido, ou '' se inválido."""
    if not is_valid_email(raw):
        return ""
    return raw.strip().lower().rsplit("@", 1)[0]


def is_placeholder_email(raw):
    """True se o e-mail tem formato válido mas o local-part é um marcador
    de 'não tem e-mail' (não entregável ao cliente real)."""
    local = email_local(raw)
    return bool(local and _PLACEHOLDER_LOCAL.match(local))


def has_replacement_char(name):
    return _REPLACEMENT in (name or "")


def has_mojibake(name):
    s = name or ""
    if _REPLACEMENT in s:
        return True
    return any(seq in s for seq in _MOJIBAKE_SEQS)


def phone_dup_groups(cmap, default_ddd=""):
    """{telefone_normalizado: [cods]} apenas para grupos com >1 cliente."""
    groups = {}
    for cod, v in cmap.items():
        v = v or {}
        ph = normalize_phone(v.get("fone", ""), default_ddd)
        if ph:
            groups.setdefault(ph, []).append(cod)
    return {k: v for k, v in groups.items() if len(v) > 1}


def email_dup_groups(cmap):
    """{email_minusculo_valido: [cods]} apenas para grupos com >1 cliente."""
    groups = {}
    for cod, v in cmap.items():
        v = v or {}
        em = (v.get("email") or "").strip().lower()
        if em and is_valid_email(em):
            groups.setdefault(em, []).append(cod)
    return {k: v for k, v in groups.items() if len(v) > 1}


def dedup_report(cmap, default_ddd="", shared_threshold=3):
    """Métrica PURA de duplicatas + e-mail junk + mojibake.

    'junk email' = local-part placeholder OU e-mail compartilhado por
    >= shared_threshold clientes (loja/vendedor/fallback) → não alcança o
    cliente individual. 'envios_redundantes' = mensagens repetidas evitáveis
    (em cada grupo de tamanho N, N-1 são redundantes)."""
    total = len(cmap)
    pg = phone_dup_groups(cmap, default_ddd)
    eg = email_dup_groups(cmap)
    phone_dup_clients = sum(len(v) for v in pg.values())
    email_dup_clients = sum(len(v) for v in eg.values())

    shared = {k: v for k, v in eg.items() if len(v) >= shared_threshold}
    junk_cods = set()
    for cod, v in cmap.items():
        v = v or {}
        em = (v.get("email") or "").strip().lower()
        if not is_valid_email(em):
            continue
        if is_placeholder_email(em) or em in shared:
            junk_cods.add(cod)

    return {
        "total":                  total,
        "phone_dup_groups":       len(pg),
        "phone_dup_clients":      phone_dup_clients,
        "phone_redundant_sends":  phone_dup_clients - len(pg),
        "email_dup_groups":       len(eg),
        "email_dup_clients":      email_dup_clients,
        "email_redundant_sends":  email_dup_clients - len(eg),
        "email_shared_groups":    len(shared),
        "email_junk_clients":     len(junk_cods),
        "mojibake_names":         sum(1 for v in cmap.values()
                                      if has_mojibake((v or {}).get("nome", ""))),
        "replacement_char_names": sum(1 for v in cmap.values()
                                      if has_replacement_char((v or {}).get("nome", ""))),
    }


# ---------------------------------------------------------------------- testes
class TestEmailClassifiers(unittest.TestCase):
    def test_valid_email_basic(self):
        self.assertTrue(is_valid_email("ana@gmail.com"))
        self.assertFalse(is_valid_email(""))
        self.assertFalse(is_valid_email("ana@gmail"))
        self.assertFalse(is_valid_email("a b@x.com"))

    def test_email_local(self):
        self.assertEqual(email_local("Ana.Silva@Gmail.COM"), "ana.silva")
        self.assertEqual(email_local("invalido"), "")

    def test_placeholder_markers(self):
        for e in ("naotem@gmail.com", "n@gmail.com", "nao@gmail.com",
                  "naosei@gmail.com", "teste@x.com", "xxx@x.com"):
            self.assertTrue(is_placeholder_email(e), e)

    def test_real_email_not_placeholder(self):
        for e in ("joao.pereira@gmail.com", "francielle159@gmail.com",
                  "maria@hotmail.com"):
            self.assertFalse(is_placeholder_email(e), e)

    def test_placeholder_requires_valid_format(self):
        # "nao" sem domínio não é e-mail → não conta como placeholder de e-mail.
        self.assertFalse(is_placeholder_email("nao"))


class TestMojibake(unittest.TestCase):
    def test_replacement_char(self):
        self.assertTrue(has_replacement_char("Gusm�o"))
        self.assertFalse(has_replacement_char("Gusmão"))

    def test_mojibake_bigrams(self):
        self.assertTrue(has_mojibake("JoÃ£o"))     # "João" mal decodificado
        self.assertTrue(has_mojibake("Concei�ão"))
        self.assertTrue(has_mojibake("AndrÃ©"))    # "André"

    def test_clean_accents_are_not_mojibake(self):
        for n in ("João", "André", "Conceição", "Müller", "José"):
            self.assertFalse(has_mojibake(n), n)


class TestDedupReport(unittest.TestCase):
    def _base(self):
        # 6 clientes: 3 no mesmo telefone (1 grupo, 2 redundantes),
        # 2 placeholders de e-mail + 1 e-mail real único.
        return {
            "1": {"nome": "Ana",  "fone": "(19) 99999-0000", "email": "ana@gmail.com"},
            "2": {"nome": "Bia",  "fone": "19999990000",     "email": "naotem@gmail.com"},
            "3": {"nome": "Cris", "fone": "+55 19 99999-0000", "email": "n@gmail.com"},
            "4": {"nome": "Davi", "fone": "11888887777",     "email": "davi@hotmail.com"},
            "5": {"nome": "Edu",  "fone": "",                "email": "loja@gmail.com"},
            "6": {"nome": "Fia",  "fone": "",                "email": "loja@gmail.com"},
        }

    def test_phone_groups_and_redundant_sends(self):
        r = dedup_report(self._base())
        self.assertEqual(r["phone_dup_groups"], 1)        # os 3 no mesmo número
        self.assertEqual(r["phone_dup_clients"], 3)
        self.assertEqual(r["phone_redundant_sends"], 2)   # 3-1

    def test_email_groups(self):
        r = dedup_report(self._base())
        # único e-mail repetido é loja@gmail.com (×2)
        self.assertEqual(r["email_dup_groups"], 1)
        self.assertEqual(r["email_dup_clients"], 2)
        self.assertEqual(r["email_redundant_sends"], 1)

    def test_junk_counts_placeholders_and_shared(self):
        # threshold 2 → loja@gmail.com (×2) também conta como compartilhado
        r = dedup_report(self._base(), shared_threshold=2)
        # placeholders: naotem, n  (2) + compartilhado: loja×2  (2) = 4
        self.assertEqual(r["email_junk_clients"], 4)

    def test_mojibake_zero_on_clean_base(self):
        r = dedup_report(self._base())
        self.assertEqual(r["mojibake_names"], 0)
        self.assertEqual(r["replacement_char_names"], 0)

    def test_empty_map(self):
        r = dedup_report({})
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["phone_dup_groups"], 0)
        self.assertEqual(r["email_junk_clients"], 0)

    def test_none_entries_safe(self):
        r = dedup_report({"1": None, "2": {"nome": "Ana", "fone": "", "email": ""}})
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["phone_dup_groups"], 0)


class TestProdBaseUntouched(unittest.TestCase):
    """Guard: a suíte NÃO pode tocar a base de produção."""
    @classmethod
    def setUpClass(cls):
        cls._mtime = os.path.getmtime(_CLIENT_MAP) if os.path.exists(_CLIENT_MAP) else None

    def test_prod_client_map_not_modified(self):
        if self._mtime is None:
            self.skipTest("client_map.json de produção ausente")
        self.assertEqual(os.path.getmtime(_CLIENT_MAP), self._mtime,
                         "data/client_map.json de PRODUÇÃO foi modificado pela suíte!")


if __name__ == "__main__":
    unittest.main(verbosity=2)
