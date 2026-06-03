"""
test_email_reach.py — QUALIDADE do e-mail e GANHO de alcance do CANAL-EMAIL
(builder, iteração 9).

Por que existe:
  A iteração 8 mediu PRESENÇA de e-mail (98,6% preenchido) mas — seguindo a própria
  lição "100% preenchido ≠ usável" — NÃO validou o CONTEÚDO. Como o CANAL-EMAIL é a
  maior alavanca de alcance proposta no backlog, esta iteração mede o alcance REAL
  e o GANHO INCREMENTAL do canal, numa varredura SOMENTE-LEITURA da base de produção
  (1.825 clientes, client_map.json de 27/05/2026).

  Achados concretos (produção, 31/05/2026):
    - 1799/1825 = 98,6% têm e-mail preenchido E com formato VÁLIDO (local@dominio.tld).
      Diferente de `nascimento` (62% era o placeholder "-"), o campo e-mail PASSOU na
      validação de conteúdo — é majoritariamente utilizável.
    - WhatsApp alcança apenas 757/1825 = 41,5% (único canal ativo hoje).
    - SEM WhatsApp mas COM e-mail válido = 1050 clientes  ← GANHO INCREMENTAL do
      CANAL-EMAIL: 57,5% da base que HOJE é 100% inalcançável passaria a ser atingível.
    - Alcance combinado (WhatsApp OU e-mail válido) = 1807/1825 = 99,0%
      (vs. 41,5% só-WhatsApp hoje). Só 18 clientes (1,0%) ficam sem nenhum canal.
    - Domínios: gmail 1151, hotmail 376, yahoo.com.br 67, outlook 39… (perfil de
      e-mail pessoal real, entregável). PORÉM ~10 têm domínio com TYPO e dariam
      bounce: gmai.com×4, gmail.com.br×3, hotmal.com, gamail.com, 48gmail.com,
      77gmail.com. Não muda o título (1050), mas é um ganho de qualidade barato:
      validar/sugerir-correção de domínio no import. Vide tarefa CANAL-EMAIL / DADOS-3.

ESCOPO E SEGURANÇA:
  Só funções PURAS — normalize_phone (modules.marketing) e a métrica abaixo sobre
  base SINTÉTICA em memória. NÃO chama load/save/import sobre dados reais. Guard de
  mtime confirma que data/client_map.json de PRODUÇÃO não é tocado.
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.marketing import normalize_phone          # noqa: E402
from modules import client_map as cm                    # noqa: E402


# Regex pragmática de "formato entregável": local@dominio.tld, tld >= 2 letras,
# sem espaços e exatamente um '@'. Não pretende ser RFC 5322 — pretende refletir
# o que um servidor SMTP de campanha aceitaria tentar entregar.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# Domínios com erro de digitação conhecidos que dão bounce (amostra observada na
# base + variações comuns). Tudo minúsculo.
_TYPO_DOMAINS = {
    "gmai.com", "gmial.com", "gmail.con", "gmail.co", "gmail.com.br",
    "gamail.com", "hotmal.com", "hotmial.com", "hotmail.con", "hotmail.co",
    "yahoo.con", "outlok.com", "outlook.con",
}


def is_valid_email(raw):
    """True se `raw` tem formato de e-mail entregável (não checa MX)."""
    em = (raw or "").strip()
    return bool(em and _EMAIL_RE.match(em))


def email_domain(raw):
    """Domínio (minúsculo) de um e-mail válido, ou '' se inválido."""
    if not is_valid_email(raw):
        return ""
    return raw.strip().rsplit("@", 1)[1].lower()


def email_reach_report(cmap, default_ddd=""):
    """Métrica PURA de alcance por e-mail e ganho incremental sobre o WhatsApp.

    Espelha exatamente como as campanhas decidiriam alcançar o cliente:
      - WhatsApp: normalize_phone(fone, ddd) != ""
      - E-mail  : formato válido (is_valid_email)

    Retorna dict com contagens, percentuais e o CRUZAMENTO de canais:
      - email_incremental: SEM WhatsApp mas COM e-mail válido (o ganho do canal)
      - alcance_combinado: WhatsApp OU e-mail válido
      - inalcancavel: nenhum canal
      - typo_dominio: e-mails de formato válido porém domínio com typo (bounce)
    """
    total = len(cmap)

    def _pct(n):
        return (100.0 * n / total) if total else 0.0

    email_filled = email_valid = typo = 0
    wa = 0
    email_incremental = 0   # sem WhatsApp, com e-mail válido
    wa_and_email = 0
    combinado = 0
    inalcancavel = 0
    for v in cmap.values():
        v = v or {}
        raw = (v.get("email") or "").strip()
        if raw:
            email_filled += 1
        valid = is_valid_email(raw)
        if valid:
            email_valid += 1
            if email_domain(raw) in _TYPO_DOMAINS:
                typo += 1
        has_wa = bool(normalize_phone(v.get("fone", ""), default_ddd))
        if has_wa:
            wa += 1
        if has_wa and valid:
            wa_and_email += 1
        if (not has_wa) and valid:
            email_incremental += 1
        if has_wa or valid:
            combinado += 1
        else:
            inalcancavel += 1

    return {
        "total": total,
        "email_filled": email_filled,
        "email_valid": email_valid,
        "typo_dominio": typo,
        "whatsapp": wa,
        "wa_and_email": wa_and_email,
        "email_incremental": email_incremental,
        "alcance_combinado": combinado,
        "inalcancavel": inalcancavel,
        "pct_email_valid": _pct(email_valid),
        "pct_whatsapp": _pct(wa),
        "pct_combinado": _pct(combinado),
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
        for ok in ("a@b.com", "celo_9sul@hotmail.com", "x.y+z@dominio.com.br"):
            self.assertTrue(is_valid_email(ok), ok)

    def test_invalidos(self):
        for bad in ("", "   ", "-", "sem-arroba.com", "a@b", "a@@b.com",
                    "a b@c.com", "a@b.c", None):
            self.assertFalse(is_valid_email(bad), repr(bad))

    def test_dominio_extraido_minusculo(self):
        self.assertEqual(email_domain("X@Gmail.COM"), "gmail.com")
        self.assertEqual(email_domain("invalido"), "")


class TestEmailReachMetric(_ClientMapGuard):
    """A métrica de alcance/ganho usada para auditar a base (dados sintéticos)."""

    def _base(self):
        return {
            # tem WhatsApp (cel) e e-mail válido → redundância multicanal
            "1": {"fone": "(11)91234-5678", "email": "a@gmail.com"},
            # sem WhatsApp, com e-mail válido → GANHO incremental do canal
            "2": {"fone": "", "email": "b@hotmail.com"},
            # sem WhatsApp, e-mail com TYPO de domínio → válido em formato, bounce
            "3": {"fone": "telefone ruim", "email": "c@gmai.com"},
            # sem WhatsApp e sem e-mail válido → inalcançável
            "4": {"fone": "", "email": "-"},
        }

    def test_contagens(self):
        r = email_reach_report(self._base())
        self.assertEqual(r["total"], 4)
        self.assertEqual(r["whatsapp"], 1)             # só o cliente 1
        self.assertEqual(r["email_valid"], 3)          # 1,2,3 (typo ainda é formato válido)
        self.assertEqual(r["typo_dominio"], 1)         # cliente 3
        self.assertEqual(r["wa_and_email"], 1)         # cliente 1
        self.assertEqual(r["email_incremental"], 2)    # 2 e 3 (sem WA, e-mail válido)
        self.assertEqual(r["alcance_combinado"], 3)    # 1,2,3
        self.assertEqual(r["inalcancavel"], 1)         # cliente 4

    def test_ganho_incremental_e_o_coracao_do_achado(self):
        # O e-mail eleva o alcance acima do que o WhatsApp sozinho atinge.
        r = email_reach_report(self._base())
        self.assertGreater(r["alcance_combinado"], r["whatsapp"])
        self.assertEqual(
            r["alcance_combinado"], r["whatsapp"] + r["email_incremental"]
        )

    def test_base_vazia_nao_divide_por_zero(self):
        r = email_reach_report({})
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["pct_combinado"], 0.0)
        self.assertEqual(r["email_incremental"], 0)

    def test_default_ddd_recupera_celular_e_reduz_ganho_de_email(self):
        # Cliente sem DDD mas com e-mail: com ddd_padrao ele passa a ter WhatsApp,
        # então deixa de contar como ganho EXCLUSIVO de e-mail (vira multicanal).
        cmap = {"1": {"fone": "91234-5678", "email": "z@gmail.com"}}
        sem = email_reach_report(cmap, default_ddd="")
        com = email_reach_report(cmap, default_ddd="61")
        self.assertEqual(sem["whatsapp"], 0)
        self.assertEqual(sem["email_incremental"], 1)
        self.assertEqual(com["whatsapp"], 1)
        self.assertEqual(com["email_incremental"], 0)
        self.assertEqual(com["wa_and_email"], 1)


if __name__ == "__main__":
    unittest.main()
