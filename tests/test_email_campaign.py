"""
test_email_campaign.py — núcleo PURO da preparação de campanha de e-mail
(builder, iteração 16).

POR QUE EXISTE
  As iterações 8–14 fecharam, com números de produção, o caso de negócio do
  CANAL-EMAIL (maior alavanca de alcance — ~962 clientes hoje inalcançáveis,
  cobertura territorial fora de SP). modules/email_campaign.py entrega a camada
  de PREPARAÇÃO da campanha (seleção de destinatários entregáveis + renderização
  de mensagem), pura e sem efeitos colaterais, para que o canal possa ser ligado
  com um núcleo já testado. NÃO há transporte SMTP / credenciais / I/O aqui.

ESCOPO E SEGURANÇA
  Só funções puras sobre base SINTÉTICA em memória. Um teste extra roda
  build_recipient_list SOMENTE-LEITURA sobre o client_map.json de PRODUÇÃO para
  reportar o número real de destinatários entregáveis; um guard de mtime
  (setUpClass/tearDownClass) FALHA se a suíte tocar o arquivo de produção.
  Rodar:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import email_campaign as ec               # noqa: E402

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLIENT_MAP = os.path.join(_BASE, "data", "client_map.json")


# --------------------------------------------------------------- funções puras
class TestEmailValidation(unittest.TestCase):
    def test_valid_email_basic(self):
        self.assertTrue(ec.is_valid_email("ana@gmail.com"))
        self.assertTrue(ec.is_valid_email("  ana.silva@dominio.com.br  "))

    def test_invalid_email(self):
        for bad in ["", None, "semarroba.com", "a@b", "a@b.c d", "@gmail.com",
                    "ana@", "ana@@gmail.com", "ana gmail.com"]:
            self.assertFalse(ec.is_valid_email(bad), bad)

    def test_email_local_and_domain(self):
        self.assertEqual(ec.email_local("Ana@Gmail.COM"), "ana")
        self.assertEqual(ec.email_domain("Ana@Gmail.COM"), "gmail.com")
        self.assertEqual(ec.email_local("invalido"), "")
        self.assertEqual(ec.email_domain("invalido"), "")

    def test_normalize_email(self):
        self.assertEqual(ec.normalize_email("  Ana@Gmail.com "), "ana@gmail.com")
        self.assertEqual(ec.normalize_email("ruim"), "")


class TestPlaceholder(unittest.TestCase):
    def test_placeholder_markers(self):
        for p in ["naotem@gmail.com", "nao@gmail.com", "n@gmail.com",
                  "naosei@gmail.com", "sememail@x.com", "x@x.com",
                  "xxxx@x.com", "teste@x.com", "test@x.com", "cliente@x.com",
                  "consumidor@x.com", "nenhum@x.com"]:
            self.assertTrue(ec.is_placeholder_email(p), p)

    def test_real_email_not_placeholder(self):
        for ok in ["ana@gmail.com", "joao.silva@uol.com.br",
                   "maria_2020@hotmail.com", "naotemmedo@gmail.com"]:
            self.assertFalse(ec.is_placeholder_email(ok), ok)

    def test_placeholder_requires_valid_format(self):
        # "nao" sem domínio não é e-mail válido → não é placeholder-entregável
        self.assertFalse(ec.is_placeholder_email("nao"))


# ---------------------------------------------------- build_recipient_list
class TestRecipientList(unittest.TestCase):
    def test_empty(self):
        out = ec.build_recipient_list({})
        self.assertEqual(out["recipients"], [])
        self.assertEqual(out["stats"]["total_clients"], 0)
        self.assertEqual(out["stats"]["entregaveis"], 0)

    def test_basic_filtering(self):
        cmap = {
            "1": {"nome": "Ana",   "email": "ana@gmail.com"},
            "2": {"nome": "Bia",   "email": "invalido"},          # formato ruim
            "3": {"nome": "Caio",  "email": "naotem@gmail.com"},  # placeholder
            "4": {"nome": "Duda",  "email": ""},                  # vazio
        }
        out = ec.build_recipient_list(cmap)
        st = out["stats"]
        self.assertEqual(st["total_clients"], 4)
        self.assertEqual(st["com_email_formato_valido"], 2)   # ana + naotem
        self.assertEqual(st["placeholder_suprimidos"], 1)     # naotem
        self.assertEqual(st["entregaveis"], 1)                # só ana
        self.assertEqual([r["cod"] for r in out["recipients"]], ["1"])
        self.assertEqual(out["recipients"][0]["email"], "ana@gmail.com")

    def test_dedup_keeps_one_per_address(self):
        cmap = {
            "10": {"nome": "Ana",  "email": "familia@gmail.com"},
            "11": {"nome": "Bia",  "email": "Familia@Gmail.com"},  # mesmo addr
        }
        out = ec.build_recipient_list(cmap, shared_threshold=3)
        self.assertEqual(out["stats"]["entregaveis"], 1)
        self.assertEqual(out["stats"]["deduplicados_removidos"], 1)
        # determinístico: mantém o menor código
        self.assertEqual(out["recipients"][0]["cod"], "10")

    def test_shared_email_suppressed(self):
        # 3 clientes com o mesmo e-mail (>= shared_threshold) → suprime todos
        cmap = {str(i): {"nome": f"C{i}", "email": "loja@gmail.com"}
                for i in range(3)}
        out = ec.build_recipient_list(cmap, shared_threshold=3)
        self.assertEqual(out["stats"]["compartilhados_suprimidos"], 3)
        self.assertEqual(out["stats"]["entregaveis"], 0)
        self.assertEqual(out["recipients"], [])

    def test_threshold_boundary(self):
        # 2 iguais com threshold=3 → NÃO suprime (dedup mantém 1)
        cmap = {"1": {"nome": "A", "email": "casa@y.com"},
                "2": {"nome": "B", "email": "casa@y.com"}}
        out = ec.build_recipient_list(cmap, shared_threshold=3)
        self.assertEqual(out["stats"]["entregaveis"], 1)
        self.assertEqual(out["stats"]["compartilhados_suprimidos"], 0)
        self.assertEqual(out["stats"]["deduplicados_removidos"], 1)

    def test_email_normalized_in_output(self):
        cmap = {"1": {"nome": "Ana", "email": "  Ana@GMAIL.com "}}
        out = ec.build_recipient_list(cmap)
        self.assertEqual(out["recipients"][0]["email"], "ana@gmail.com")

    def test_none_client_value_safe(self):
        cmap = {"1": None, "2": {"nome": "Ana", "email": "ana@gmail.com"}}
        out = ec.build_recipient_list(cmap)
        self.assertEqual(out["stats"]["entregaveis"], 1)


# -------------------------------------------------------------- render_email
class TestRenderEmail(unittest.TestCase):
    def test_default_render_substitutes(self):
        out = ec.render_email("Ana Maria Silva", categoria="LV",
                              data="10/01/2025", dias=120)
        self.assertIn("Ana", out["corpo"])
        self.assertIn("Ana", out["assunto"])
        # categoria mapeada via marketing._CAT_LABEL
        self.assertIn("armação de grau", out["corpo"])
        self.assertIn("120", out["corpo"])
        self.assertIn("10/01/2025", out["corpo"])

    def test_first_name_only(self):
        out = ec.render_email("Ana Maria Silva")
        # format_message usa só o primeiro nome
        self.assertIn("Ana", out["assunto"])
        self.assertNotIn("Ana Maria Silva", out["assunto"])

    def test_custom_templates(self):
        out = ec.render_email("Joao", subject_template="Oi {nome}",
                              body_template="Corpo de {nome}, {dias} dias", dias=5)
        self.assertEqual(out["assunto"], "Oi Joao")
        self.assertEqual(out["corpo"], "Corpo de Joao, 5 dias")

    def test_returns_both_keys(self):
        out = ec.render_email("Ana")
        self.assertEqual(set(out.keys()), {"assunto", "corpo"})


# --------------------------- run SOMENTE-LEITURA sobre PRODUÇÃO + guard de mtime
class TestProductionReadOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._mtime_before = (os.path.getmtime(_CLIENT_MAP)
                             if os.path.exists(_CLIENT_MAP) else None)

    @classmethod
    def tearDownClass(cls):
        if cls._mtime_before is not None:
            after = os.path.getmtime(_CLIENT_MAP)
            assert after == cls._mtime_before, (
                "client_map.json de PRODUÇÃO foi modificado pela suíte!")

    def test_real_deliverable_count(self):
        """Reporta o número real de destinatários entregáveis da campanha de
        e-mail sobre a base de produção (somente leitura)."""
        if not os.path.exists(_CLIENT_MAP):
            self.skipTest("client_map.json de produção ausente")
        with open(_CLIENT_MAP, encoding="utf-8") as f:
            cmap = json.load(f)
        out = ec.build_recipient_list(cmap, shared_threshold=3)
        st = out["stats"]
        # invariantes (não números mágicos frágeis):
        self.assertEqual(len(out["recipients"]), st["entregaveis"])
        self.assertLessEqual(st["entregaveis"], st["com_email_formato_valido"])
        self.assertEqual(
            st["com_email_formato_valido"],
            st["entregaveis"] + st["placeholder_suprimidos"]
            + st["compartilhados_suprimidos"] + st["deduplicados_removidos"],
        )
        # endereços de saída são únicos (dedup real)
        addrs = [r["email"] for r in out["recipients"]]
        self.assertEqual(len(addrs), len(set(addrs)))
        print(f"\n[PROD email_campaign] base={st['total_clients']} "
              f"formato_valido={st['com_email_formato_valido']} "
              f"placeholder={st['placeholder_suprimidos']} "
              f"compartilhados={st['compartilhados_suprimidos']} "
              f"dedup={st['deduplicados_removidos']} "
              f"ENTREGAVEIS={st['entregaveis']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
