"""
manager_coverage.py — Painel de COBERTURA por território para o GERENTE.

Por que existe (builder, iteração 17):
  As iterações 8-15 produziram, em arquivos de TESTE, uma cadeia de achados sobre
  alcance/território da base de clientes (1.825 clientes). Todo esse conhecimento
  estava preso nos testes — o app (e portanto o gerente) não conseguia VER.
  Este módulo consolida essa lógica PURA, já validada, num único ponto importável,
  pensado para a persona que ainda não tinha entregável: o GERENTE de praça.

  Achados que este módulo operacionaliza:
    - GEO-1 (Iter 13): o WhatsApp — único canal de saída ativo — é, na prática,
      SP-only; fora de SP a base é alcançável só por e-mail.
    - UF-1 (Iter 14): 24 das 27 UFs são "puro-lote" (100% vindas do import de
      15/05, telefone-pobre) → WhatsApp ~0%; o nº de clientes-do-lote-sem-telefone
      é o ROI de enriquecimento telefônico daquela praça.
    - GEO-2 (Iter 13/15): os 18 "mortos" (sem nenhum canal) por praça, para sanear.
    - CIDADE-NORM (Iter 15): a chave canônica de cidade colapsa variantes de
      acento/caixa para o painel não fragmentar uma praça em várias linhas.

  A intenção é que uma futura página "Cobertura (Gerente)" no app.py chame
  `manager_coverage_report(load_clients(), default_ddd=...)` e renderize as linhas
  por UF + a lista de mortos + o ranking de ROI. Hoje o módulo é PURO e NÃO é
  importado pelo app — ligá-lo é um passo explícito com o app parado (zero risco
  ao app em produção rodando agora).

ESCOPO E SEGURANÇA:
  Sem IO, sem rede, sem credenciais. Não lê nem escreve arquivos: recebe o cmap
  já carregado. Reusa normalize_phone (modules.marketing). Funções determinísticas.
"""
import datetime
import re
import unicodedata
from collections import defaultdict

from modules.marketing import normalize_phone

# Carimbo de importação detectado na Iter 12 (DADOS-7): 58% da base carrega esta
# data em cliente_desde (data de carga, não aquisição real). Parametrizável.
IMPORT_STAMP = datetime.date(2026, 5, 15)

# Mesmo critério de FORMATO das Iter 9/13 (não garante entregabilidade).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(e):
    """True se o e-mail tem FORMATO válido (não garante entrega)."""
    return bool(_EMAIL_RE.match((e or "").strip()))


def norm_city(s):
    """Chave canônica de cidade: sem acento, MAIÚSCULA, espaços colapsados.

    Colapsa variantes da mesma praça ("Brasília"/"Brasilia", "Porto Ferreira"/
    "Porto ferreira") na MESMA chave → uma linha só por cidade no painel.
    Vazio/None → "".
    """
    s = (s or "").strip()
    if not s:
        return ""
    s2 = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", s2).upper().strip()


def _parse_date(raw):
    """date a partir de 'DD/MM/AAAA', ou None se vazio/'-'/inválido."""
    s = (raw or "").strip()
    if not s or s == "-":
        return None
    try:
        return datetime.datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        return None


def is_batch_client(rec, stamp=IMPORT_STAMP):
    """True se cliente_desde do registro é exatamente a data do carimbo de import."""
    return _parse_date((rec or {}).get("cliente_desde", "")) == stamp


def _uf_status(d):
    """Rótulo de cobertura da praça, pensado para o gerente bater o olho.

    - "PURO-LOTE / SÓ E-MAIL": só clientes do lote, nenhum nativo → WhatsApp ~0,
      reativação por WhatsApp impossível até enriquecer telefone.
    - "WHATSAPP CRÍTICO": WhatsApp abaixo de 20% e existe e-mail como alternativa.
    - "WHATSAPP OK": maioria alcançável por WhatsApp.
    - "SEM CANAL": praça sem nenhum canal (raro).
    """
    t = d["total"]
    if t == 0:
        return "SEM CLIENTES"
    if d["mortos"] == t:
        return "SEM CANAL"
    if d.get("puro_lote"):
        return "PURO-LOTE / SO E-MAIL"
    if d["pct_wa"] < 20.0:
        return "WHATSAPP CRITICO"
    return "WHATSAPP OK"


def manager_coverage_report(cmap, default_ddd="", stamp=IMPORT_STAMP):
    """Relatório UNIFICADO de cobertura por território, para o gerente.

    Uma única passada sobre o cmap consolida o que antes vivia em três auditorias
    separadas (geo_reach, uf_batch_roi, city fragmentation). PURO: não escreve nada.

    Retorna dict:
      {
        "total": int,
        "mortos": int,                       # base inteira sem nenhum canal
        "batch_total": int,                  # clientes do lote 15/05
        "roi_total": int,                    # batch sem telefone (alcance WA a destravar)
        "wa_alcance": int, "email_alcance": int,
        "wa_top_uf": uf|None, "wa_top_uf_share": float,  # concentração do WhatsApp
        "ufs_puro_lote": int,                # nº de UFs 100% lote (WhatsApp ~0)
        "cidades_canonicas": int,            # praças distintas após norm_city
        "por_uf": { uf: {total, wa, email, mortos, batch, nativo, batch_sem_fone,
                          pct_wa, pct_email, pct_mortos, puro_lote, status,
                          cidades: int} },
        "roi_ranking": [ (uf, batch_sem_fone), ... ],     # desc por volume
        "uf_ordenado": [ uf, ... ],          # UFs por total desc (ordem do painel)
      }
    """
    por_uf = {}
    cidades_por_uf = defaultdict(set)
    cidades_global = set()
    wa_alcance = email_alcance = batch_total = 0

    for v in cmap.values():
        v = v or {}
        uf = (v.get("uf") or "").strip().upper() or "(vazio)"
        d = por_uf.setdefault(
            uf, {"total": 0, "wa": 0, "email": 0, "mortos": 0,
                 "batch": 0, "nativo": 0, "batch_sem_fone": 0}
        )
        d["total"] += 1

        has_phone = bool(normalize_phone(v.get("fone", ""), default_ddd))
        has_email = is_valid_email(v.get("email", ""))
        if has_phone:
            d["wa"] += 1
            wa_alcance += 1
        if has_email:
            d["email"] += 1
            email_alcance += 1
        if not has_phone and not has_email:
            d["mortos"] += 1

        if is_batch_client(v, stamp):
            d["batch"] += 1
            batch_total += 1
            if not has_phone:
                d["batch_sem_fone"] += 1
        else:
            d["nativo"] += 1

        ck = norm_city(v.get("cidade", ""))
        if ck:
            cidades_por_uf[uf].add(ck)
            cidades_global.add((uf, ck))

    mortos = roi_total = 0
    for uf, d in por_uf.items():
        t = d["total"]
        d["pct_wa"] = (100.0 * d["wa"] / t) if t else 0.0
        d["pct_email"] = (100.0 * d["email"] / t) if t else 0.0
        d["pct_mortos"] = (100.0 * d["mortos"] / t) if t else 0.0
        d["puro_lote"] = d["batch"] > 0 and d["nativo"] == 0
        d["cidades"] = len(cidades_por_uf.get(uf, ()))
        d["status"] = _uf_status(d)
        mortos += d["mortos"]
        roi_total += d["batch_sem_fone"]

    wa_top_uf = None
    wa_top_uf_share = 0.0
    if wa_alcance:
        wa_top_uf = max(por_uf, key=lambda u: por_uf[u]["wa"])
        wa_top_uf_share = 100.0 * por_uf[wa_top_uf]["wa"] / wa_alcance

    roi_ranking = sorted(
        ((uf, d["batch_sem_fone"]) for uf, d in por_uf.items()
         if d["batch_sem_fone"] > 0),
        key=lambda kv: (-kv[1], kv[0]),
    )
    uf_ordenado = sorted(por_uf, key=lambda u: (-por_uf[u]["total"], u))

    return {
        "total": len(cmap),
        "mortos": mortos,
        "batch_total": batch_total,
        "roi_total": roi_total,
        "wa_alcance": wa_alcance,
        "email_alcance": email_alcance,
        "wa_top_uf": wa_top_uf,
        "wa_top_uf_share": wa_top_uf_share,
        "ufs_puro_lote": sum(1 for d in por_uf.values() if d["puro_lote"]),
        "cidades_canonicas": len(cidades_global),
        "por_uf": por_uf,
        "roi_ranking": roi_ranking,
        "uf_ordenado": uf_ordenado,
    }


def mortos_list(cmap, default_ddd=""):
    """Lista (saneamento, GEO-2) dos clientes 'mortos' — sem WhatsApp nem e-mail
    válido — com praça, para o gerente/captador endereçar 1 a 1. PURO.

    Retorna lista de dicts {cod, nome, uf, cidade} ordenada por (uf, cidade, nome).
    """
    out = []
    for cod, v in cmap.items():
        v = v or {}
        has_phone = bool(normalize_phone(v.get("fone", ""), default_ddd))
        has_email = is_valid_email(v.get("email", ""))
        if not has_phone and not has_email:
            out.append({
                "cod": cod,
                "nome": (v.get("nome") or "").strip(),
                "uf": (v.get("uf") or "").strip().upper(),
                "cidade": (v.get("cidade") or "").strip(),
            })
    out.sort(key=lambda r: (r["uf"], norm_city(r["cidade"]), r["nome"]))
    return out
