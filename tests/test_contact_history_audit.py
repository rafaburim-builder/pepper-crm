"""
test_contact_history_audit.py — Auditoria do HISTÓRICO DE CONTATOS e da
obsolescência das SUGESTÕES salvas (builder, iteração 11).

Por que existe:
  db.py guarda duas coisas que sustentam a régua de relacionamento do CRM:
  (1) o contact_history (quem o vendedor/captador já contatou — o que impede
  torrar o mesmo cliente duas vezes no mês via was_contacted_this_month) e
  (2) as suggestions de mix salvas (a "Meta"). A iteração 10 fechou a dedupe da
  BASE de clientes; faltava auditar o que de fato é GRAVADO em uso real e cruzar
  esses registros de volta contra a base (telefone ainda válido? código órfão?).

  ACHADO DE PRODUÇÃO (pepper.db, 31/05/2026 02h — lido por CÓPIA, app trava o
  arquivo):
    contact_history: 1 linha — e é o código ÓRFÃO de teste 'TESTCODE999'
      (não é cliente da base). Ou seja, ZERO contatos reais registrados em
      produção desde a estreia do recurso.
    suggestions: 2 linhas ('Meta 23/05/2026', 7 dias) — dados-semente.

  INTERPRETAÇÃO (o achado que importa): o guard anti-spam existe e ESTÁ ligado
  (app.py ~3912: was_contacted_this_month / days_since_last_contact pintam o
  ⚠️ "Contatado há Xd"), mas chega VAZIO porque registrar o contato é um 2º
  passo MANUAL — o vendedor abre o WhatsApp pelo link (ação externa), e só
  depois teria que voltar, marcar "✅ Contatado" e clicar "💾 Salvar Contatos"
  (app.py ~3959-3966). Esse 2º passo quase nunca acontece. Resultado: a régua
  de recontato e a trava de não-repetir-no-mês ficam INERTES na prática — o
  mesmo cliente pode ser contatado vários dias seguidos sem o aviso aparecer.
  CRMs consolidados (Salesforce, RD Station, Dynamics, Linx) resolvem isso
  registrando o "toque" no MOMENTO do clique de enviar, não num passo separado.
  → vira item de backlog (decisão + alteração no app.py, NÃO mudança noturna):
    LOG-1 (ver RELATORIO_E_TAREFAS).

ESCOPO E SEGURANÇA:
  Funções PURAS sobre dados sintéticos + um teste de integração que escreve num
  SQLite TEMPORÁRIO (monkeypatch de db._DB_PATH, mesmo padrão do test_db.py).
  NENHUM teste toca data/pepper.db real; guard de mtime em setUpClass/
  tearDownClass confirma que o banco de produção não foi modificado.
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import sys
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db                       # noqa: E402
from modules.marketing import normalize_phone  # noqa: E402

_SUG_FMT = "%d/%m/%Y %H:%M"


# ── Funções PURAS de auditoria (sem I/O) ──────────────────────────────────────

def audit_contact_history(rows, client_map, normalizer):
    """rows: iterável de (codigo, nome, campanha, contacted_at).
    Cruza os contatos gravados contra a base de clientes e devolve métricas.
    Pura: não lê arquivo nem banco."""
    codes = [str(r[0]) for r in rows]
    distinct = set(codes)
    orphan_codes = sorted(k for k in distinct if k not in client_map)
    contacted_no_valid_phone = sorted(
        k for k in distinct
        if k in client_map and not normalizer(client_map[k].get("fone", ""))
    )
    # Clientes DISTINTOS contatados que compartilham o mesmo telefone normalizado:
    # cada grupo > 1 representa envios redundantes evitáveis.
    phone_to_codes = {}
    for k in distinct:
        if k in client_map:
            p = normalizer(client_map[k].get("fone", ""))
            if p:
                phone_to_codes.setdefault(p, set()).add(k)
    dup_groups = {p: cs for p, cs in phone_to_codes.items() if len(cs) > 1}
    return {
        "total_rows": len(codes),
        "distinct_codes": len(distinct),
        "orphan_codes": orphan_codes,
        "contacted_no_valid_phone": contacted_no_valid_phone,
        "dup_phone_groups": len(dup_groups),
        "dup_phone_redundant_sends": sum(len(cs) - 1 for cs in dup_groups.values()),
    }


def suggestion_ages(rows, now, fmt=_SUG_FMT):
    """rows: iterável de (id, nome, created_at). Devolve [(id, age_days|None)].
    age None quando created_at não casa com o formato esperado."""
    out = []
    for r in rows:
        sid, ca = r[0], r[2]
        try:
            dt = datetime.strptime(ca, fmt)
            out.append((sid, max(0, (now - dt).days)))
        except Exception:
            out.append((sid, None))
    return out


def count_stale_suggestions(rows, now, max_age_days=30, fmt=_SUG_FMT):
    """Quantas sugestões salvas têm idade > max_age_days (datas inválidas não
    contam como stale)."""
    return sum(
        1 for _, age in suggestion_ages(rows, now, fmt)
        if age is not None and age > max_age_days
    )


# ── Testes das funções puras de contact_history ───────────────────────────────

class TestAuditContactHistory(unittest.TestCase):
    def setUp(self):
        # base sintética: '1' tem cel válido; '2' tem fixo válido; '3' sem fone;
        # '4' compartilha o mesmo telefone do '1' (conta-família).
        self.cm = {
            "1": {"nome": "Ana",   "fone": "(11) 99999-1111"},
            "2": {"nome": "Bruno", "fone": "(11) 3333-2222"},
            "3": {"nome": "Caio",  "fone": ""},
            "4": {"nome": "Duda",  "fone": "(11) 99999-1111"},
        }

    def test_vazio(self):
        a = audit_contact_history([], self.cm, normalize_phone)
        self.assertEqual(a["total_rows"], 0)
        self.assertEqual(a["distinct_codes"], 0)
        self.assertEqual(a["orphan_codes"], [])
        self.assertEqual(a["dup_phone_redundant_sends"], 0)

    def test_orfaos(self):
        rows = [("1", "Ana", "c", "01/05/2026 10:00"),
                ("999", "Fantasma", "c", "01/05/2026 10:00")]
        a = audit_contact_history(rows, self.cm, normalize_phone)
        self.assertEqual(a["orphan_codes"], ["999"])

    def test_codigo_inteiro_vira_string(self):
        # log_contact grava str(codigo); a auditoria aceita int e normaliza.
        rows = [(1, "Ana", "c", "01/05/2026 10:00")]
        a = audit_contact_history(rows, self.cm, normalize_phone)
        self.assertEqual(a["orphan_codes"], [])
        self.assertEqual(a["distinct_codes"], 1)

    def test_distintos_conta_uma_vez(self):
        rows = [("1", "Ana", "c", "01/05/2026 10:00"),
                ("1", "Ana", "c", "10/05/2026 10:00")]
        a = audit_contact_history(rows, self.cm, normalize_phone)
        self.assertEqual(a["total_rows"], 2)
        self.assertEqual(a["distinct_codes"], 1)

    def test_sem_telefone_valido(self):
        rows = [("3", "Caio", "c", "01/05/2026 10:00")]
        a = audit_contact_history(rows, self.cm, normalize_phone)
        self.assertEqual(a["contacted_no_valid_phone"], ["3"])

    def test_fixo_conta_como_valido(self):
        rows = [("2", "Bruno", "c", "01/05/2026 10:00")]
        a = audit_contact_history(rows, self.cm, normalize_phone)
        self.assertEqual(a["contacted_no_valid_phone"], [])

    def test_telefone_duplicado_gera_redundancia(self):
        rows = [("1", "Ana", "c", "01/05/2026 10:00"),
                ("4", "Duda", "c", "01/05/2026 10:00")]
        a = audit_contact_history(rows, self.cm, normalize_phone)
        self.assertEqual(a["dup_phone_groups"], 1)
        self.assertEqual(a["dup_phone_redundant_sends"], 1)

    def test_orfao_nao_entra_em_dup_nem_em_sem_fone(self):
        rows = [("999", "Fantasma", "c", "01/05/2026 10:00")]
        a = audit_contact_history(rows, self.cm, normalize_phone)
        self.assertEqual(a["contacted_no_valid_phone"], [])
        self.assertEqual(a["dup_phone_groups"], 0)


# ── Testes das funções puras de obsolescência de sugestões ─────────────────────

class TestSuggestionStaleness(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 31, 2, 0)

    def test_idade_em_dias(self):
        rows = [(1, "Meta", "24/05/2026 02:00"), (2, "Meta", "31/05/2026 02:00")]
        ages = dict(suggestion_ages(rows, self.now))
        self.assertEqual(ages[1], 7)
        self.assertEqual(ages[2], 0)

    def test_data_invalida_vira_none(self):
        rows = [(1, "Meta", "sem-data")]
        self.assertIsNone(dict(suggestion_ages(rows, self.now))[1])

    def test_idade_nunca_negativa(self):
        rows = [(1, "Meta", "10/06/2026 02:00")]  # futuro
        self.assertEqual(dict(suggestion_ages(rows, self.now))[1], 0)

    def test_contagem_stale(self):
        rows = [(1, "velha", "01/01/2026 02:00"),   # ~150d
                (2, "nova",  "30/05/2026 02:00"),   # 1d
                (3, "ruim",  "xxx")]                 # inválida
        self.assertEqual(count_stale_suggestions(rows, self.now, max_age_days=30), 1)

    def test_stale_limite_exclusivo(self):
        rows = [(1, "borda", "01/05/2026 02:00")]  # exatamente 30d
        self.assertEqual(count_stale_suggestions(rows, self.now, max_age_days=30), 0)


# ── Integração: escreve num SQLite TEMPORÁRIO e roda a auditoria de volta ───────

class TestAuditSobreBancoTemporario(unittest.TestCase):
    """Usa db.Database real, mas com _DB_PATH apontado para arquivo temporário.
    Confirma que o que log_contact grava é o que a auditoria lê de volta."""

    @classmethod
    def setUpClass(cls):
        cls._prod_db = db._DB_PATH
        cls._prod_mtime = (
            os.path.getmtime(cls._prod_db) if os.path.exists(cls._prod_db) else None
        )

    @classmethod
    def tearDownClass(cls):
        if cls._prod_mtime is not None:
            assert os.path.exists(cls._prod_db), "banco de produção sumiu!"
            assert os.path.getmtime(cls._prod_db) == cls._prod_mtime, (
                "banco de produção foi modificado pela suíte de teste!"
            )

    def setUp(self):
        self._prev = db._DB_PATH
        self._tmp = tempfile.mkdtemp(prefix="pepper-chaudit-")
        db._DB_PATH = os.path.join(self._tmp, "t.db")
        self.d = db.Database()
        self.cm = {
            "1": {"nome": "Ana",  "fone": "(11) 99999-1111"},
            "4": {"nome": "Duda", "fone": "(11) 99999-1111"},
        }

    def tearDown(self):
        try:
            self.d._conn.close()
        except Exception:
            pass
        db._DB_PATH = self._prev
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_roundtrip_log_contact_alimenta_auditoria(self):
        self.d.log_contact("1", "Ana", "Reativação")
        self.d.log_contact("4", "Duda", "Reativação")
        self.d.log_contact("999", "Fantasma", "Reativação")  # órfão
        rows = self.d._conn.execute(
            "SELECT codigo, nome, campanha, contacted_at FROM contact_history"
        ).fetchall()
        a = audit_contact_history(rows, self.cm, normalize_phone)
        self.assertEqual(a["total_rows"], 3)
        self.assertEqual(a["distinct_codes"], 3)
        self.assertEqual(a["orphan_codes"], ["999"])
        self.assertEqual(a["dup_phone_redundant_sends"], 1)  # 1 e 4 mesmo número

    def test_banco_recem_criado_audita_zero(self):
        rows = self.d._conn.execute(
            "SELECT codigo, nome, campanha, contacted_at FROM contact_history"
        ).fetchall()
        a = audit_contact_history(rows, self.cm, normalize_phone)
        self.assertEqual(a["total_rows"], 0)
        self.assertEqual(a["distinct_codes"], 0)

    def test_suggestion_staleness_sobre_save_real(self):
        sid = self.d.save_suggestion("Meta hoje", {"x": 1})
        rows = self.d._conn.execute(
            "SELECT id, nome, created_at FROM suggestions"
        ).fetchall()
        ages = dict(suggestion_ages(rows, datetime.now()))
        self.assertEqual(ages[sid], 0)  # criada agora → 0 dias


if __name__ == "__main__":
    unittest.main()
