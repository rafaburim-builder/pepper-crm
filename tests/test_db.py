"""
test_db.py — Testes da camada de persistência local (modules/db.py).

Por que existe (builder, iteração 5):
  db.py guarda as sugestões de mix salvas e o HISTÓRICO DE CONTATOS do WhatsApp.
  O histórico de contatos é o que impede o vendedor/captador de torrar o mesmo
  cliente duas vezes no mês (was_contacted_this_month) e o que alimenta a régua
  de recontato (days_since_last_contact). Se essa lógica de datas quebrar, o CRM
  passa a sugerir contatos errados — risco comercial direto. Travamos com
  regressão automatizada.

ISOLAMENTO (importante):
  Todos os testes fazem monkeypatch de modules.db._DB_PATH para um arquivo
  SQLite TEMPORÁRIO em setUp e restauram em tearDown. NENHUM teste toca o
  data/pepper.db real. Um guard em setUpClass/tearDownClass confirma que o
  mtime do banco de produção não mudou durante a suíte.
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import sys
import tempfile
import shutil
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db  # noqa: E402


class _DBIsoladoBase(unittest.TestCase):
    """Aponta _DB_PATH para um SQLite temporário antes de cada teste."""

    # ── Guard: o banco de produção não pode ser tocado pela suíte ──────────────
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
        self._prev_path = db._DB_PATH
        self._tmp = tempfile.mkdtemp(prefix="pepper-db-test-")
        db._DB_PATH = os.path.join(self._tmp, "test.db")
        self.database = db.Database()

    def tearDown(self):
        try:
            self.database._conn.close()
        except Exception:
            pass
        db._DB_PATH = self._prev_path
        shutil.rmtree(self._tmp, ignore_errors=True)

    # helper: insere um contato com data/hora controlada (bypass do now())
    def _insert_contact_at(self, codigo, nome, when: datetime, campanha=""):
        self.database._conn.execute(
            "INSERT INTO contact_history (codigo, nome, campanha, contacted_at) "
            "VALUES (?, ?, ?, ?)",
            (str(codigo), nome, campanha, when.strftime("%d/%m/%Y %H:%M")),
        )
        self.database._conn.commit()


class TestInicializacao(_DBIsoladoBase):
    def test_cria_arquivo_de_banco(self):
        self.assertTrue(os.path.exists(db._DB_PATH))

    def test_tabelas_criadas(self):
        nomes = {
            r[0]
            for r in self.database._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("suggestions", nomes)
        self.assertIn("contact_history", nomes)

    def test_init_idempotente(self):
        # criar uma segunda conexão sobre o mesmo arquivo não deve falhar nem
        # apagar dados existentes
        self.database.save_suggestion("X", {"a": 1})
        outra = db.Database()
        self.assertEqual(len(outra.list_suggestions()), 1)
        outra._conn.close()


class TestSugestoes(_DBIsoladoBase):
    def test_save_retorna_rowid_incremental(self):
        id1 = self.database.save_suggestion("Mix A", {"tier1": 10})
        id2 = self.database.save_suggestion("Mix B", {"tier1": 20})
        self.assertEqual(id1, 1)
        self.assertEqual(id2, 2)

    def test_list_ordena_mais_novo_primeiro(self):
        self.database.save_suggestion("Antiga", {})
        self.database.save_suggestion("Nova", {})
        nomes = [s["nome"] for s in self.database.list_suggestions()]
        self.assertEqual(nomes, ["Nova", "Antiga"])

    def test_list_limita_em_20(self):
        for i in range(25):
            self.database.save_suggestion(f"Mix {i}", {})
        self.assertEqual(len(self.database.list_suggestions()), 20)

    def test_list_traz_campos_esperados(self):
        self.database.save_suggestion("Mix", {})
        item = self.database.list_suggestions()[0]
        self.assertEqual(set(item.keys()), {"id", "nome", "created_at"})

    def test_load_roundtrip_preserva_dados(self):
        payload = {"tier1": 10, "tier2": 20, "nome": "Acentuação çãõ"}
        sid = self.database.save_suggestion("Mix", payload)
        self.assertEqual(self.database.load_suggestion(sid), payload)

    def test_load_inexistente_retorna_dict_vazio(self):
        self.assertEqual(self.database.load_suggestion(99999), {})

    def test_delete_remove(self):
        sid = self.database.save_suggestion("Mix", {})
        self.database.delete_suggestion(sid)
        self.assertEqual(self.database.list_suggestions(), [])

    def test_delete_inexistente_nao_explode(self):
        self.database.delete_suggestion(12345)  # não deve lançar


class TestHistoricoContatos(_DBIsoladoBase):
    def test_log_e_list(self):
        self.database.log_contact("C1", "João", "Reativação")
        contatos = self.database.list_contacts()
        self.assertEqual(len(contatos), 1)
        self.assertEqual(contatos[0]["Código"], "C1")
        self.assertEqual(contatos[0]["Cliente"], "João")
        self.assertEqual(contatos[0]["Campanha"], "Reativação")

    def test_list_ordena_mais_recente_primeiro(self):
        self.database.log_contact("C1", "Primeiro")
        self.database.log_contact("C2", "Segundo")
        nomes = [c["Cliente"] for c in self.database.list_contacts()]
        self.assertEqual(nomes, ["Segundo", "Primeiro"])

    def test_list_respeita_limit(self):
        for i in range(10):
            self.database.log_contact(f"C{i}", f"Cliente {i}")
        self.assertEqual(len(self.database.list_contacts(limit=3)), 3)

    def test_codigo_convertido_para_string(self):
        # log_contact aceita código numérico e normaliza para texto
        self.database.log_contact(123, "Numérico")
        self.assertTrue(self.database.was_contacted_this_month("123"))
        self.assertTrue(self.database.was_contacted_this_month(123))


class TestRegrasDeData(_DBIsoladoBase):
    def test_contatado_este_mes_true_apos_log(self):
        self.database.log_contact("C1", "João")
        self.assertTrue(self.database.was_contacted_this_month("C1"))

    def test_contatado_este_mes_false_se_mes_passado(self):
        mes_passado = datetime.now() - timedelta(days=40)
        self._insert_contact_at("C1", "João", mes_passado)
        self.assertFalse(self.database.was_contacted_this_month("C1"))

    def test_contatado_este_mes_false_se_nunca(self):
        self.assertFalse(self.database.was_contacted_this_month("DESCONHECIDO"))

    def test_dias_desde_ultimo_menos_um_se_nunca(self):
        self.assertEqual(self.database.days_since_last_contact("NAOEXISTE"), -1)

    def test_dias_desde_ultimo_zero_se_hoje(self):
        self.database.log_contact("C1", "João")
        self.assertEqual(self.database.days_since_last_contact("C1"), 0)

    def test_dias_desde_ultimo_conta_dias(self):
        dez_dias = datetime.now() - timedelta(days=10)
        self._insert_contact_at("C1", "João", dez_dias)
        self.assertEqual(self.database.days_since_last_contact("C1"), 10)

    def test_dias_usa_contato_mais_recente(self):
        self._insert_contact_at("C1", "João", datetime.now() - timedelta(days=30))
        self._insert_contact_at("C1", "João", datetime.now() - timedelta(days=5))
        self.assertEqual(self.database.days_since_last_contact("C1"), 5)

    def test_dias_data_corrompida_retorna_menos_um(self):
        self.database._conn.execute(
            "INSERT INTO contact_history (codigo, nome, campanha, contacted_at) "
            "VALUES (?, ?, ?, ?)",
            ("C1", "João", "", "data-invalida"),
        )
        self.database._conn.commit()
        self.assertEqual(self.database.days_since_last_contact("C1"), -1)


if __name__ == "__main__":
    unittest.main()
