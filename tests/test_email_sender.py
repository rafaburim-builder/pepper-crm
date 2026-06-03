"""
test_email_sender.py — Transporte de e-mail via Brevo (builder, iteração 21).

Por que existe:
  modules/email_sender.py foi criado pelo usuário em 01/06/2026 com o canal de
  e-mail (CANAL-EMAIL-WIRE). É o ÚNICO módulo novo que continuava SEM nenhum
  teste (Iter 20 cobriu email_queue + pos_venda; prescricao já estava coberto).
  Cobre config (load/save/is_configured), _texto_para_html, BrevoClient
  (from_config + send_email + send_bulk) e test_connection — SEM tocar rede
  (requests é mockado) nem o data/email_config.json de PRODUÇÃO.

ESCOPO E SEGURANÇA:
  100% ISOLADO — email_sender._CFG_PATH aponta para tempfile durante os testes;
  o data/email_config.json de produção (que HOJE contém a chave Brevo em
  plaintext — ver SEGREDO-EMAIL) NÃO é lido, escrito nem alterado (guard de
  mtime confirma). NENHUMA chave real é carregada ou impressa: os testes usam
  uma chave-fake "xkeysib-FAKE". 'requests' é substituído por dublê → zero rede.
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import sys
import json
import tempfile
import unittest
from unittest import mock

import requests as _real_requests  # classe Timeout real p/ os except do módulo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import email_sender as es  # noqa: E402


class _FakeResp:
    """Resposta HTTP dublê para mockar requests.post / requests.get."""

    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data or {}

    def json(self):
        return self._json


class _SenderIsolated(unittest.TestCase):
    """Redireciona _CFG_PATH para tempfile e protege o config de produção."""

    @classmethod
    def setUpClass(cls):
        cls._prod_path = es._CFG_PATH
        cls._prod_existia = os.path.exists(cls._prod_path)
        cls._prod_mtime = (
            os.path.getmtime(cls._prod_path) if cls._prod_existia else None
        )

    @classmethod
    def tearDownClass(cls):
        if cls._prod_existia:
            assert os.path.getmtime(cls._prod_path) == cls._prod_mtime, (
                "data/email_config.json de produção foi modificado pela suíte!"
            )
        else:
            assert not os.path.exists(cls._prod_path), (
                "a suíte criou indevidamente um data/email_config.json de produção!"
            )

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        self._tmp = tmp.name
        self._orig = es._CFG_PATH
        es._CFG_PATH = self._tmp

    def tearDown(self):
        es._CFG_PATH = self._orig
        if os.path.exists(self._tmp):
            os.unlink(self._tmp)

    def _write_cfg(self, cfg):
        with open(self._tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f)


class TestConfig(_SenderIsolated):
    def test_load_inexistente_retorna_vazio(self):
        self.assertEqual(es.load_email_config(), {})

    def test_load_corrompido_retorna_vazio(self):
        with open(self._tmp, "w", encoding="utf-8") as f:
            f.write("{ isto não é json válido ")
        self.assertEqual(es.load_email_config(), {})

    def test_save_e_load_roundtrip(self):
        cfg = {"brevo_api_key": "xkeysib-FAKE", "sender_email": "a@b.com",
               "sender_name": "Ótica P. Ferreira"}
        es.save_email_config(cfg)
        self.assertEqual(es.load_email_config(), cfg)

    def test_save_preserva_acentos(self):
        es.save_email_config({"sender_name": "Ótica São José"})
        with open(self._tmp, encoding="utf-8") as f:
            raw = f.read()
        self.assertIn("Ótica São José", raw)  # ensure_ascii=False

    def test_is_configured_so_com_key_e_email(self):
        self.assertFalse(es.is_email_configured())  # vazio
        es.save_email_config({"brevo_api_key": "xkeysib-FAKE"})
        self.assertFalse(es.is_email_configured())  # falta sender_email
        es.save_email_config({"sender_email": "a@b.com"})
        self.assertFalse(es.is_email_configured())  # falta key
        es.save_email_config({"brevo_api_key": "xkeysib-FAKE",
                              "sender_email": "a@b.com"})
        self.assertTrue(es.is_email_configured())


class TestTextoParaHtml(_SenderIsolated):
    def test_remove_link_wa_me(self):
        html = es._texto_para_html("Olá! Veja: https://wa.me/5511999999999 tchau")
        self.assertNotIn("wa.me", html)

    def test_quebra_em_paragrafos(self):
        html = es._texto_para_html("linha1\nlinha2\n\nlinha3")
        self.assertEqual(html.count("<p>"), 3)  # linhas vazias ignoradas

    def test_envelopa_html_e_rodape(self):
        html = es._texto_para_html("oi")
        self.assertIn("<html>", html)
        self.assertIn("</body></html>", html)
        self.assertIn("Ótica P. Ferreira", html)  # rodapé de identificação

    def test_texto_vazio_nao_quebra(self):
        html = es._texto_para_html("")
        self.assertIn("<html>", html)
        self.assertEqual(html.count("<p>"), 0)  # rodapé usa <p style=...>, não <p>
        self.assertIn("Você está recebendo", html)  # rodapé presente


class TestFromConfig(_SenderIsolated):
    def test_from_config_nao_configurado_retorna_none(self):
        self.assertIsNone(es.BrevoClient.from_config())

    def test_from_config_constroi_cliente(self):
        es.save_email_config({"brevo_api_key": "xkeysib-FAKE",
                              "sender_email": "loja@otica.com",
                              "sender_name": "Loja"})
        c = es.BrevoClient.from_config()
        self.assertIsNotNone(c)
        self.assertEqual(c.api_key, "xkeysib-FAKE")
        self.assertEqual(c.sender_email, "loja@otica.com")
        self.assertEqual(c.sender_name, "Loja")

    def test_from_config_sender_name_default(self):
        es.save_email_config({"brevo_api_key": "xkeysib-FAKE",
                              "sender_email": "loja@otica.com"})
        c = es.BrevoClient.from_config()
        self.assertEqual(c.sender_name, "Ótica P. Ferreira")


class TestSendEmail(_SenderIsolated):
    def _client(self):
        return es.BrevoClient("xkeysib-FAKE", "loja@otica.com", "Loja")

    def test_email_invalido_nao_dispara(self):
        ok, msg = self._client().send_email("", "Fulano", "Assunto", "Corpo")
        self.assertFalse(ok)
        ok2, _ = self._client().send_email("semarroba", "Fulano", "A", "B")
        self.assertFalse(ok2)

    def test_sucesso_200(self):
        with mock.patch.object(es, "requests") as rq:
            rq.post.return_value = _FakeResp(200)
            ok, msg = self._client().send_email("c@x.com", "Cliente", "Oi", "Corpo")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_sucesso_201(self):
        with mock.patch.object(es, "requests") as rq:
            rq.post.return_value = _FakeResp(201)
            ok, _ = self._client().send_email("c@x.com", "Cliente", "Oi", "Corpo")
        self.assertTrue(ok)

    def test_status_erro_propaga_mensagem(self):
        with mock.patch.object(es, "requests") as rq:
            rq.post.return_value = _FakeResp(400, text="bad request detail")
            ok, msg = self._client().send_email("c@x.com", "C", "Oi", "Corpo")
        self.assertFalse(ok)
        self.assertIn("400", msg)

    def test_payload_envia_html_e_texto(self):
        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["json"] = json
            captured["headers"] = headers
            return _FakeResp(200)

        with mock.patch.object(es, "requests") as rq:
            rq.post.side_effect = fake_post
            self._client().send_email("c@x.com", "Cliente",
                                      "Assunto", "Linha A\nhttps://wa.me/55 fim")
        self.assertEqual(captured["headers"]["api-key"], "xkeysib-FAKE")
        self.assertIn("htmlContent", captured["json"])
        self.assertIn("textContent", captured["json"])
        # corpo HTML não pode conter o link wa.me
        self.assertNotIn("wa.me", captured["json"]["htmlContent"])
        # mas o textContent mantém o corpo original
        self.assertIn("wa.me", captured["json"]["textContent"])

    def test_timeout_tratado(self):
        with mock.patch.object(es, "requests") as rq:
            rq.Timeout = _real_requests.Timeout  # classe real p/ o except do módulo
            rq.post.side_effect = _real_requests.Timeout()
            ok, msg = self._client().send_email("c@x.com", "C", "Oi", "Corpo")
        self.assertFalse(ok)
        self.assertIn("Timeout", msg)

    def test_excecao_generica_tratada(self):
        with mock.patch.object(es, "requests") as rq:
            rq.Timeout = _real_requests.Timeout
            rq.post.side_effect = ValueError("boom")
            ok, msg = self._client().send_email("c@x.com", "C", "Oi", "Corpo")
        self.assertFalse(ok)
        self.assertIn("ValueError", msg)


class TestSendBulk(_SenderIsolated):
    def test_agrega_enviados_falhas_e_erros(self):
        c = es.BrevoClient("xkeysib-FAKE", "loja@otica.com", "Loja")
        recipients = [
            {"email": "ok1@x.com", "nome": "A", "mensagem": "m"},
            {"email": "", "nome": "SemEmail", "mensagem": "m"},  # inválido
            {"email": "ok2@x.com", "nome": "B", "mensagem": "m"},
        ]
        with mock.patch.object(es, "requests") as rq:
            rq.post.return_value = _FakeResp(200)
            res = c.send_bulk(recipients, "Campanha")
        self.assertEqual(res["enviados"], 2)
        self.assertEqual(res["falhas"], 1)
        self.assertEqual(len(res["erros"]), 1)
        self.assertIn("SemEmail", res["erros"][0])


class TestConnection(_SenderIsolated):
    def test_conexao_ok_parseia_plano(self):
        with mock.patch.object(es, "requests") as rq:
            rq.get.return_value = _FakeResp(200, json_data={"plan": [{"type": "free"}]})
            ok, msg = es.test_connection("xkeysib-FAKE", "loja@otica.com")
        self.assertTrue(ok)
        self.assertIn("free", msg)
        self.assertIn("loja@otica.com", msg)

    def test_conexao_status_erro(self):
        with mock.patch.object(es, "requests") as rq:
            rq.get.return_value = _FakeResp(401, text="unauthorized")
            ok, msg = es.test_connection("xkeysib-RUIM", "loja@otica.com")
        self.assertFalse(ok)
        self.assertIn("401", msg)

    def test_conexao_excecao(self):
        with mock.patch.object(es, "requests") as rq:
            rq.get.side_effect = ConnectionError("sem rede")
            ok, msg = es.test_connection("xkeysib-FAKE", "loja@otica.com")
        self.assertFalse(ok)
        self.assertIn("Erro de conexão", msg)


if __name__ == "__main__":
    unittest.main()
