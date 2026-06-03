"""
test_queue_gating.py — helper PURO de gating/dedupe da régua de pós-venda
(builder, iteração 23).

Por que existe
  modules/queue_gating.py é a peça que conserta DOIS bugs latentes da fila:
    * POSVENDA-1 — push_to_queue deduplica só por e-mail, então os 4 toques
      da régua (mesmo e-mail) viram "duplicados" e D+7/D+30/D+90 somem.
    * POSVENDA-3 — process_queue dispara a fila INTEIRA de uma vez; sem
      "enviar_em" os toques não respeitam a data prevista.
  Aqui testamos o helper E demonstramos, contra o email_queue REAL e isolado,
  que (a) o bug POSVENDA-1 existe hoje e (b) due_key/dedupe_new o resolve;
  e que partition_due dá o portão de data que o POSVENDA-3 precisa.

ESCOPO E SEGURANÇA
  100% ISOLADO — queue_gating é puro (sem I/O). Os testes de regressão que
  tocam email_queue redirecionam QUEUE/HISTORY para tempfiles e um guard de
  mtime confirma que os arquivos de produção NÃO são tocados. ZERO rede.
  Rodar:  venv\\Scripts\\python.exe -m pytest tests/test_queue_gating.py -q
"""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import queue_gating as qg  # noqa: E402
from modules import email_queue          # noqa: E402


def _tp(seg, dia, email="cliente@x.com", base=None):
    """Monta um toque da régua como a pos_venda faria, já com enviar_em."""
    base = base or date.today()
    return {
        "id": "C1", "nome": "Cliente", "email": email,
        "assunto": f"Toque {seg}", "mensagem": "m",
        "segmento": seg,
        qg.SEND_FIELD: qg.stamp_send_date(base, dia),
    }


# ---------------------------------------------------------------- due_key
class TestDueKey(unittest.TestCase):
    def test_email_normalizado(self):
        a = {"email": "  Ana@X.com ", "segmento": "s", qg.SEND_FIELD: "01/06/2026"}
        b = {"email": "ana@x.com", "segmento": "s", qg.SEND_FIELD: "01/06/2026"}
        self.assertEqual(qg.due_key(a), qg.due_key(b))

    def test_data_em_iso_para_ser_ordenavel(self):
        k = qg.due_key({"email": "a@x.com", "segmento": "s", qg.SEND_FIELD: "02/06/2026"})
        self.assertEqual(k[2], "2026-06-02")

    def test_toques_da_regua_tem_chaves_distintas(self):
        # MESMO e-mail, segmentos/datas diferentes -> chaves diferentes (anti POSVENDA-1)
        toques = [_tp("pos_venda_D+1", 1), _tp("pos_venda_D+7", 7),
                  _tp("pos_venda_D+30", 30), _tp("pos_venda_D+90", 90)]
        chaves = {qg.due_key(t) for t in toques}
        self.assertEqual(len(chaves), 4)

    def test_mesma_venda_rescaneada_colide(self):
        # re-scan da MESMA venda gera a MESMA chave -> continua deduplicado
        t1 = _tp("pos_venda_D+1", 1, base=date(2026, 6, 1))
        t2 = _tp("pos_venda_D+1", 1, base=date(2026, 6, 1))
        self.assertEqual(qg.due_key(t1), qg.due_key(t2))


# ---------------------------------------------------------------- dedupe_new
class TestDedupeNew(unittest.TestCase):
    def test_quatro_toques_sobrevivem(self):
        toques = [_tp("pos_venda_D+1", 1), _tp("pos_venda_D+7", 7),
                  _tp("pos_venda_D+30", 30), _tp("pos_venda_D+90", 90)]
        novos = qg.dedupe_new([], toques)
        self.assertEqual(len(novos), 4)

    def test_ignora_ja_existente(self):
        ex = [_tp("pos_venda_D+1", 1)]
        novos = qg.dedupe_new(ex, [_tp("pos_venda_D+1", 1), _tp("pos_venda_D+7", 7)])
        self.assertEqual(len(novos), 1)
        self.assertEqual(novos[0]["segmento"], "pos_venda_D+7")

    def test_dedupe_dentro_da_mesma_leva(self):
        novos = qg.dedupe_new([], [_tp("pos_venda_D+1", 1), _tp("pos_venda_D+1", 1)])
        self.assertEqual(len(novos), 1)

    def test_ignora_sem_email(self):
        novos = qg.dedupe_new([], [{"segmento": "s"}, {"email": "", "segmento": "s"}])
        self.assertEqual(novos, [])


# ---------------------------------------------------------------- is_due / partition
class TestGating(unittest.TestCase):
    def test_sem_campo_vence_agora(self):
        self.assertTrue(qg.is_due({"email": "a@x.com"}))

    def test_data_invalida_vence_agora(self):
        self.assertTrue(qg.is_due({qg.SEND_FIELD: "lixo"}))

    def test_passado_e_hoje_vencem(self):
        hoje = date(2026, 6, 2)
        self.assertTrue(qg.is_due({qg.SEND_FIELD: "01/06/2026"}, today=hoje))
        self.assertTrue(qg.is_due({qg.SEND_FIELD: "02/06/2026"}, today=hoje))

    def test_futuro_nao_vence(self):
        hoje = date(2026, 6, 2)
        self.assertFalse(qg.is_due({qg.SEND_FIELD: "03/06/2026"}, today=hoje))

    def test_partition_separa_corretamente(self):
        hoje = date(2026, 6, 2)
        fila = [
            {"segmento": "venceu", qg.SEND_FIELD: "01/06/2026", "email": "a@x.com"},
            {"segmento": "hoje",   qg.SEND_FIELD: "02/06/2026", "email": "b@x.com"},
            {"segmento": "futuro", qg.SEND_FIELD: "10/06/2026", "email": "c@x.com"},
            {"segmento": "legado", "email": "d@x.com"},  # sem campo -> vence
        ]
        venc, pend = qg.partition_due(fila, today=hoje)
        self.assertEqual({i["segmento"] for i in venc}, {"venceu", "hoje", "legado"})
        self.assertEqual({i["segmento"] for i in pend}, {"futuro"})


# ---------------------------------------------------------------- stamp_send_date
class TestStamp(unittest.TestCase):
    def test_offset_a_partir_de_date(self):
        self.assertEqual(qg.stamp_send_date(date(2026, 6, 1), 7), "08/06/2026")

    def test_offset_a_partir_de_texto_br(self):
        self.assertEqual(qg.stamp_send_date("01/06/2026", 30), "01/07/2026")

    def test_base_invalida(self):
        self.assertEqual(qg.stamp_send_date("lixo", 1), "")

    def test_toques_da_regua_geram_4_datas(self):
        base = date(2026, 6, 1)
        datas = [qg.stamp_send_date(base, d) for d in (1, 7, 30, 90)]
        self.assertEqual(datas, ["02/06/2026", "08/06/2026", "01/07/2026", "30/08/2026"])


# ------------------------------------------------ REGRESSÃO contra email_queue real
class _QueueIsolated(unittest.TestCase):
    """Isola QUEUE/HISTORY em tempfiles e garante que produção fica intacta."""
    @classmethod
    def setUpClass(cls):
        cls._prod = [email_queue.QUEUE, email_queue.HISTORY]
        cls._existia = {p: os.path.exists(p) for p in cls._prod}
        cls._mtime = {p: (os.path.getmtime(p) if cls._existia[p] else None)
                      for p in cls._prod}

    @classmethod
    def tearDownClass(cls):
        for p in cls._prod:
            if cls._existia[p]:
                assert os.path.getmtime(p) == cls._mtime[p], \
                    f"arquivo de produção {p} foi modificado pela suíte!"
            else:
                assert not os.path.exists(p), \
                    f"a suíte criou indevidamente {p}!"

    def setUp(self):
        self._orig = (email_queue.QUEUE, email_queue.HISTORY)
        self._tq = tempfile.NamedTemporaryFile(suffix=".json", delete=False); self._tq.close()
        self._th = tempfile.NamedTemporaryFile(suffix=".json", delete=False); self._th.close()
        os.unlink(self._tq.name); os.unlink(self._th.name)
        email_queue.QUEUE, email_queue.HISTORY = self._tq.name, self._th.name

    def tearDown(self):
        email_queue.QUEUE, email_queue.HISTORY = self._orig
        for p in (self._tq.name, self._th.name):
            if os.path.exists(p):
                os.unlink(p)


class TestRegressaoPosVenda1(_QueueIsolated):
    def test_bug_vivo_push_descarta_3_dos_4_toques(self):
        """DEMONSTRA POSVENDA-1: push_to_queue (dedupe só por e-mail) mantém só 1
        dos 4 toques de mesmo e-mail. Vira VERMELHO quando o fix entrar."""
        toques = [_tp("pos_venda_D+1", 1), _tp("pos_venda_D+7", 7),
                  _tp("pos_venda_D+30", 30), _tp("pos_venda_D+90", 90)]
        n = email_queue.push_to_queue(toques)
        self.assertEqual(n, 1)                         # bug atual: só 1 entra
        self.assertEqual(email_queue.queue_size(), 1)

    def test_fix_dedupe_new_mantem_os_4(self):
        """PROVA do FIX: usando qg.dedupe_new como identidade, os 4 sobrevivem."""
        toques = [_tp("pos_venda_D+1", 1), _tp("pos_venda_D+7", 7),
                  _tp("pos_venda_D+30", 30), _tp("pos_venda_D+90", 90)]
        existentes = email_queue._load(email_queue.QUEUE)
        a_inserir = qg.dedupe_new(existentes, toques)
        self.assertEqual(len(a_inserir), 4)


class TestRegressaoPosVenda3(_QueueIsolated):
    def test_partition_segura_os_futuros(self):
        """O portão que process_queue precisa: só os vencidos sairiam hoje."""
        base = date.today()
        fila = [_tp("pos_venda_D+1", 1, base=base),    # vence amanhã -> futuro
                _tp("pos_venda_D+7", 7, base=base)]
        # com base hoje, D+1 e D+7 são futuros -> nenhum vence hoje
        venc, pend = qg.partition_due(fila)
        self.assertEqual(venc, [])
        self.assertEqual(len(pend), 2)


if __name__ == "__main__":
    unittest.main()
