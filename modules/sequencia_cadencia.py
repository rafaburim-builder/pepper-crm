"""
sequencia_cadencia.py — peças PURAS para a SEQUÊNCIA multi-toque de relacionamento.

Motivo de existir
-----------------
modules/cadencia.py já resolve "qual é a PRÓXIMA ação para este cliente" (um único
toque por segmento — o "Next Best Action" do Salesforce). Mas os CRMs consolidados
não param em UM toque: eles definem uma SEQUÊNCIA datada de vários toques que avança
sozinha até o cliente responder:

  * Microsoft Dynamics "Sequences" — fila de atividades por estágio (passo 2 de 4).
  * RD Station "Cadência"          — WhatsApp D+0 → Ligação D+3 → E-mail D+7…
  * Salesforce "Cadences/Sales Engagement" — steps com canal, prazo e parada na
    resposta do cliente ("stop-on-reply").

Este módulo é exatamente esse motor de sequência, em cima da política de segmentos
que cadencia.py já tem: para cada segmento RFM define uma TRILHA ordenada de toques
(canal + D+N + ação + script), calcula em que passo cada cliente está, qual é o
PRÓXIMO toque devido (e a data dele) e — a regra de ouro — ENCERRA a sequência assim
que o cliente responde/converte, para não seguir cutucando quem já reagiu.

Importante: módulo PURO — sem I/O, sem rede, sem estado global, sem pandas, sem
relógio interno (a data "today" é sempre injetada). NÃO é importado pelo app; é uma
peça pronta para ligar quando o app estiver parado (instruções de fiação no relatório
noturno). Reusa modules.cadencia (política/​script do D+0) e modules.dateutils.

Entrada esperada (cada "row" é um dict, o formato que rfm.score_rfm já produz):
    codigo_cliente, nome, fone, segmento  (+ os demais campos do RFM)
  campos OPCIONAIS lidos por este módulo:
    sequencia_inicio ("DD/MM/AAAA") — quando a sequência começou; default = today
    toques_feitos    (int)         — quantos passos já foram executados; default 0
    respondeu        (bool)        — o cliente respondeu/converteu? (stop-on-reply)
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Optional

from . import cadencia as cad
from . import dateutils as du

# Campos opcionais lidos da row.
START_FIELD = "sequencia_inicio"
DONE_FIELD = "toques_feitos"
REPLIED_FIELD = "respondeu"

# Resultados de toque que contam como "o cliente reagiu" → para a sequência.
REPLY_RESULTS = {
    "respondeu", "respondido", "converteu", "convertido", "venda", "vendeu",
    "agendou", "agendado", "compareceu", "fechou", "fechado", "interessado",
}

_LOJA_DEFAULT = "Chilli Beans"


# ── Trilhas de toque por segmento ─────────────────────────────────────────────
# Cada passo: dia_offset (D+N a partir do início), canal, ação e um script.
# O 1º passo (D+0) reusa o canal/script que cadencia.py já define para o segmento
# (script=None abaixo → preenchido por cadencia.script_for), mantendo coerência com
# o painel de cadência. Os toques seguintes (follow-ups) são definidos aqui. A trilha
# é mais agressiva (mais toques, prazos curtos) para win-back e mais leve para
# clientes saudáveis — mesma lógica de prioridade da política de cadência.
_SEQUENCES = {
    "⚠️ Em Risco": [
        {"dia_offset": 0, "canal": "WhatsApp", "acao": "1º toque — reativar",
         "script": None},
        {"dia_offset": 3, "canal": "Ligação", "acao": "2º toque — ligar se não respondeu",
         "script": ("Oi {nome}, é a {loja}! Te mandei mensagem há uns dias sobre uma "
                    "condição pra renovar suas lentes/armação. Consegue falar 2 minutinhos?")},
        {"dia_offset": 7, "canal": "WhatsApp", "acao": "3º toque — oferta final",
         "script": ("{nome}, última chamada 😊 A condição especial pra sua troca vai até "
                    "o fim da semana. Quer que eu já separe pra você não perder?")},
    ],
    "🌙 Hibernando": [
        {"dia_offset": 0, "canal": "WhatsApp", "acao": "1º toque — resgate",
         "script": None},
        {"dia_offset": 5, "canal": "Ligação", "acao": "2º toque — ligar com novidade",
         "script": ("Oi {nome}, aqui é da {loja}! Chegou coleção nova e lembrei de você. "
                    "Tem um minutinho pra eu te contar o que separei?")},
        {"dia_offset": 12, "canal": "E-mail", "acao": "3º toque — mimo de boas-vindas",
         "script": ("{nome}, preparamos um mimo de boas-vindas de volta na {loja}. "
                    "Passa aqui pra resgatar quando quiser!")},
    ],
    "❄️ Perdidos": [
        {"dia_offset": 0, "canal": "Ligação", "acao": "1º toque — win-back",
         "script": None},
        {"dia_offset": 7, "canal": "WhatsApp", "acao": "2º toque — convite de retorno",
         "script": ("Oi {nome}! É a {loja}. Faz tempo que não te vemos — temos uma "
                    "condição exclusiva de retorno te esperando. Topa dar uma passada?")},
        {"dia_offset": 21, "canal": "E-mail", "acao": "3º toque — última tentativa",
         "script": ("{nome}, deixamos a porta aberta na {loja} 💙 Sua condição de retorno "
                    "ainda está de pé. Esperamos te ver em breve!")},
    ],
    "🌱 Potenciais Fiéis": [
        {"dia_offset": 0, "canal": "WhatsApp", "acao": "1º toque — nutrir 2ª compra",
         "script": None},
        {"dia_offset": 10, "canal": "WhatsApp", "acao": "2º toque — combo grau+solar",
         "script": ("Oi {nome}! Quem fecha grau + solar na {loja} leva uma condição "
                    "especial. Quer ver as combinações com a sua cara?")},
    ],
    "💎 Fiéis": [
        {"dia_offset": 0, "canal": "WhatsApp", "acao": "1º toque — relacionamento",
         "script": None},
        {"dia_offset": 30, "canal": "Ligação", "acao": "2º toque — indicação/upsell",
         "script": ("Oi {nome}! Você é cliente especial da {loja} 💎 Se trouxer um amigo, "
                    "vocês dois ganham um bônus. Quando posso te receber?")},
    ],
    "🏆 Campeões": [
        {"dia_offset": 0, "canal": "Ligação", "acao": "1º toque — VIP premium",
         "script": None},
        {"dia_offset": 30, "canal": "WhatsApp", "acao": "2º toque — pré-lançamento VIP",
         "script": ("{nome}, como cliente VIP da {loja} 🏆 quis te avisar em primeira mão: "
                    "chegou a coleção premium. Quer dar uma olhada antes de todo mundo?")},
    ],
    "👤 Regular": [
        {"dia_offset": 0, "canal": "E-mail", "acao": "1º toque — manutenção",
         "script": None},
        {"dia_offset": 30, "canal": "E-mail", "acao": "2º toque — lembrete de visita",
         "script": ("Oi {nome}, é a {loja}! Estamos por aqui pra revisão de grau, ajuste "
                    "de armação ou só renovar o visual. Aparece pra gente! 😎")},
    ],
}

# Ordem de processamento herdada da política de cadência (mais urgente primeiro).
SEGMENT_SEQUENCE_ORDER = [s for s in cad.SEGMENT_CADENCE_ORDER if s in _SEQUENCES]

# Estados possíveis de uma sequência.
EM_ANDAMENTO = "em_andamento"
RESPONDEU = "respondeu"
CONCLUIDA = "concluida"

# Status possíveis de um passo individual.
FEITO = "feito"
HOJE = "hoje"
ATRASADO = "atrasado"
AGENDADO = "agendado"
ENCERRADO_RESPOSTA = "encerrado_resposta"


def sequence_for(segmento: str) -> list:
    """Devolve a trilha (lista de passos) do segmento, ou [] se desconhecido."""
    return list(_SEQUENCES.get(str(segmento), []))


def has_sequence(segmento: str) -> bool:
    return str(segmento) in _SEQUENCES


def _add_days(d: date, n: int) -> date:
    return d + timedelta(days=n)


def _step_script(segmento: str, step: dict, nome: str, loja: str) -> str:
    """Script do passo: o D+0 reusa cadencia.script_for; os demais usam o template."""
    raw = step.get("script")
    if raw is None:
        return cad.script_for(segmento, nome, loja)
    nome_fmt = (str(nome).strip().split()[0] if str(nome).strip() else "tudo bem")
    loja_fmt = str(loja).strip() or _LOJA_DEFAULT
    return raw.format(nome=nome_fmt, loja=loja_fmt)


def _is_reply(value) -> bool:
    """Interpreta o sinal de resposta: bool direto ou string de resultado conhecida."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    return str(value).strip().lower() in REPLY_RESULTS


def replied_from_touches(touches: Iterable[dict]) -> bool:
    """True se algum toque na lista indica que o cliente reagiu (stop-on-reply)."""
    for t in touches or []:
        if _is_reply(t.get("resultado", "")) or _is_reply(t.get("respondeu", False)):
            return True
    return False


def count_done_steps(
    touches: Iterable[dict],
    inicio: Optional[date] = None,
    segmento: str = "",
) -> int:
    """
    Conveniência: deriva quantos passos já foram executados a partir de uma lista de
    toques registrados (cada um com 'data' "DD/MM/AAAA"). Conta toques cuja data é
    >= o início da sequência, com teto no número de passos da trilha. É uma estimativa
    por VOLUME (não casa canal a canal) — o suficiente para posicionar o cliente na
    trilha; quem quiser precisão pode passar toques_feitos explicitamente na row.
    """
    n_passos = len(_SEQUENCES.get(str(segmento), [])) if segmento else 10 ** 9
    feitos = 0
    for t in touches or []:
        d = du.parse_br_date(t.get("data", ""))
        if d is None:
            continue
        if inicio is None or d >= inicio:
            feitos += 1
    return min(feitos, n_passos)


def build_sequence(
    row: dict,
    today: Optional[date] = None,
    loja: str = "",
    touches: Optional[Iterable[dict]] = None,
) -> Optional[dict]:
    """
    Monta o estado completo da sequência multi-toque de UM cliente, ou None se o
    segmento não tem trilha definida.

    Resolve, nesta ordem de preferência:
      * início  ← row[sequencia_inicio] (DD/MM/AAAA); senão `today`.
      * respondeu ← row[respondeu] OU qualquer toque de `touches` com resultado de
                    resposta (stop-on-reply).
      * toques_feitos ← row[toques_feitos] (int) OU derivado de `touches`.

    Retorna:
        {
          codigo_cliente, nome, fone, segmento, loja,
          inicio ("DD/MM/AAAA"),
          estado: em_andamento | respondeu | concluida,
          total_passos, passos_feitos,
          passos: [ {ordem, canal, acao, vencimento, status, script}, ... ],
          proxima_acao: {ordem, canal, acao, vencimento, status, script} | None,
        }
    """
    today = today or date.today()
    segmento = str(row.get("segmento", ""))
    trilha = _SEQUENCES.get(segmento)
    if not trilha:
        return None

    touches = list(touches or [])
    nome = str(row.get("nome", "")).strip()
    loja = str(loja).strip() or _LOJA_DEFAULT

    inicio = du.parse_br_date(row.get(START_FIELD, "")) or today

    if REPLIED_FIELD in row:
        respondeu = _is_reply(row.get(REPLIED_FIELD))
    else:
        respondeu = replied_from_touches(touches)

    if DONE_FIELD in row:
        try:
            feitos = max(0, int(row.get(DONE_FIELD) or 0))
        except (TypeError, ValueError):
            feitos = 0
    else:
        feitos = count_done_steps(touches, inicio=inicio, segmento=segmento)
    feitos = min(feitos, len(trilha))

    passos = []
    proxima = None
    for i, step in enumerate(trilha):
        venc = _add_days(inicio, int(step["dia_offset"]))
        if i < feitos:
            status = FEITO
        elif respondeu:
            status = ENCERRADO_RESPOSTA
        elif i == feitos:
            if venc < today:
                status = ATRASADO
            elif venc == today:
                status = HOJE
            else:
                status = AGENDADO
        else:
            status = AGENDADO
        item = {
            "ordem": i + 1,
            "canal": step["canal"],
            "acao": step["acao"],
            "vencimento": du.to_br(venc),
            "status": status,
            "script": _step_script(segmento, step, nome, loja),
        }
        passos.append(item)
        if proxima is None and status in (ATRASADO, HOJE, AGENDADO):
            proxima = item

    if respondeu:
        estado = RESPONDEU
    elif feitos >= len(trilha):
        estado = CONCLUIDA
    else:
        estado = EM_ANDAMENTO

    return {
        "codigo_cliente": row.get("codigo_cliente"),
        "nome": nome,
        "fone": str(row.get("fone", "")).strip(),
        "segmento": segmento,
        "loja": loja,
        "inicio": du.to_br(inicio),
        "estado": estado,
        "total_passos": len(trilha),
        "passos_feitos": feitos,
        "passos": passos,
        "proxima_acao": proxima,
    }


def next_step(
    row: dict,
    today: Optional[date] = None,
    loja: str = "",
    touches: Optional[Iterable[dict]] = None,
) -> Optional[dict]:
    """O próximo toque devido do cliente (dict do passo), ou None se encerrada/concluída."""
    seq = build_sequence(row, today=today, loja=loja, touches=touches)
    return seq["proxima_acao"] if seq else None


def advance_sequences(
    rows: Iterable[dict],
    today: Optional[date] = None,
    loja: str = "",
    only_due: bool = False,
) -> list:
    """
    Roda build_sequence para todas as linhas (descartando segmentos sem trilha) e
    devolve a lista ordenada pela urgência do PRÓXIMO toque: atrasados primeiro, depois
    os de hoje, depois agendados; sequências sem próximo toque (respondeu/concluída) vão
    para o fim. Empate desfeito pela ordem de prioridade do segmento.

    only_due=True: mantém só as sequências com um toque atrasado ou para hoje (a fila
    de trabalho do dia).
    """
    today = today or date.today()
    seqs = []
    for row in rows:
        s = build_sequence(row, today=today, loja=loja)
        if s is None:
            continue
        if only_due:
            prox = s.get("proxima_acao")
            if not prox or prox["status"] not in (ATRASADO, HOJE):
                continue
        seqs.append(s)

    rank_status = {ATRASADO: 0, HOJE: 1, AGENDADO: 2}
    seg_order = {seg: i for i, seg in enumerate(SEGMENT_SEQUENCE_ORDER)}

    def _key(s: dict) -> tuple:
        prox = s.get("proxima_acao")
        if prox is None:
            return (9, "9999-99-99", seg_order.get(s.get("segmento"), 99))
        venc_iso = du.to_iso(prox.get("vencimento", "")) or "9999-99-99"
        return (rank_status.get(prox["status"], 8), venc_iso,
                seg_order.get(s.get("segmento"), 99))

    seqs.sort(key=_key)
    return seqs


def sequence_summary(seqs: Iterable[dict]) -> dict:
    """
    Resumo para o cabeçalho do painel:
        {
          "total": n,
          "por_estado": {em_andamento, respondeu, concluida},
          "proximos_por_status": {atrasado, hoje, agendado},
          "atrasados": n,   # atalho prático
        }
    """
    seqs = list(seqs)
    por_estado: dict = {}
    por_status: dict = {}
    for s in seqs:
        est = s.get("estado", "?")
        por_estado[est] = por_estado.get(est, 0) + 1
        prox = s.get("proxima_acao")
        if prox:
            st = prox.get("status", "?")
            por_status[st] = por_status.get(st, 0) + 1
    return {
        "total": len(seqs),
        "por_estado": por_estado,
        "proximos_por_status": por_status,
        "atrasados": por_status.get(ATRASADO, 0),
    }
