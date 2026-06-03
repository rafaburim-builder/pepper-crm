"""
test_auth.py — Autenticação e hierarquia de perfis (builder, iteração 19).

Por que existe:
  modules/auth.py foi criado pelo usuário em 01/06/2026 (login + perfis
  vendedor/gerente/captador/supervisor/admin/dev — o item P1.2 do backlog).
  É código de SEGURANÇA (hash de senha, controle de acesso por nível) e estava
  SEM cobertura de teste. Esta suíte trava o contrato de autenticação e
  permissões para que mudanças futuras sejam deliberadas.

ESCOPO E SEGURANÇA:
  100% ISOLADO — cada teste aponta auth._PATH para um arquivo temporário; o
  data/users.json de PRODUÇÃO nunca é lido nem escrito (guard de mtime confirma).
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import sys
import json
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import auth  # noqa: E402


class _AuthIsolated(unittest.TestCase):
    """Aponta auth._PATH para tempfile; garante que o users.json de prod não muda."""

    @classmethod
    def setUpClass(cls):
        cls._prod_path = auth._PATH
        cls._prod_mtime = (
            os.path.getmtime(cls._prod_path) if os.path.exists(cls._prod_path) else None
        )

    @classmethod
    def tearDownClass(cls):
        # O users.json de produção não pode ter sido tocado pela suíte.
        if cls._prod_mtime is not None:
            assert os.path.exists(cls._prod_path), "users.json de produção sumiu!"
            assert os.path.getmtime(cls._prod_path) == cls._prod_mtime, (
                "users.json de produção foi modificado pela suíte de teste!"
            )

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w", encoding="utf-8"
        )
        self._tmp.close()
        os.unlink(self._tmp.name)  # começa inexistente
        self._orig = auth._PATH
        auth._PATH = self._tmp.name

    def tearDown(self):
        auth._PATH = self._orig
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)


class TestHashESenhaPadrao(_AuthIsolated):
    def test_hash_e_sha256_deterministico(self):
        self.assertEqual(auth._hash("abc"), auth._hash("abc"))
        self.assertNotEqual(auth._hash("abc"), auth._hash("abd"))
        self.assertEqual(len(auth._hash("x")), 64)  # sha256 hex

    def test_hash_nao_e_texto_plano(self):
        self.assertNotIn("pepper2026", auth._hash("pepper2026"))

    def test_senha_padrao_usa_ano_atual(self):
        self.assertEqual(auth.senha_padrao(), f"pepper{date.today().year}")


class TestEnsureDefaultAdmin(_AuthIsolated):
    def test_cria_admin_quando_vazio(self):
        self.assertTrue(auth.ensure_default_admin())
        users = auth.list_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["login"], "admin")
        self.assertEqual(users[0]["perfil"], "gerente")
        self.assertTrue(users[0]["primeiro_acesso"])

    def test_nao_recria_se_ja_existe(self):
        auth.ensure_default_admin()
        self.assertFalse(auth.ensure_default_admin())
        self.assertEqual(len(auth.list_users()), 1)

    def test_admin_padrao_autentica_com_senha_do_ano(self):
        auth.ensure_default_admin()
        u = auth.authenticate("admin", auth.senha_padrao())
        self.assertIsNotNone(u)
        self.assertEqual(u["login"], "admin")


class TestAuthenticate(_AuthIsolated):
    def setUp(self):
        super().setUp()
        auth.create_user("joao", "João", "vendedor", senha="segredo123")

    def test_senha_correta_autentica(self):
        self.assertIsNotNone(auth.authenticate("joao", "segredo123"))

    def test_senha_errada_falha(self):
        self.assertIsNone(auth.authenticate("joao", "errada"))

    def test_login_inexistente_falha(self):
        self.assertIsNone(auth.authenticate("ninguem", "segredo123"))

    def test_login_com_espacos_e_normalizado(self):
        self.assertIsNotNone(auth.authenticate("  joao  ", "segredo123"))

    def test_usuario_inativo_nao_autentica(self):
        auth.toggle_user("joao", False)
        self.assertIsNone(auth.authenticate("joao", "segredo123"))
        auth.toggle_user("joao", True)
        self.assertIsNotNone(auth.authenticate("joao", "segredo123"))


class TestCreateUser(_AuthIsolated):
    def test_cria_com_senha_padrao_e_primeiro_acesso(self):
        ok, msg = auth.create_user("maria", "Maria", "gerente")
        self.assertTrue(ok)
        self.assertEqual(msg, "")
        u = auth.authenticate("maria", auth.senha_padrao())
        self.assertIsNotNone(u)
        self.assertTrue(u["primeiro_acesso"])

    def test_perfil_invalido_rejeitado(self):
        ok, msg = auth.create_user("x1z", "X", "diretor")
        self.assertFalse(ok)
        self.assertIn("inválido", msg.lower())

    def test_login_curto_rejeitado(self):
        ok, msg = auth.create_user("ab", "AB", "vendedor")
        self.assertFalse(ok)

    def test_login_com_caractere_invalido_rejeitado(self):
        ok, _ = auth.create_user("jo ao", "Joao", "vendedor")
        self.assertFalse(ok)
        ok2, _ = auth.create_user("jo@ao", "Joao", "vendedor")
        self.assertFalse(ok2)

    def test_login_duplicado_rejeitado(self):
        auth.create_user("dup", "Dup", "vendedor")
        ok, msg = auth.create_user("dup", "Dup2", "gerente")
        self.assertFalse(ok)
        self.assertIn("existe", msg.lower())


class TestChangePassword(_AuthIsolated):
    def setUp(self):
        super().setUp()
        auth.create_user("ana", "Ana", "vendedor", senha="velha")

    def test_troca_senha_e_limpa_primeiro_acesso(self):
        self.assertTrue(auth.change_password("ana", "novasenha"))
        self.assertIsNone(auth.authenticate("ana", "velha"))
        u = auth.authenticate("ana", "novasenha")
        self.assertIsNotNone(u)
        self.assertFalse(u["primeiro_acesso"])

    def test_troca_de_login_inexistente_retorna_false(self):
        self.assertFalse(auth.change_password("naoexiste", "x"))


class TestUpdateUser(_AuthIsolated):
    def setUp(self):
        super().setUp()
        auth.create_user("ped", "Pedro", "vendedor")

    def test_atualiza_campos_permitidos(self):
        self.assertTrue(auth.update_user("ped", nome="Pedro Silva", perfil="gerente"))
        u = next(x for x in auth.list_users() if x["login"] == "ped")
        self.assertEqual(u["nome"], "Pedro Silva")
        self.assertEqual(u["perfil"], "gerente")

    def test_ignora_campos_nao_permitidos(self):
        # senha_hash e ativo NÃO estão na allowlist de update_user → ignorados.
        antes = next(x for x in auth.list_users() if x["login"] == "ped")["senha_hash"]
        auth.update_user("ped", senha_hash="hackeado", ativo=False)
        u = next(x for x in auth.list_users() if x["login"] == "ped")
        self.assertEqual(u["senha_hash"], antes)   # não alterado
        self.assertTrue(u["ativo"])                  # não alterado


class TestHierarquiaPermissoes(_AuthIsolated):
    """Não precisa de I/O — testa as funções puras de nível/permissão."""

    def _u(self, perfil):
        return {"perfil": perfil}

    def test_nivel_none_e_zero(self):
        self.assertEqual(auth.nivel(None), 0)
        self.assertEqual(auth.nivel({"perfil": "inexistente"}), 0)

    def test_ordem_da_hierarquia(self):
        self.assertGreater(auth.nivel(self._u("dev")), auth.nivel(self._u("admin")))
        self.assertGreater(auth.nivel(self._u("admin")), auth.nivel(self._u("gerente")))
        self.assertGreater(auth.nivel(self._u("gerente")), auth.nivel(self._u("vendedor")))
        self.assertGreater(auth.nivel(self._u("vendedor")), auth.nivel(self._u("captador")))

    def test_can_respeita_nivel_minimo(self):
        self.assertTrue(auth.can(self._u("gerente"), "vendedor"))
        self.assertTrue(auth.can(self._u("gerente"), "gerente"))
        self.assertFalse(auth.can(self._u("vendedor"), "gerente"))
        self.assertFalse(auth.can(None, "captador"))

    def test_is_helpers(self):
        self.assertTrue(auth.is_dev(self._u("dev")))
        self.assertFalse(auth.is_dev(self._u("admin")))
        self.assertTrue(auth.is_admin(self._u("admin")))
        self.assertTrue(auth.is_gerente(self._u("gerente")))
        self.assertFalse(auth.is_gerente(self._u("vendedor")))
        self.assertTrue(auth.is_vendedor(self._u("vendedor")))
        self.assertFalse(auth.is_vendedor(self._u("captador")))

    def test_cod_vendedor_do_usuario(self):
        self.assertEqual(auth.cod_vendedor_do_usuario({"cod_vendedor_microvix": 42}), "42")
        self.assertEqual(auth.cod_vendedor_do_usuario({}), "")
        self.assertEqual(auth.cod_vendedor_do_usuario(None), "")

    def test_perfis_criaveis_por(self):
        self.assertEqual(auth.perfis_criáveis_por(self._u("dev")), auth.PERFIS)
        self.assertNotIn("dev", auth.perfis_criáveis_por(self._u("admin")))
        self.assertNotIn("admin", auth.perfis_criáveis_por(self._u("admin")))
        self.assertEqual(
            set(auth.perfis_criáveis_por(self._u("gerente"))), {"vendedor", "captador"}
        )
        self.assertEqual(auth.perfis_criáveis_por(self._u("vendedor")), [])
        self.assertEqual(auth.perfis_criáveis_por(None), [])

    def test_perfil_display(self):
        self.assertEqual(auth.perfil_display(None), "—")
        self.assertIn("Vendedor", auth.perfil_display(self._u("vendedor")))


if __name__ == "__main__":
    unittest.main()
