"""
email_campaign.py — Preparação PURA de campanhas de e-mail (canal CANAL-EMAIL).

POR QUE ESTE MÓDULO EXISTE
--------------------------
As iterações 8–14 do builder mediram, com dados reais de produção, que o
WhatsApp — único canal de saída ativo hoje — alcança apenas ~41,5% da base e,
pior, é geograficamente monocultural (praticamente só São Paulo): fora de SP a
base veio de um lote de importação (15/05/2026) rico em e-mail e pobre em
telefone. O e-mail é, de longe, a maior alavanca barata de alcance:
  - alcance combinado (WhatsApp OU e-mail entregável) ≈ 94% vs 41,5% só-WhatsApp;
  - ganho incremental honesto do e-mail ≈ 962 clientes hoje inalcançáveis,
    DEPOIS de remover placeholders ("naotem@gmail.com") e e-mails compartilhados
    da loja/vendedor (que não alcançam o cliente real).

Este módulo entrega a CAMADA DE PREPARAÇÃO da campanha — pura, sem efeitos
colaterais — para que, quando o canal for ligado, o núcleo testado já exista:
  1. seleção de destinatários ENTREGÁVEIS (formato válido + sem placeholder +
     deduplicado por endereço + e-mails compartilhados suprimidos);
  2. renderização da mensagem (assunto + corpo) reaproveitando exatamente o
     mesmo motor de variáveis de modules.marketing.format_message.

LIMITES DELIBERADOS (segurança / reversibilidade)
-------------------------------------------------
  - NÃO faz transporte SMTP, NÃO abre rede, NÃO lê/gera arquivos, NÃO guarda
    nem usa credenciais. O envio real (SMTP/provedor) é tarefa MANUAL registrada
    como CANAL-EMAIL no relatório do builder, e exige decisão do gestor +
    credenciais no cofre seguro (modules.secure_store), nunca no código.
  - Este módulo é IMPORTÁVEL mas NÃO é importado por app.py — ligá-lo é um passo
    explícito (com o app parado). Por isso é zero-risco para o app em produção.
  - LGPD: a lista de destinatários deve, no momento da ligação, respeitar opt-out
    (tarefa 2.1/2.x do backlog). Este módulo só PREPARA; a checagem de consentimento
    entra no ponto de envio.

Tudo aqui é determinístico e testável — ver tests/test_email_campaign.py.
"""
from typing import Dict, List, Optional
import re

from .marketing import format_message, DEFAULT_TEMPLATE

# Mesmo "formato entregável" usado nos auditores (test_email_reach / test_contact_dedup).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# Local-parts marcadores de "cliente não informou e-mail": passam no regex de
# formato mas não alcançam ninguém. Match exato, case-insensitive.
_PLACEHOLDER_LOCAL = re.compile(
    r"^(naotem|naotenho|notem|nao|naosei|naoinformado|naopossui|sememail|sem|"
    r"n|na|x+|teste|test|abc|aaa|email|nenhum|consumidor|cliente)$",
    re.I,
)

# Assunto padrão de reativação (variáveis iguais ao corpo: {nome}/{categoria}/{data}/{dias}).
DEFAULT_EMAIL_SUBJECT = "{nome}, sentimos sua falta na Chilli Beans 🌶️"
# Corpo padrão: reaproveita o template de reativação já validado no WhatsApp.
DEFAULT_EMAIL_BODY = DEFAULT_TEMPLATE


# --------------------------------------------------------------------- validação
def is_valid_email(raw: Optional[str]) -> bool:
    """True se `raw` tem formato de e-mail entregável (não checa MX)."""
    em = (raw or "").strip()
    return bool(em and _EMAIL_RE.match(em))


def email_local(raw: Optional[str]) -> str:
    """Local-part minúsculo de um e-mail válido, ou '' se inválido."""
    if not is_valid_email(raw):
        return ""
    return raw.strip().lower().rsplit("@", 1)[0]


def email_domain(raw: Optional[str]) -> str:
    """Domínio minúsculo de um e-mail válido, ou '' se inválido."""
    if not is_valid_email(raw):
        return ""
    return raw.strip().lower().rsplit("@", 1)[1]


def normalize_email(raw: Optional[str]) -> str:
    """Endereço minúsculo e sem espaços para deduplicação, ou '' se inválido."""
    if not is_valid_email(raw):
        return ""
    return raw.strip().lower()


def is_placeholder_email(raw: Optional[str]) -> bool:
    """True se o e-mail tem formato válido mas o local-part é um marcador de
    'não tem e-mail' (não entregável ao cliente real)."""
    local = email_local(raw)
    return bool(local and _PLACEHOLDER_LOCAL.match(local))


# --------------------------------------------------------------- destinatários
def build_recipient_list(
    cmap: Dict[str, dict],
    shared_threshold: int = 3,
) -> Dict[str, object]:
    """Monta a lista de destinatários ENTREGÁVEIS de uma campanha de e-mail.

    Espelha exatamente como decidiríamos alcançar o cliente por e-mail, aplicando
    as lições das iterações 9/10 do builder (formato válido ≠ entregável):

      1. mantém só e-mails de FORMATO válido;
      2. descarta PLACEHOLDERs ("naotem@gmail.com", "n@...", etc.);
      3. descarta e-mails COMPARTILHADOS por >= `shared_threshold` clientes
         (e-mail da loja/vendedor usado como fallback — não alcança o cliente);
      4. DEDUPLICA por endereço: um envio por caixa, mantendo o 1º cliente
         (ordem estável por código) e contando os demais como removidos.

    Função PURA: não envia, não escreve, não toca credenciais.

    Retorna {"recipients": [...], "stats": {...}}:
      recipients: lista de {"cod", "nome", "email"} (e-mail normalizado), pronta
                  para o envio (1 por endereço).
      stats: total_clients, com_email_formato_valido, placeholder_suprimidos,
             compartilhados_suprimidos, deduplicados_removidos, entregaveis.
    """
    total = len(cmap)
    valid_format = 0
    placeholder = 0

    # Passo 1: candidatos = formato válido E não-placeholder; agrupa por endereço.
    groups: Dict[str, List[dict]] = {}
    for cod, v in cmap.items():
        v = v or {}
        raw = v.get("email", "")
        if not is_valid_email(raw):
            continue
        valid_format += 1
        if is_placeholder_email(raw):
            placeholder += 1
            continue
        addr = normalize_email(raw)
        groups.setdefault(addr, []).append(
            {"cod": cod, "nome": (v.get("nome") or "").strip(), "email": addr}
        )

    # Passo 2: suprime compartilhados; dedup mantém o 1º de cada grupo.
    recipients: List[dict] = []
    shared_suppressed = 0
    dedup_removed = 0
    for addr, members in groups.items():
        if len(members) >= shared_threshold:
            shared_suppressed += len(members)
            continue
        # ordem estável por código para tornar o "primeiro" determinístico
        members_sorted = sorted(members, key=lambda m: str(m["cod"]))
        recipients.append(members_sorted[0])
        dedup_removed += len(members_sorted) - 1

    recipients.sort(key=lambda m: str(m["cod"]))
    stats = {
        "total_clients":            total,
        "com_email_formato_valido": valid_format,
        "placeholder_suprimidos":   placeholder,
        "compartilhados_suprimidos": shared_suppressed,
        "deduplicados_removidos":   dedup_removed,
        "entregaveis":              len(recipients),
    }
    return {"recipients": recipients, "stats": stats}


# ------------------------------------------------------------------ renderização
def render_email(
    nome: str,
    categoria: str = "",
    data: str = "",
    dias: int = 0,
    subject_template: str = DEFAULT_EMAIL_SUBJECT,
    body_template: str = DEFAULT_EMAIL_BODY,
) -> Dict[str, str]:
    """Renderiza {assunto, corpo} substituindo {nome}/{categoria}/{data}/{dias}.

    Usa modules.marketing.format_message para o corpo (mesmo motor/labels do
    WhatsApp → mensagem consistente entre canais) e o mesmo mapeamento para o
    assunto. Função PURA — só devolve strings.
    """
    body = format_message(body_template, nome, categoria, data, dias)
    subject = format_message(subject_template, nome, categoria, data, dias)
    return {"assunto": subject, "corpo": body}
