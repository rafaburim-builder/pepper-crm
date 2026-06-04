"""
test_sequencia_cadencia.py — contrato do motor de SEQUÊNCIA multi-toque (builder, iter 33).

Por que existe:
  modules/sequencia_cadencia.py é a generalização de cadencia.py: de "um próximo
  toque" para a TRILHA datada de vários toques (Dynamics Sequences / RD Cadência),
  com a regra de ouro stop-on-reply. Por ser peça pura e determinística (a data é
  injetada), trava aqui o cálculo de passos, datas, status e encerramento.

Escrito como unittest.TestCase para rodar tanto no unittest discover (Rodar_Testes.bat)
quanto no pytest.
"""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import sequencia_cadencia as seq  # noqa: E402


HOJE = date(2026, 6, 4)


def _row(segmento="⚠️ Em Risco", **extra):
    base = {"codigo_cliente": 1, "nome": "Maria Souza", "fone": "11999",
            "segmento": segmento}
    base.update(extra)
    return base


class TestTrilhas(unittest.TestCase):
    def test_sequence_for_conhecido_nao_vazio(self):
        for s in seq.SEGMENT_SEQUENCE_ORDER:
            self.assertTrue(seq.sequence_for(s), f"trilha vazia: {s}")

    def test_sequence_for_desconhecido_vazio(self):
        self.assertEqual(seq.sequence_for("inexistente"), [])
        self.assertFalse(seq.has_sequence("inexistente"))

    def test_primeiro_passo_sempre_d0(self):
        for s in seq.SEGMENT_SEQUENCE_ORDER:
            self.assertEqual(seq.sequence_for(s)[0]["dia_offset"], 0)

    def test_offsets_sao_crescentes(self):
        for s in seq.SEGMENT_SEQUENCE_ORDER:
            offs = [p["dia_offset"] for p in seq.sequence_for(s)]
            self.assertEqual(offs, sorted(offs))

    def test_ordem_de_segmentos_herda_cadencia(self):
        # win-back (Em Risco) vem antes de Regular na ordem de processamento
        self.assertLess(
            seq.SEGMENT_SEQUENCE_ORDER.index("⚠️ Em Risco"),
            seq.SEGMENT_SEQUENCE_ORDER.index("👤 Regular"),
        )


class TestBuildSequence(unittest.TestCase):
    def test_segmento_sem_trilha_retorna_none(self):
        self.assertIsNone(seq.build_sequence(_row(segmento="??"), today=HOJE))

    def test_inicio_default_eh_today(self):
        s = seq.build_sequence(_row(), today=HOJE)
        self.assertEqual(s["inicio"], "04/06/2026")

    def test_datas_dos_passos_sao_inicio_mais_offset(self):
        s = seq.build_sequence(_row(), today=HOJE)
        # Em Risco: D+0, D+3, D+7
        venc = [p["vencimento"] for p in s["passos"]]
        self.assertEqual(venc, ["04/06/2026", "07/06/2026", "11/06/2026"])

    def test_primeiro_passo_hoje_quando_inicio_hoje(self):
        s = seq.build_sequence(_row(), today=HOJE)
        self.assertEqual(s["passos"][0]["status"], seq.HOJE)
        self.assertEqual(s["proxima_acao"]["ordem"], 1)
        self.assertEqual(s["estado"], seq.EM_ANDAMENTO)

    def test_passos_feitos_avancam_o_ponteiro(self):
        s = seq.build_sequence(_row(toques_feitos=1), today=HOJE)
        self.assertEqual(s["passos"][0]["status"], seq.FEITO)
        self.assertEqual(s["passos_feitos"], 1)
        self.assertEqual(s["proxima_acao"]["ordem"], 2)

    def test_proximo_passo_futuro_eh_agendado(self):
        # já fiz o D+0; o D+3 ainda não venceu em HOJE
        s = seq.build_sequence(_row(toques_feitos=1), today=HOJE)
        self.assertEqual(s["proxima_acao"]["status"], seq.AGENDADO)

    def test_proximo_passo_vencido_eh_atrasado(self):
        # início 10 dias atrás, 1 feito → D+3 (3 dias após início) já passou
        s = seq.build_sequence(
            _row(sequencia_inicio="25/05/2026", toques_feitos=1), today=HOJE)
        self.assertEqual(s["proxima_acao"]["status"], seq.ATRASADO)

    def test_respondeu_encerra_sequencia(self):
        s = seq.build_sequence(_row(respondeu=True), today=HOJE)
        self.assertEqual(s["estado"], seq.RESPONDEU)
        self.assertIsNone(s["proxima_acao"])
        for p in s["passos"]:
            self.assertEqual(p["status"], seq.ENCERRADO_RESPOSTA)

    def test_todos_feitos_marca_concluida(self):
        s = seq.build_sequence(_row(toques_feitos=3), today=HOJE)
        self.assertEqual(s["estado"], seq.CONCLUIDA)
        self.assertIsNone(s["proxima_acao"])
        self.assertTrue(all(p["status"] == seq.FEITO for p in s["passos"]))

    def test_toques_feitos_saturam_no_total(self):
        s = seq.build_sequence(_row(toques_feitos=99), today=HOJE)
        self.assertEqual(s["passos_feitos"], s["total_passos"])

    def test_script_d0_reusa_cadencia(self):
        from modules import cadencia as cad
        s = seq.build_sequence(_row(), today=HOJE, loja="Loja X")
        esperado = cad.script_for("⚠️ Em Risco", "Maria Souza", "Loja X")
        self.assertEqual(s["passos"][0]["script"], esperado)

    def test_script_followup_preenche_nome_e_loja(self):
        s = seq.build_sequence(_row(), today=HOJE, loja="Loja X")
        sc = s["passos"][1]["script"]
        self.assertIn("Maria", sc)       # primeiro nome
        self.assertIn("Loja X", sc)
        self.assertNotIn("{nome}", sc)
        self.assertNotIn("{loja}", sc)


class TestStopOnReplyPorToques(unittest.TestCase):
    def test_toque_com_resultado_resposta_encerra(self):
        toques = [{"data": "04/06/2026", "canal": "WhatsApp", "resultado": "respondeu"}]
        s = seq.build_sequence(_row(), today=HOJE, touches=toques)
        self.assertEqual(s["estado"], seq.RESPONDEU)

    def test_toque_sem_resposta_nao_encerra(self):
        toques = [{"data": "04/06/2026", "canal": "WhatsApp", "resultado": "sem_resposta"}]
        s = seq.build_sequence(_row(), today=HOJE, touches=toques)
        self.assertNotEqual(s["estado"], seq.RESPONDEU)
        # mas conta como 1 passo executado
        self.assertEqual(s["passos_feitos"], 1)

    def test_row_respondeu_tem_prioridade_sobre_touches(self):
        toques = [{"data": "04/06/2026", "resultado": "respondeu"}]
        s = seq.build_sequence(_row(respondeu=False), today=HOJE, touches=toques)
        self.assertNotEqual(s["estado"], seq.RESPONDEU)

    def test_replied_from_touches_helper(self):
        self.assertTrue(seq.replied_from_touches([{"resultado": "converteu"}]))
        self.assertFalse(seq.replied_from_touches([{"resultado": "nada"}]))
        self.assertTrue(seq.replied_from_touches([{"respondeu": True}]))

    def test_count_done_steps_satura_e_filtra_por_inicio(self):
        toques = [
            {"data": "01/06/2026"},          # antes do início → não conta
            {"data": "04/06/2026"},
            {"data": "05/06/2026"},
            {"data": "06/06/2026"},
            {"data": "07/06/2026"},          # 4 válidos, trilha tem 3 → satura em 3
        ]
        n = seq.count_done_steps(toques, inicio=date(2026, 6, 4), segmento="⚠️ Em Risco")
        self.assertEqual(n, 3)


class TestAdvanceSequences(unittest.TestCase):
    def _rows(self):
        return [
            _row(codigo_cliente=1, segmento="⚠️ Em Risco",
                 sequencia_inicio="25/05/2026", toques_feitos=1),       # atrasado
            _row(codigo_cliente=2, segmento="💎 Fiéis"),                 # hoje (D+0)
            _row(codigo_cliente=3, segmento="🌱 Potenciais Fiéis",
                 toques_feitos=1),                                       # agendado (D+10)
            _row(codigo_cliente=4, segmento="🏆 Campeões", respondeu=True),  # encerrada
            _row(codigo_cliente=5, segmento="??"),                       # sem trilha → fora
        ]

    def test_descarta_sem_trilha(self):
        out = seq.advance_sequences(self._rows(), today=HOJE)
        self.assertEqual(len(out), 4)
        self.assertNotIn(5, [s["codigo_cliente"] for s in out])

    def test_ordena_atrasado_antes_de_hoje_antes_de_agendado(self):
        out = seq.advance_sequences(self._rows(), today=HOJE)
        codigos = [s["codigo_cliente"] for s in out]
        self.assertEqual(codigos[0], 1)        # atrasado primeiro
        self.assertEqual(codigos[1], 2)        # hoje
        self.assertEqual(codigos[2], 3)        # agendado
        self.assertEqual(codigos[3], 4)        # respondeu (sem próximo) por último

    def test_only_due_mantem_so_atrasado_e_hoje(self):
        out = seq.advance_sequences(self._rows(), today=HOJE, only_due=True)
        codigos = sorted(s["codigo_cliente"] for s in out)
        self.assertEqual(codigos, [1, 2])

    def test_next_step_atalho(self):
        ns = seq.next_step(_row(), today=HOJE)
        self.assertEqual(ns["ordem"], 1)
        self.assertIsNone(seq.next_step(_row(respondeu=True), today=HOJE))


class TestSummary(unittest.TestCase):
    def test_summary_conta_estados_e_status(self):
        rows = [
            _row(codigo_cliente=1, segmento="⚠️ Em Risco",
                 sequencia_inicio="25/05/2026", toques_feitos=1),   # atrasado / em_andamento
            _row(codigo_cliente=2, segmento="💎 Fiéis"),             # hoje / em_andamento
            _row(codigo_cliente=3, segmento="🏆 Campeões", respondeu=True),  # respondeu
            _row(codigo_cliente=4, segmento="🌙 Hibernando", toques_feitos=3),  # concluida
        ]
        seqs = seq.advance_sequences(rows, today=HOJE)
        resumo = seq.sequence_summary(seqs)
        self.assertEqual(resumo["total"], 4)
        self.assertEqual(resumo["por_estado"][seq.EM_ANDAMENTO], 2)
        self.assertEqual(resumo["por_estado"][seq.RESPONDEU], 1)
        self.assertEqual(resumo["por_estado"][seq.CONCLUIDA], 1)
        self.assertEqual(resumo["atrasados"], 1)
        self.assertEqual(resumo["proximos_por_status"].get(seq.HOJE), 1)


if __name__ == "__main__":
    unittest.main()
