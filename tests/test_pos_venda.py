"""
test_pos_venda.py — Régua de pós-venda D+1/7/30/90 (builder, iteração 20).

Por que existe:
  modules/pos_venda.py foi criado pelo usuário em 01/06/2026. Agenda 4
  touchpoints de relacionamento por venda na fila de e-mail. Estava SEM teste.
  Cobre a matemática de janelas (só agenda touchpoints FUTUROS), a trava de
  opt-out LGPD, o dedup por venda (não reagenda a mesma venda) e o scan a
  partir do df_retorno.

ESCOPO E SEGURANÇA:
  100% ISOLADO — pos_venda._LOG, email_queue.QUEUE/HISTORY e lgpd._PATH
  apontam para tempfiles; nenhum arquivo de produção (pos_venda_log.json,
  email_queue*.json, lgpd_optout.json — hoje todos inexistentes) é criado ou
  tocado (guard confirma). NÃO toca rede/Brevo (register só enfileira).
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import pos_venda, email_queue, lgpd  # noqa: E402


class _PosVendaIsolated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._prod = [
            pos_venda._LOG, email_queue.QUEUE, email_queue.HISTORY, lgpd._PATH,
        ]
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
        self._orig = (pos_venda._LOG, email_queue.QUEUE, email_queue.HISTORY,
                      lgpd._PATH)
        self._tmps = []
        for _ in range(4):
            t = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
            t.close()
            os.unlink(t.name)
            self._tmps.append(t.name)
        pos_venda._LOG = self._tmps[0]
        email_queue.QUEUE = self._tmps[1]
        email_queue.HISTORY = self._tmps[2]
        lgpd._PATH = self._tmps[3]

    def tearDown(self):
        (pos_venda._LOG, email_queue.QUEUE, email_queue.HISTORY,
         lgpd._PATH) = self._orig
        for p in self._tmps:
            if os.path.exists(p):
                os.unlink(p)


class TestLog(_PosVendaIsolated):
    def test_log_vazio(self):
        self.assertEqual(pos_venda._load_log(), {})

    def test_log_round_trip(self):
        pos_venda._save_log({"k": {"x": 1}})
        self.assertEqual(pos_venda._load_log(), {"k": {"x": 1}})

    def test_log_corrompido_retorna_vazio(self):
        with open(pos_venda._LOG, "w", encoding="utf-8") as f:
            f.write("{ não é json")
        self.assertEqual(pos_venda._load_log(), {})


class TestRegister(_PosVendaIsolated):
    def test_sem_email_retorna_zero(self):
        n = pos_venda.register_sale_for_pos_venda("1", "Ana", "", date.today())
        self.assertEqual(n, 0)
        self.assertEqual(email_queue.queue_size(), 0)

    def test_venda_hoje_conta_quatro_agendados(self):
        n = pos_venda.register_sale_for_pos_venda(
            "1", "Ana", "ana@x.com", date.today()
        )
        self.assertEqual(n, 4)                       # contador agendados = D+1/7/30/90

    def test_BUG_POSVENDA1_dedup_email_descarta_touchpoints_alem_do_D1(self):
        # POSVENDA-1 (bug conhecido, travado de propósito): register chama
        # push_to_queue 1x POR touchpoint, todos com o MESMO e-mail. push_to_queue
        # dedup-a por e-mail => só o D+1 entra na fila; D+7/D+30/D+90 são
        # silenciosamente descartados, e a régua de pós-venda fica inerte além do
        # 1º dia. Este teste trava o comportamento ATUAL (errado) p/ um fix futuro
        # ser deliberado. Ver relatório: POSVENDA-1.
        pos_venda.register_sale_for_pos_venda("1", "Ana", "ana@x.com", date.today())
        self.assertEqual(email_queue.queue_size(), 1)

    def test_dedup_mesma_venda_nao_reagenda(self):
        d = date.today()
        pos_venda.register_sale_for_pos_venda("1", "Ana", "ana@x.com", d)
        n2 = pos_venda.register_sale_for_pos_venda("1", "Ana", "ana@x.com", d)
        self.assertEqual(n2, 0)                      # key já no log

    def test_so_agenda_touchpoints_futuros(self):
        # venda há 40 dias: D+1/7/30 já passaram, só D+90 (=+50) é futuro
        venda = date.today() - timedelta(days=40)
        n = pos_venda.register_sale_for_pos_venda("9", "Bia", "bia@x.com", venda)
        self.assertEqual(n, 1)
        self.assertEqual(email_queue.queue_size(), 1)

    def test_venda_muito_antiga_nao_agenda_nem_grava_log(self):
        venda = date.today() - timedelta(days=200)   # todos os touchpoints no passado
        n = pos_venda.register_sale_for_pos_venda("9", "Bia", "bia@x.com", venda)
        self.assertEqual(n, 0)
        self.assertEqual(pos_venda._load_log(), {})   # nada gravado se agendados==0

    def test_optout_lgpd_bloqueia(self):
        lgpd.set_optout("1")
        n = pos_venda.register_sale_for_pos_venda(
            "1", "Ana", "ana@x.com", date.today()
        )
        self.assertEqual(n, 0)
        self.assertEqual(email_queue.queue_size(), 0)

    def test_template_usa_primeiro_nome(self):
        pos_venda.register_sale_for_pos_venda(
            "1", "Maria Clara Souza", "mc@x.com", date.today()
        )
        msgs = [i["mensagem"] for i in email_queue._load(email_queue.QUEUE)]
        self.assertTrue(all("Maria" in m for m in msgs))
        self.assertFalse(any("Clara" in m for m in msgs))

    def test_log_registra_chave_apos_sucesso(self):
        d = date.today()
        pos_venda.register_sale_for_pos_venda("42", "Ana", "ana@x.com", d)
        key = f"42_{d.strftime('%Y%m%d')}"
        self.assertIn(key, pos_venda._load_log())


class TestScanFromRetorno(_PosVendaIsolated):
    def _df(self, rows):
        import pandas as pd
        return pd.DataFrame(rows)

    def test_df_vazio(self):
        import pandas as pd
        self.assertEqual(
            pos_venda.scan_from_retorno(pd.DataFrame(), {}),
            {"novos": 0, "ja_registrados": 0},
        )

    def test_none_df(self):
        self.assertEqual(
            pos_venda.scan_from_retorno(None, {}),
            {"novos": 0, "ja_registrados": 0},
        )

    def test_cliente_com_email_recente_vira_novo(self):
        # data com dia>12 ("20/05") é parseada sem ambiguidade => recente => novo.
        df = self._df([{"codigo_cliente": "1", "ultima_compra": "20/05/2026"}])
        cmap = {"1": {"nome": "Ana", "email": "ana@x.com"}}
        r = pos_venda.scan_from_retorno(df, cmap)
        self.assertEqual(r["novos"], 1)

    def test_cliente_sem_email_conta_como_ja_reg(self):
        df = self._df([{"codigo_cliente": "1", "ultima_compra": "20/05/2026"}])
        cmap = {"1": {"nome": "Ana", "email": ""}}
        r = pos_venda.scan_from_retorno(df, cmap)
        self.assertEqual(r["novos"], 0)
        self.assertEqual(r["ja_registrados"], 1)

    def test_POSVENDA2_data_ambigua_dd_mm_parseada_corretamente(self):
        # POSVENDA-2 (CORRIGIDO em v1.8.1): scan_from_retorno agora usa
        # modules.dateutils.parse_br_date (dia-primeiro). Uma data brasileira
        # ambígua (dia<=12), ex. 02/06/2026 = 2 de junho 2026, é interpretada
        # como junho — dentro do cutoff de 90 dias → cliente recente entra na régua.
        df = self._df([{"codigo_cliente": "1", "ultima_compra": "02/06/2026"}])
        cmap = {"1": {"nome": "Ana", "email": "ana@x.com"}}
        r = pos_venda.scan_from_retorno(df, cmap)
        self.assertEqual(r["novos"], 1)

    def test_compra_antiga_ignorada(self):
        antiga = (date.today() - timedelta(days=200)).strftime("%d/%m/%Y")
        df = self._df([{"codigo_cliente": "1", "ultima_compra": antiga}])
        cmap = {"1": {"nome": "Ana", "email": "ana@x.com"}}
        r = pos_venda.scan_from_retorno(df, cmap)
        self.assertEqual(r, {"novos": 0, "ja_registrados": 0})


class TestScanAndRegister(_PosVendaIsolated):
    def test_df_vazio(self):
        import pandas as pd
        self.assertEqual(
            pos_venda.scan_and_register(pd.DataFrame(), {}),
            {"novos": 0, "ja_registrados": 0},
        )

    def test_none_df(self):
        self.assertEqual(
            pos_venda.scan_and_register(None, {}),
            {"novos": 0, "ja_registrados": 0},
        )


if __name__ == "__main__":
    unittest.main()
