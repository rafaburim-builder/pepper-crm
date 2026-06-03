"""
test_email_queue.py — Fila de e-mails do canal Brevo (builder, iteração 20).

Por que existe:
  modules/email_queue.py foi criado pelo usuário em 01/06/2026 junto com o
  transporte de e-mail (CANAL-EMAIL-WIRE). É a fila que o job das 02h consome
  para disparar reativação/pós-venda. Estava SEM teste. Cobre push/dedup,
  process_queue (sucesso/falha/retry/cap de histórico) e leitura de histórico,
  SEM tocar rede nem o Brevo real (cliente é injetado/dublê).

ESCOPO E SEGURANÇA:
  100% ISOLADO — email_queue.QUEUE e .HISTORY apontam para tempfiles; os
  arquivos data/email_queue.json e data/email_queue_history.json de produção
  (hoje inexistentes) NÃO são criados nem tocados (guard confirma).
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import email_queue, lgpd  # noqa: E402


class _FakeBrevo:
    """Dublê do BrevoClient — nunca toca rede. Decide ok/falha por destinatário."""

    def __init__(self, fail_emails=None):
        self.fail_emails = set(fail_emails or [])
        self.sent = []

    def send_email(self, to_email, to_name, subject, body_text):
        self.sent.append(to_email)
        if to_email in self.fail_emails:
            return (False, "SMTP 550 recusado")
        return (True, "ok")


class _QueueIsolated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._prod = [email_queue.QUEUE, email_queue.HISTORY, lgpd._PATH]
        cls._existia = {p: os.path.exists(p) for p in cls._prod}
        cls._mtime = {
            p: (os.path.getmtime(p) if cls._existia[p] else None) for p in cls._prod
        }

    @classmethod
    def tearDownClass(cls):
        for p in cls._prod:
            if cls._existia[p]:
                assert os.path.getmtime(p) == cls._mtime[p], (
                    f"arquivo de produção {p} foi modificado pela suíte!"
                )
            else:
                assert not os.path.exists(p), (
                    f"a suíte criou indevidamente o arquivo de produção {p}!"
                )

    def setUp(self):
        self._orig_q, self._orig_h, self._orig_l = (
            email_queue.QUEUE, email_queue.HISTORY, lgpd._PATH)
        self._tq = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._th = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tl = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tq.close()
        self._th.close()
        self._tl.close()
        os.unlink(self._tq.name)
        os.unlink(self._th.name)
        os.unlink(self._tl.name)
        email_queue.QUEUE = self._tq.name
        email_queue.HISTORY = self._th.name
        lgpd._PATH = self._tl.name

    def tearDown(self):
        email_queue.QUEUE, email_queue.HISTORY = self._orig_q, self._orig_h
        lgpd._PATH = self._orig_l
        for p in (self._tq.name, self._th.name, self._tl.name):
            if os.path.exists(p):
                os.unlink(p)


class TestPushToQueue(_QueueIsolated):
    def test_fila_vazia(self):
        self.assertEqual(email_queue.queue_size(), 0)
        self.assertEqual(email_queue._load(email_queue.QUEUE), [])

    def test_push_adiciona_e_conta(self):
        n = email_queue.push_to_queue(
            [{"id": 1, "nome": "Ana", "email": "ana@x.com", "assunto": "Oi",
              "mensagem": "msg", "segmento": "Em Risco"}]
        )
        self.assertEqual(n, 1)
        self.assertEqual(email_queue.queue_size(), 1)

    def test_push_preserva_campos_e_defaults(self):
        email_queue.push_to_queue(
            [{"id": 7, "nome": "Bia", "email": "bia@x.com",
              "assunto": "A", "mensagem": "M", "segmento": "Hibernando"}]
        )
        item = email_queue._load(email_queue.QUEUE)[0]
        self.assertEqual(item["id"], "7")          # coage para str
        self.assertEqual(item["email"], "bia@x.com")
        self.assertEqual(item["tentativas"], 0)
        self.assertIn("agendado_em", item)

    def test_push_dedup_email_ja_na_fila(self):
        email_queue.push_to_queue([{"email": "a@x.com", "nome": "A"}])
        n = email_queue.push_to_queue([{"email": "a@x.com", "nome": "A2"}])
        self.assertEqual(n, 0)
        self.assertEqual(email_queue.queue_size(), 1)

    def test_push_dedup_dentro_da_mesma_chamada(self):
        n = email_queue.push_to_queue(
            [{"email": "z@x.com"}, {"email": "z@x.com"}, {"email": "y@x.com"}]
        )
        self.assertEqual(n, 2)

    def test_push_ignora_sem_email(self):
        n = email_queue.push_to_queue([{"nome": "Sem email"}, {"email": ""}])
        self.assertEqual(n, 0)
        self.assertEqual(email_queue.queue_size(), 0)

    def test_arquivo_corrompido_retorna_lista_vazia(self):
        with open(email_queue.QUEUE, "w", encoding="utf-8") as f:
            f.write("{ não é json")
        self.assertEqual(email_queue._load(email_queue.QUEUE), [])
        self.assertEqual(email_queue.queue_size(), 0)


class TestGetHistory(_QueueIsolated):
    def test_history_vazio(self):
        self.assertEqual(email_queue.get_history(), [])

    def test_history_respeita_limite(self):
        email_queue._save(
            email_queue.HISTORY, [{"id": str(i)} for i in range(10)]
        )
        self.assertEqual(len(email_queue.get_history(limit=3)), 3)
        # devolve os ÚLTIMOS
        self.assertEqual(email_queue.get_history(limit=3)[-1]["id"], "9")


class TestProcessQueue(_QueueIsolated):
    def test_fila_vazia_nao_chama_brevo(self):
        r = email_queue.process_queue()
        self.assertEqual(r, {"enviados": 0, "falhas": 0, "erros": []})

    def test_brevo_nao_configurado_marca_falhas(self):
        email_queue.push_to_queue([{"email": "a@x.com", "nome": "A"}])
        with mock.patch("modules.email_sender.BrevoClient.from_config",
                        return_value=None):
            r = email_queue.process_queue()
        self.assertEqual(r["enviados"], 0)
        self.assertEqual(r["falhas"], 1)
        self.assertTrue(r["erros"])

    def test_envio_sucesso_esvazia_fila_e_arquiva(self):
        email_queue.push_to_queue(
            [{"email": "a@x.com", "nome": "A", "assunto": "S", "mensagem": "M"}]
        )
        fake = _FakeBrevo()
        with mock.patch("modules.email_sender.BrevoClient.from_config",
                        return_value=fake):
            r = email_queue.process_queue()
        self.assertEqual(r["enviados"], 1)
        self.assertEqual(r["falhas"], 0)
        self.assertEqual(email_queue.queue_size(), 0)          # fila esvaziada
        hist = email_queue.get_history(limit=10)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["resultado"], "enviado")
        self.assertEqual(fake.sent, ["a@x.com"])

    def test_falha_reenfileira_enquanto_tem_tentativas(self):
        email_queue.push_to_queue([{"email": "f@x.com", "nome": "F"}])
        fake = _FakeBrevo(fail_emails=["f@x.com"])
        with mock.patch("modules.email_sender.BrevoClient.from_config",
                        return_value=fake):
            r = email_queue.process_queue()
        self.assertEqual(r["falhas"], 1)
        self.assertEqual(email_queue.queue_size(), 1)          # voltou para a fila
        self.assertEqual(email_queue._load(email_queue.QUEUE)[0]["tentativas"], 1)

    def test_falha_descartada_apos_max_tentativas(self):
        email_queue.push_to_queue([{"email": "f@x.com", "nome": "F"}])
        # injeta tentativas já no limite-1: após +1 atinge MAX_TRIES e sai da fila
        fila = email_queue._load(email_queue.QUEUE)
        fila[0]["tentativas"] = email_queue.MAX_TRIES - 1
        email_queue._save(email_queue.QUEUE, fila)
        fake = _FakeBrevo(fail_emails=["f@x.com"])
        with mock.patch("modules.email_sender.BrevoClient.from_config",
                        return_value=fake):
            email_queue.process_queue()
        self.assertEqual(email_queue.queue_size(), 0)          # descartada

    def test_optout_descartado_no_disparo(self):
        # Backstop LGPD: cliente que pediu opt-out DEPOIS de entrar na fila é
        # descartado no disparo das 02h — não envia ao Brevo nem reenfileira.
        lgpd.set_optout("77")
        email_queue.push_to_queue(
            [{"id": "77", "email": "x@x.com", "nome": "X",
              "assunto": "S", "mensagem": "M"}]
        )
        fake = _FakeBrevo()
        with mock.patch("modules.email_sender.BrevoClient.from_config",
                        return_value=fake):
            r = email_queue.process_queue()
        self.assertEqual(r["enviados"], 0)
        self.assertEqual(r["falhas"], 0)
        self.assertEqual(fake.sent, [])                # nunca tocou o Brevo
        self.assertEqual(email_queue.queue_size(), 0)  # saiu da fila
        hist = email_queue.get_history(limit=10)
        self.assertEqual(hist[-1]["resultado"], "descartado: opt-out LGPD")

    def test_nao_optout_envia_normalmente(self):
        # Controle: sem opt-out, o disparo segue normal (não regrediu).
        email_queue.push_to_queue(
            [{"id": "88", "email": "y@x.com", "nome": "Y",
              "assunto": "S", "mensagem": "M"}]
        )
        fake = _FakeBrevo()
        with mock.patch("modules.email_sender.BrevoClient.from_config",
                        return_value=fake):
            r = email_queue.process_queue()
        self.assertEqual(r["enviados"], 1)
        self.assertEqual(fake.sent, ["y@x.com"])

    def test_historico_limitado_a_max_hist(self):
        # pré-popula histórico no limite e processa 1 sucesso → mantém MAX_HIST
        email_queue._save(
            email_queue.HISTORY,
            [{"id": str(i)} for i in range(email_queue.MAX_HIST)],
        )
        email_queue.push_to_queue([{"email": "a@x.com", "nome": "A"}])
        with mock.patch("modules.email_sender.BrevoClient.from_config",
                        return_value=_FakeBrevo()):
            email_queue.process_queue()
        self.assertEqual(
            len(email_queue._load(email_queue.HISTORY)), email_queue.MAX_HIST
        )


if __name__ == "__main__":
    unittest.main()
