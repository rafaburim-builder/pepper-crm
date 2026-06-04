"""
cadencia.py — peças PURAS para a CADÊNCIA de relacionamento (próxima ação por cliente).

Motivo de existir
-----------------
Hoje o Pepper já segmenta os clientes por RFM (modules/rfm.py: 🏆 Campeões,
💎 Fiéis, 🌱 Potenciais Fiéis, ⚠️ Em Risco, 🌙 Hibernando, ❄️ Perdidos, 👤 Regular),
mas PARA aí: o vendedor vê o segmento e precisa decidir sozinho "e agora, o que
eu faço com esse cliente?". É exatamente o passo que os CRMs consolidados
automatizam:

  * Salesforce "Next Best Action"  — para cada conta, a próxima ação recomendada.
  * RD Station "Cadência"          — sequência de toques com canal + prazo + script.
  * Microsoft Dynamics "Sequences" — fila de atividades datadas por estágio.

Este módulo transforma a saída do RFM em uma LISTA DE TAREFAS acionáveis, cada uma
com: o que fazer (ação), por qual canal, até quando (vencimento), por quê (motivo)
e um SCRIPT de abordagem pronto por segmento — a peça que a home "MEU DIA" (UX-1) e
o painel de Cadência (COM-1) vão consumir.

Importante: módulo PURO — sem I/O, sem rede, sem estado global, sem pandas. NÃO é
importado pelo app; é uma peça pronta para ligar quando o app estiver parado. As
instruções de fiação estão no relatório noturno. Reusa modules.dateutils para
qualquer manipulação de data (mesma classe dos bugs já corrigidos).

Entrada esperada (cada "row" é um dict, o formato que rfm.score_rfm já produz):
    codigo_cliente, nome, fone, segmento, R_dias  (e os demais campos do RFM)
    + opcional: ultimo_toque ("DD/MM/AAAA") — data do último contato registrado,
      usada para o COOLDOWN (não incomodar quem já foi contatado há pouco).
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from . import dateutils as du

# Campo opcional na row com a data do último contato (texto "DD/MM/AAAA").
LAST_TOUCH_FIELD = "ultimo_toque"

# Placeholder de loja quando o chamador não informar o nome.
_LOJA_DEFAULT = "Chilli Beans"


# ── Política de cadência por segmento ─────────────────────────────────────────
# Para cada segmento RFM: prioridade (1 = age primeiro), a ação, o canal sugerido,
# em quantos dias a tarefa vence (prazo_dias), o cooldown (não recontatar antes de
# N dias) e o motivo/script. Espelha a lógica "Next Best Action" dos CRMs: clientes
# escorregando (Em Risco/Hibernando) têm prioridade e prazo curto; clientes saudáveis
# (Campeões/Fiéis) viram relacionamento/upsell com prazo folgado.
_CADENCE_POLICY = {
    "⚠️ Em Risco": {
        "prioridade": 1, "canal": "WhatsApp", "prazo_dias": 0, "cooldown_dias": 30,
        "acao": "Reativar agora — cliente bom esfriando",
        "script": ("Oi {nome}! Aqui é da {loja} 😎 Faz um tempinho que a gente não "
                   "se vê. Suas lentes/armação já passaram do tempo ideal de troca? "
                   "Separei uma condição especial pra você dar uma renovada. Posso te "
                   "mostrar?"),
    },
    "🌙 Hibernando": {
        "prioridade": 2, "canal": "WhatsApp", "prazo_dias": 1, "cooldown_dias": 45,
        "acao": "Resgatar — sem comprar há tempo",
        "script": ("Oi {nome}, tudo bem? É a {loja}! Sentimos sua falta por aqui. "
                   "Chegou coleção nova e estamos com um mimo de boas-vindas de volta. "
                   "Quer que eu separe algumas opções com a sua cara?"),
    },
    "❄️ Perdidos": {
        "prioridade": 3, "canal": "Ligação", "prazo_dias": 2, "cooldown_dias": 90,
        "acao": "Última tentativa de win-back",
        "script": ("Olá {nome}, aqui é da {loja}. Faz bastante tempo desde a sua "
                   "última visita e queria te fazer um convite especial pra voltar — "
                   "com uma condição exclusiva de retorno. Tem 2 minutinhos?"),
    },
    "🌱 Potenciais Fiéis": {
        "prioridade": 4, "canal": "WhatsApp", "prazo_dias": 3, "cooldown_dias": 30,
        "acao": "Nutrir para a 2ª compra",
        "script": ("Oi {nome}! Curtiu sua última compra na {loja}? 😍 Quem combina "
                   "óculos de grau + um solar leva uma condição especial. Quer ver as "
                   "novidades que têm tudo a ver com o seu estilo?"),
    },
    "💎 Fiéis": {
        "prioridade": 5, "canal": "WhatsApp", "prazo_dias": 7, "cooldown_dias": 45,
        "acao": "Relacionamento + pedir indicação",
        "script": ("Oi {nome}! Você é cliente especial da {loja} 💎 Acabou de chegar "
                   "lançamento e quis te avisar em primeira mão. E se trouxer um amigo, "
                   "vocês dois ganham um bônus. Bora dar uma passada?"),
    },
    "🏆 Campeões": {
        "prioridade": 6, "canal": "Ligação", "prazo_dias": 7, "cooldown_dias": 45,
        "acao": "VIP — upsell premium e fidelização",
        "script": ("Olá {nome}! Aqui é da {loja} 🏆 Você é um dos nossos clientes "
                   "VIP e separei um atendimento exclusivo das peças premium da nova "
                   "coleção, antes de todo mundo. Quando posso te receber?"),
    },
    "👤 Regular": {
        "prioridade": 7, "canal": "E-mail", "prazo_dias": 14, "cooldown_dias": 30,
        "acao": "Manutenção de relacionamento",
        "script": ("Oi {nome}, é a {loja}! Passando pra lembrar que estamos por aqui "
                   "pro que você precisar — revisão de grau, ajuste de armação ou só "
                   "dar aquela renovada no visual. Aparece pra gente! 😎"),
    },
}

# Ordem de exibição/processamento (menor prioridade primeiro).
SEGMENT_CADENCE_ORDER = sorted(_CADENCE_POLICY, key=lambda s: _CADENCE_POLICY[s]["prioridade"])


def policy_for(segmento: str) -> Optional[dict]:
    """Devolve a política de cadência do segmento, ou None se desconhecido."""
    return _CADENCE_POLICY.get(segmento)


def script_for(segmento: str, nome: str = "", loja: str = "") -> str:
    """
    Monta o script de abordagem do segmento com {nome} e {loja} preenchidos.
    Segmento desconhecido -> "".
    """
    pol = _CADENCE_POLICY.get(segmento)
    if pol is None:
        return ""
    nome = (str(nome).strip() or "tudo bem").split()[0] if str(nome).strip() else "tudo bem"
    loja = str(loja).strip() or _LOJA_DEFAULT
    return pol["script"].format(nome=nome, loja=loja)


def _in_cooldown(row: dict, segmento: str, today: date) -> bool:
    """
    True se o cliente já foi contatado há MENOS de cooldown_dias (não recontatar).
    Sem 'ultimo_toque' (ou data inválida) -> nunca está em cooldown (libera a tarefa).
    """
    pol = _CADENCE_POLICY.get(segmento)
    if pol is None:
        return False
    raw = row.get(LAST_TOUCH_FIELD, "")
    last = du.parse_br_date(raw)
    if last is None:
        return False
    dias = (today - last).days
    return 0 <= dias < int(pol["cooldown_dias"])


def build_task(row: dict, today: Optional[date] = None, loja: str = "") -> Optional[dict]:
    """
    Converte uma linha RFM em UMA tarefa de cadência (dict), ou None se o cliente
    não deve gerar tarefa agora (segmento desconhecido ou em cooldown).

    A tarefa traz tudo que a UI precisa para um cartão acionável:
        codigo_cliente, nome, fone, segmento, prioridade, acao, canal,
        vencimento ("DD/MM/AAAA"), motivo, script
    """
    today = today or date.today()
    segmento = str(row.get("segmento", ""))
    pol = _CADENCE_POLICY.get(segmento)
    if pol is None:
        return None
    if _in_cooldown(row, segmento, today):
        return None

    nome = str(row.get("nome", "")).strip()
    r_dias = row.get("R_dias")
    if isinstance(r_dias, (int, float)) and r_dias >= 0:
        motivo = f"Última compra há {int(r_dias)} dias"
    else:
        motivo = pol["acao"]

    return {
        "codigo_cliente": row.get("codigo_cliente"),
        "nome": nome,
        "fone": str(row.get("fone", "")).strip(),
        "segmento": segmento,
        "prioridade": pol["prioridade"],
        "acao": pol["acao"],
        "canal": pol["canal"],
        "vencimento": du.to_br(_add_days(today, int(pol["prazo_dias"]))),
        "motivo": motivo,
        "script": script_for(segmento, nome, loja),
    }


def _add_days(d: date, n: int) -> date:
    from datetime import timedelta
    return d + timedelta(days=n)


def _sort_key(task: dict) -> tuple:
    """Ordena por prioridade ASC e, dentro dela, pelo mais frio (R_dias) primeiro."""
    venc_iso = du.to_iso(task.get("vencimento", "")) or "9999-99-99"
    return (task.get("prioridade", 99), venc_iso, -_recency(task))


def _recency(task: dict) -> int:
    m = task.get("motivo", "")
    # extrai o número de dias do motivo "Última compra há N dias" para desempate
    for tok in str(m).split():
        if tok.isdigit():
            return int(tok)
    return 0


def generate_cadence(
    rows: Iterable[dict],
    today: Optional[date] = None,
    loja: str = "",
    only_segments: Optional[Iterable[str]] = None,
) -> list:
    """
    Gera a lista de tarefas de cadência a partir das linhas RFM, já ordenada por
    prioridade (segmentos mais urgentes primeiro). Clientes em cooldown ou de
    segmento desconhecido são descartados.

    only_segments: se informado, restringe aos segmentos da coleção (ex.: só os
    de win-back ⚠️/🌙/❄️ para uma campanha de reativação).
    """
    today = today or date.today()
    allow = set(only_segments) if only_segments is not None else None
    tarefas = []
    for row in rows:
        if allow is not None and str(row.get("segmento", "")) not in allow:
            continue
        t = build_task(row, today=today, loja=loja)
        if t is not None:
            tarefas.append(t)
    tarefas.sort(key=_sort_key)
    return tarefas


def daily_agenda(
    rows: Iterable[dict],
    today: Optional[date] = None,
    loja: str = "",
    limit: int = 10,
) -> list:
    """
    "MEU DIA" (UX-1): as `limit` tarefas mais prioritárias para o vendedor atacar
    hoje. Atalho sobre generate_cadence com um teto de itens para não afogar a home.
    """
    tarefas = generate_cadence(rows, today=today, loja=loja)
    if limit is not None and limit >= 0:
        return tarefas[:limit]
    return tarefas


def cadence_summary(tasks: Iterable[dict]) -> dict:
    """
    Resumo por canal e por segmento para o cabeçalho do painel:
        {"total": n, "por_canal": {...}, "por_segmento": {...}}
    """
    tasks = list(tasks)
    por_canal: dict = {}
    por_seg: dict = {}
    for t in tasks:
        por_canal[t.get("canal", "?")] = por_canal.get(t.get("canal", "?"), 0) + 1
        por_seg[t.get("segmento", "?")] = por_seg.get(t.get("segmento", "?"), 0) + 1
    return {"total": len(tasks), "por_canal": por_canal, "por_segmento": por_seg}
