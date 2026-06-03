"""
test_secure_store.py — Testes do cofre de segredos (modules/secure_store.py).

Por que existe (auditoria de segurança, builder):
  secure_store.py é o componente que tira o token Microvix + certificado A1 +
  senha do certificado de dentro do config.json sincronizado no OneDrive e os
  guarda em um cofre LOCAL fora do OneDrive. Como é o componente de segurança
  #1 do app e é "best-effort" (nunca pode quebrar o app), travamos seu
  comportamento com regressão automatizada.

ISOLAMENTO (importante):
  Todos os testes apontam PEPPER_SECRETS_DIR para um diretório TEMPORÁRIO via
  setUp/tearDown. NENHUM teste toca o cofre real em %LOCALAPPDATA%\\Pepper.
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import json
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import secure_store  # noqa: E402


class _IsoladoBase(unittest.TestCase):
    """Aponta o cofre para um tempdir antes de cada teste e restaura depois."""

    def setUp(self):
        self._prev = os.environ.get("PEPPER_SECRETS_DIR")
        self._tmp = tempfile.mkdtemp(prefix="pepper-secrets-test-")
        os.environ["PEPPER_SECRETS_DIR"] = self._tmp

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("PEPPER_SECRETS_DIR", None)
        else:
            os.environ["PEPPER_SECRETS_DIR"] = self._prev
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestCaminhoDoCofre(_IsoladoBase):

    def test_secrets_dir_respeita_override(self):
        self.assertEqual(secure_store.secrets_dir(), self._tmp)

    def test_secrets_path_dentro_do_dir(self):
        self.assertEqual(
            secure_store.secrets_path(),
            os.path.join(self._tmp, "secrets.json"),
        )

    def test_secrets_dir_cria_diretorio(self):
        # aponta para um subdir inexistente; secrets_dir deve criá-lo
        novo = os.path.join(self._tmp, "sub", "nivel2")
        os.environ["PEPPER_SECRETS_DIR"] = novo
        self.assertEqual(secure_store.secrets_dir(), novo)
        self.assertTrue(os.path.isdir(novo))


class TestRoundTrip(_IsoladoBase):

    def test_load_vazio_quando_nao_existe(self):
        self.assertEqual(secure_store.load_secrets(), {})

    def test_save_e_load_round_trip(self):
        payload = {"token": "ABC123", "sefaz_cert_password": "senha-secreta"}
        self.assertTrue(secure_store.save_secrets(payload))
        self.assertEqual(secure_store.load_secrets(), payload)

    def test_save_sobrescreve(self):
        secure_store.save_secrets({"token": "v1"})
        secure_store.save_secrets({"token": "v2"})
        self.assertEqual(secure_store.load_secrets(), {"token": "v2"})

    def test_load_retorna_vazio_em_json_corrompido(self):
        with open(secure_store.secrets_path(), "w", encoding="utf-8") as f:
            f.write("{ isto nao e json valido ")
        self.assertEqual(secure_store.load_secrets(), {})

    def test_load_retorna_vazio_se_topo_nao_for_dict(self):
        with open(secure_store.secrets_path(), "w", encoding="utf-8") as f:
            json.dump(["lista", "nao", "dict"], f)
        self.assertEqual(secure_store.load_secrets(), {})

    def test_save_unicode_preservado(self):
        payload = {"token": "açãõ-ç-€-✓"}
        secure_store.save_secrets(payload)
        self.assertEqual(secure_store.load_secrets()["token"], "açãõ-ç-€-✓")


class TestEscritaAtomica(_IsoladoBase):

    def test_nao_deixa_arquivos_temporarios(self):
        secure_store.save_secrets({"token": "x"})
        sobras = [n for n in os.listdir(self._tmp) if n.startswith(".secrets-")]
        self.assertEqual(sobras, [], f"arquivos .tmp não removidos: {sobras}")

    def test_arquivo_final_chama_secrets_json(self):
        secure_store.save_secrets({"token": "x"})
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "secrets.json")))


class TestSplitDisk(unittest.TestCase):
    """split_disk não tem efeito colateral em disco — não precisa de isolamento."""

    def test_esvazia_todos_os_campos_sensiveis(self):
        full = {
            "token": "T", "sefaz_cert_b64": "CERT", "sefaz_cert_password": "P",
            "cnpj": "00.000.000/0001-00", "loja": "Matriz",
        }
        on_disk = secure_store.split_disk(full)
        for k in secure_store.SENSITIVE_KEYS:
            self.assertEqual(on_disk[k], "", f"{k} deveria estar vazio")

    def test_preserva_campos_nao_sensiveis(self):
        full = {"token": "T", "cnpj": "123", "loja": "Matriz"}
        on_disk = secure_store.split_disk(full)
        self.assertEqual(on_disk["cnpj"], "123")
        self.assertEqual(on_disk["loja"], "Matriz")

    def test_nao_muta_o_original(self):
        full = {"token": "T", "cnpj": "123"}
        secure_store.split_disk(full)
        self.assertEqual(full["token"], "T", "split_disk não pode mutar o dict de entrada")

    def test_campos_sensiveis_esperados(self):
        # trava a lista — se alguém adicionar um segredo novo, atualiza o teste de propósito
        self.assertEqual(
            set(secure_store.SENSITIVE_KEYS),
            {"token", "sefaz_cert_b64", "sefaz_cert_password"},
        )


class TestHasPlaintext(unittest.TestCase):

    def test_true_quando_tem_token(self):
        self.assertTrue(secure_store.has_plaintext({"token": "abc"}))

    def test_true_quando_tem_certificado(self):
        self.assertTrue(secure_store.has_plaintext({"sefaz_cert_b64": "MIIxxx"}))

    def test_false_quando_tudo_vazio(self):
        self.assertFalse(secure_store.has_plaintext(
            {"token": "", "sefaz_cert_b64": "", "sefaz_cert_password": ""}
        ))

    def test_false_quando_ausente(self):
        self.assertFalse(secure_store.has_plaintext({"cnpj": "123", "loja": "X"}))

    def test_false_para_dict_vazio(self):
        self.assertFalse(secure_store.has_plaintext({}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
