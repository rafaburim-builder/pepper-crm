"""
whatsapp_campaign.py — Preparação PURA de campanhas de WhatsApp (dedup + supressão).

POR QUE ESTE MÓDULO EXISTE
--------------------------
O WhatsApp é hoje o ÚNICO canal de saída ativo do Pepper, mas as auditorias do
builder mostraram que a fila de envio bruta (todo cliente com telefone) gasta
mensagens à toa:

  - Iteração 10: 23 grupos / 63 clientes compartilham o MESMO telefone. O maior
    grupo tem 11 clientes em um único número — provável número da LOJA usado como
    fallback no cadastro. Mandar reativação para o número da própria loja é
    inútil (e, repetido, é spam). Famílias (2–4 pessoas no mesmo celular) são
    legítimas, mas o recado chega UMA vez àquele aparelho — não N vezes.
  - Iteração 11: a trava anti-spam (was_contacted_this_month / "⚠️ Contatado há
    Xd") EXISTE e está ligada em app.py, mas chega VAZIA porque o log do contato
    é um 2º passo manual que quase nunca acontece. Enquanto LOG-1 não acopla o
    log ao envio, a lista de destinatários já pode RESPEITAR quem foi contatado
    no mês quando essa informação for fornecida.

Este módulo entrega a CAMADA DE PREPARAÇÃO da campanha de WhatsApp — pura, sem
efeitos colaterais — o análogo de modules.email_campaign para o telefone:

  1. seleção de destinatários ENTREGÁVEIS (telefone normalizável + número da
     loja/fallback suprimido + deduplicado por telefone + opcionalmente
     respeitando a trava mensal de quem já foi contatado);
  2. renderização do envio (link wa.me + mensagem) reaproveitando exatamente
     modules.marketing.make_whatsapp_link / format_message.

LIMITES DELIBERADOS (segurança / reversibilidade)
-------------------------------------------------
  - NÃO abre rede, NÃO envia WhatsApp, NÃO lê/grava arquivos, NÃO toca banco nem
    credenciais. A trava mensal é consultada FORA (o app passa o conjunto de
    códigos já contatados, lido de modules.db) — aqui só se filtra, mantendo a
    função pura e testável.
  - Este módulo é IMPORTÁVEL mas NÃO é importado por app.py — ligá-lo é um passo
    explícito (com o app parado). Por isso é zero-risco para o app em produção.

Tudo aqui é determinístico e testável — ver tests/test_whatsapp_campaign.py.
Relaciona-se com LOG-1 / DADOS-5 / DADOS-6 do relatório do builder.
"""
from typing import Callable, Dict, Iterable, List, Optional, Set, Union

from .marketing import format_message, make_whatsapp_link, normalize_phone, DEFAULT_TEMPLATE

# Mensagem padrão de reativação: a MESMA do WhatsApp/e-mail (consistência de canal).
DEFAULT_WHATSAPP_BODY = DEFAULT_TEMPLATE

# A partir de quantos clientes no MESMO telefone tratamos o número como
# loja/fallback (suprimir o grupo inteiro). Famílias legítimas (2–4 no mesmo
# celular) ficam abaixo do limiar e são apenas DEDUPLICADAS para 1 envio.
# Iteração 10 viu grupos de 11, 5, 4, 3, 3 → 5 isola loja(11)/coletivo(5) e
# preserva as famílias 4/3/3. Configurável.
DEFAULT_STORE_THRESHOLD = 5


# ----------------------------------------------------------------- contatados
def _contacted_predicate(
    already_contacted: Optional[Union[Iterable, Callable[[object], bool]]],
) -> Callable[[object], bool]:
    """Normaliza o argumento da trava mensal para um predicado cod->bool.

    Aceita: None (ninguém contatado), um iterável de códigos já contatados no
    mês, ou um callable(cod)->bool. Mantém a função de montagem pura: a consulta
    real ao banco (db.was_contacted_this_month) é feita por quem CHAMA."""
    if already_contacted is None:
        return lambda cod: False
    if callable(already_contacted):
        return already_contacted
    contacted: Set[str] = {str(c) for c in already_contacted}
    return lambda cod: str(cod) in contacted


# --------------------------------------------------------------- destinatários
def build_whatsapp_recipient_list(
    cmap: Dict[str, dict],
    default_ddd: str = "",
    store_threshold: int = DEFAULT_STORE_THRESHOLD,
    already_contacted: Optional[Union[Iterable, Callable[[object], bool]]] = None,
) -> Dict[str, object]:
    """Monta a lista de destinatários ENTREGÁVEIS de uma campanha de WhatsApp.

    Espelha modules.email_campaign.build_recipient_list, mas para telefone,
    aplicando as lições das iterações 10 e 11:

      1. mantém só clientes com telefone NORMALIZÁVEL (normalize_phone != "");
      2. SUPRIME números de loja/fallback — telefones compartilhados por
         >= `store_threshold` clientes (o grupo inteiro sai);
      3. RESPEITA a trava mensal — remove quem já foi contatado no mês, quando
         `already_contacted` é fornecido (conjunto de cods ou predicado);
      4. DEDUPLICA por telefone: um envio por aparelho, mantendo o 1º cliente
         (ordem estável por código) e contando os demais como redundantes.

    Função PURA: não envia, não escreve, não toca banco nem credenciais.

    Retorna {"recipients": [...], "stats": {...}}:
      recipients: lista de {"cod", "nome", "fone"} (telefone normalizado), pronta
                  para o envio (1 por aparelho).
      stats: total_clients, com_fone_valido, loja_suprimidos, ja_contatados,
             deduplicados_removidos, entregaveis.
    """
    total = len(cmap)
    valid_fone = 0
    is_contacted = _contacted_predicate(already_contacted)

    # Passo 1: candidatos = telefone normalizável; agrupa por número.
    groups: Dict[str, List[dict]] = {}
    for cod, v in cmap.items():
        v = v or {}
        phone = normalize_phone(v.get("fone", ""), default_ddd)
        if not phone:
            continue
        valid_fone += 1
        groups.setdefault(phone, []).append(
            {"cod": cod, "nome": (v.get("nome") or "").strip(), "fone": phone}
        )

    # Passo 2: suprime loja/fallback; aplica trava mensal; dedup mantém o 1º.
    recipients: List[dict] = []
    store_suppressed = 0
    contacted_suppressed = 0
    dedup_removed = 0
    for phone, members in groups.items():
        if len(members) >= store_threshold:
            store_suppressed += len(members)
            continue
        # ordem estável por código para tornar o "primeiro" determinístico
        members_sorted = sorted(members, key=lambda m: str(m["cod"]))
        # trava mensal: descarta membros já contatados no mês
        eligible = [m for m in members_sorted if not is_contacted(m["cod"])]
        contacted_suppressed += len(members_sorted) - len(eligible)
        if not eligible:
            continue
        recipients.append(eligible[0])
        dedup_removed += len(eligible) - 1

    recipients.sort(key=lambda m: str(m["cod"]))
    stats = {
        "total_clients":          total,
        "com_fone_valido":        valid_fone,
        "loja_suprimidos":        store_suppressed,
        "ja_contatados":          contacted_suppressed,
        "deduplicados_removidos": dedup_removed,
        "entregaveis":            len(recipients),
    }
    return {"recipients": recipients, "stats": stats}


# ------------------------------------------------------------------ renderização
def render_whatsapp(
    nome: str,
    fone: str,
    categoria: str = "",
    data: str = "",
    dias: int = 0,
    default_ddd: str = "",
    body_template: str = DEFAULT_WHATSAPP_BODY,
) -> Dict[str, str]:
    """Renderiza {mensagem, link} para um envio de WhatsApp.

    Usa modules.marketing.format_message para o corpo (mesmo motor/labels do
    e-mail → mensagem consistente entre canais) e make_whatsapp_link para o link
    wa.me. `link` vem "" se o telefone for inválido. Função PURA — só strings.
    """
    message = format_message(body_template, nome, categoria, data, dias)
    link = make_whatsapp_link(fone, message, default_ddd)
    return {"mensagem": message, "link": link}
