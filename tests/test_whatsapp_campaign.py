"""
test_whatsapp_campaign.py — núcleo PURO da preparação de campanha de WhatsApp
(builder, iteração 18).

POR QUE EXISTE
  O WhatsApp é o ÚNICO canal de saída ativo, mas a fila bruta (todo cliente com
  telefone) gasta envios à toa: a iteração 10 achou 23 grupos / 63 clientes no
  mesmo número (maior grupo 11 = provável número da LOJA) e a iteração 11 achou
  que a trava anti-spam mensal chega VAZIA. modules/whatsapp_campaign.py é o
  análogo de email_campaign para o telefone — entrega a camada de PREPARAÇÃO
  (destinatários entregáveis: telefone normalizável + número-loja suprimido +
  trava mensal respeitada + dedup por aparelho) + renderização (link wa.me +
  mensagem), tudo PURO, sem rede / banco / credenciais. Ligá-lo é passo manual
  (LOG-1 / DADOS-5 / DADOS-6 no relatório).

ESCOPO E SEGURANÇA
  Só funções puras sobre base SINTÉTICA em memória. Um teste extra roda
  build_whatsapp_recipient_list SOMENTE-LEITURA sobre o client_map.json de
  PRODUÇÃO para reportar o número real de destinatários; um guard de mtime
  (setUpClass/tearDownClass) FALHA se a suíte tocar o arquivo de produção.
  Rodar:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import whatsapp_campaign as wc              # noqa: E402

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLIENT_MAP = os.path.join(_BASE, "data", "client_map.json")


# --------------------------------------------------------- predicado de contato
class TestContactedPredicate(unittest.TestCase):
    def test_none_means_nobody(self):
        pred = wc._contacted_predicate(None)
        self.assertFalse(pred("1"))
        self.assertFalse(pred("qualquer"))

    def test_iterable_of_codes(self):
        pred = wc._contacted_predicate(["1", "3"])
        self.assertTrue(pred("1"))
        self.assertTrue(pred("3"))
        self.assertFalse(pred("2"))

    def test_code_compared_as_string(self):
        # cods podem vir como int no map mas set construído por str
        pred = wc._contacted_predicate([1, 2])
        self.assertTrue(pred(1))
        self.assertTrue(pred("2"))

    def test_callable_passthrough(self):
        pred = wc._contacted_predicate(lambda cod: str(cod).startswith("a"))
        self.assertTrue(pred("abc"))
        self.assertFalse(pred("xyz"))


# ------------------------------------------------- build_whatsapp_recipient_list
class TestBuildRecipientList(unittest.TestCase):
    def _family(self):
        # 3 clientes no MESMO celular (família) + 1 com celular próprio.
        return {
            "1": {"nome": "Ana",  "fone": "(19) 99999-0000"},
            "2": {"nome": "Bia",  "fone": "19999990000"},
            "3": {"nome": "Cris", "fone": "+55 19 99999-0000"},
            "4": {"nome": "Davi", "fone": "11888887777"},
        }

    def test_dedup_keeps_one_per_phone(self):
        out = wc.build_whatsapp_recipient_list(self._family())
        st = out["stats"]
        self.assertEqual(st["com_fone_valido"], 4)
        self.assertEqual(st["entregaveis"], 2)            # 1 da família + Davi
        self.assertEqual(st["deduplicados_removidos"], 2)  # 3-1 na família
        self.assertEqual(st["loja_suprimidos"], 0)

    def test_dedup_keeps_first_by_code(self):
        out = wc.build_whatsapp_recipient_list(self._family())
        cods = {r["cod"] for r in out["recipients"]}
        self.assertIn("1", cods)   # menor cod do grupo família
        self.assertIn("4", cods)
        self.assertNotIn("2", cods)
        self.assertNotIn("3", cods)

    def test_phone_normalized_in_output(self):
        out = wc.build_whatsapp_recipient_list(
            {"1": {"nome": "Ana", "fone": "+55 (19) 99999-0000"}})
        self.assertEqual(out["recipients"][0]["fone"], "19999990000")

    def test_invalid_phone_skipped(self):
        cmap = {"1": {"nome": "Ana", "fone": ""},
                "2": {"nome": "Bia", "fone": "abc"},
                "3": {"nome": "Cris", "fone": "123"}}  # curto demais, sem DDD
        out = wc.build_whatsapp_recipient_list(cmap)
        self.assertEqual(out["stats"]["com_fone_valido"], 0)
        self.assertEqual(out["stats"]["entregaveis"], 0)

    def test_default_ddd_completes_cellphone(self):
        cmap = {"1": {"nome": "Ana", "fone": "99999-0000"}}  # 9 díg, sem DDD
        out = wc.build_whatsapp_recipient_list(cmap, default_ddd="11")
        self.assertEqual(out["recipients"][0]["fone"], "11999990000")

    def test_store_number_suppressed(self):
        # 5 clientes no mesmo número → número-loja/fallback, grupo inteiro sai.
        cmap = {str(i): {"nome": f"C{i}", "fone": "1133334444"} for i in range(5)}
        cmap["99"] = {"nome": "Real", "fone": "11999990000"}
        out = wc.build_whatsapp_recipient_list(cmap, store_threshold=5)
        st = out["stats"]
        self.assertEqual(st["loja_suprimidos"], 5)
        self.assertEqual(st["entregaveis"], 1)            # só o número próprio
        self.assertEqual(st["deduplicados_removidos"], 0)

    def test_store_threshold_preserves_family(self):
        # 4 no mesmo número, threshold 5 → família (não loja): dedup p/ 1.
        cmap = {str(i): {"nome": f"C{i}", "fone": "1133334444"} for i in range(4)}
        out = wc.build_whatsapp_recipient_list(cmap, store_threshold=5)
        st = out["stats"]
        self.assertEqual(st["loja_suprimidos"], 0)
        self.assertEqual(st["entregaveis"], 1)
        self.assertEqual(st["deduplicados_removidos"], 3)

    def test_monthly_guard_suppresses_contacted(self):
        cmap = {"1": {"nome": "Ana", "fone": "11999990001"},
                "2": {"nome": "Bia", "fone": "11999990002"}}
        out = wc.build_whatsapp_recipient_list(cmap, already_contacted=["1"])
        st = out["stats"]
        self.assertEqual(st["ja_contatados"], 1)
        self.assertEqual(st["entregaveis"], 1)
        self.assertEqual(out["recipients"][0]["cod"], "2")

    def test_monthly_guard_within_dedup_group_promotes_next(self):
        # família de 2; o 1º já foi contatado → o 2º assume o único envio.
        cmap = {"1": {"nome": "Ana", "fone": "11999990000"},
                "2": {"nome": "Bia", "fone": "11999990000"}}
        out = wc.build_whatsapp_recipient_list(cmap, already_contacted=["1"])
        st = out["stats"]
        self.assertEqual(st["ja_contatados"], 1)
        self.assertEqual(st["entregaveis"], 1)
        self.assertEqual(out["recipients"][0]["cod"], "2")
        self.assertEqual(st["deduplicados_removidos"], 0)

    def test_monthly_guard_whole_group_contacted(self):
        cmap = {"1": {"nome": "Ana", "fone": "11999990000"},
                "2": {"nome": "Bia", "fone": "11999990000"}}
        out = wc.build_whatsapp_recipient_list(cmap, already_contacted=["1", "2"])
        self.assertEqual(out["stats"]["ja_contatados"], 2)
        self.assertEqual(out["stats"]["entregaveis"], 0)

    def test_none_client_value_safe(self):
        cmap = {"1": None, "2": {"nome": "Ana", "fone": "11999990000"}}
        out = wc.build_whatsapp_recipient_list(cmap)
        self.assertEqual(out["stats"]["total_clients"], 2)
        self.assertEqual(out["stats"]["entregaveis"], 1)

    def test_empty_map(self):
        out = wc.build_whatsapp_recipient_list({})
        self.assertEqual(out["stats"]["total_clients"], 0)
        self.assertEqual(out["stats"]["entregaveis"], 0)
        self.assertEqual(out["recipients"], [])

    def test_recipients_sorted_by_code(self):
        cmap = {"30": {"nome": "C", "fone": "11999990003"},
                "10": {"nome": "A", "fone": "11999990001"},
                "20": {"nome": "B", "fone": "11999990002"}}
        out = wc.build_whatsapp_recipient_list(cmap)
        cods = [r["cod"] for r in out["recipients"]]
        self.assertEqual(cods, sorted(cods, key=str))

    def test_stats_conservation(self):
        # com_fone_valido = entregaveis + loja + ja_contatados + dedup_removidos
        cmap = {str(i): {"nome": f"C{i}", "fone": "1133334444"} for i in range(5)}
        cmap["a"] = {"nome": "Fam1", "fone": "11999990000"}
        cmap["b"] = {"nome": "Fam2", "fone": "11999990000"}
        cmap["c"] = {"nome": "Solo", "fone": "11888887777"}
        out = wc.build_whatsapp_recipient_list(
            cmap, store_threshold=5, already_contacted=["c"])
        st = out["stats"]
        self.assertEqual(
            st["com_fone_valido"],
            st["entregaveis"] + st["loja_suprimidos"]
            + st["ja_contatados"] + st["deduplicados_removidos"])


# ------------------------------------------------------------- render_whatsapp
class TestRenderWhatsApp(unittest.TestCase):
    def test_default_render_substitutes(self):
        out = wc.render_whatsapp("Ana Maria Silva", "19999990000",
                                 categoria="LV", data="10/01/2025", dias=120)
        self.assertIn("Ana", out["mensagem"])
        self.assertIn("armação de grau", out["mensagem"])
        self.assertIn("120", out["mensagem"])
        self.assertTrue(out["link"].startswith("https://wa.me/5519999990000?text="))

    def test_first_name_only(self):
        out = wc.render_whatsapp("Ana Maria Silva", "19999990000")
        self.assertIn("Ana", out["mensagem"])
        self.assertNotIn("Ana Maria Silva", out["mensagem"])

    def test_invalid_phone_empty_link(self):
        out = wc.render_whatsapp("Ana", "abc")
        self.assertEqual(out["link"], "")
        self.assertIn("Ana", out["mensagem"])   # mensagem ainda renderiza

    def test_returns_both_keys(self):
        out = wc.render_whatsapp("Ana", "11999990000")
        self.assertEqual(set(out.keys()), {"mensagem", "link"})


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
        """Reporta o número real de destinatários de WhatsApp sobre a base de
        produção (somente leitura) — quantos envios ÚTEIS sobram após dedup por
        aparelho e supressão de número-loja."""
        if not os.path.exists(_CLIENT_MAP):
            self.skipTest("client_map.json de produção ausente")
        with open(_CLIENT_MAP, encoding="utf-8") as f:
            cmap = json.load(f)
        out = wc.build_whatsapp_recipient_list(cmap)
        st = out["stats"]
        # invariantes (não números mágicos frágeis):
        self.assertEqual(len(out["recipients"]), st["entregaveis"])
        self.assertLessEqual(st["entregaveis"], st["com_fone_valido"])
        self.assertEqual(
            st["com_fone_valido"],
            st["entregaveis"] + st["loja_suprimidos"]
            + st["ja_contatados"] + st["deduplicados_removidos"])
        # telefones de saída são únicos (dedup real por aparelho)
        fones = [r["fone"] for r in out["recipients"]]
        self.assertEqual(len(fones), len(set(fones)))
        print(f"\n[PROD whatsapp_campaign] base={st['total_clients']} "
              f"fone_valido={st['com_fone_valido']} "
              f"loja_suprimidos={st['loja_suprimidos']} "
              f"dedup={st['deduplicados_removidos']} "
              f"ENVIOS_UTEIS={st['entregaveis']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
