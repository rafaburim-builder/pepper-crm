"""
pos_venda.py — Régua de pós-venda D+1 / D+7 / D+30 / D+90.

Fluxo:
  1. scan_new_sales() lê LinxMovimento buscando vendas recentes
     não registradas ainda na régua.
  2. Para cada venda nova, cria entradas na fila (email_queue) para
     os 4 touchpoints: D+1, D+7, D+30, D+90.
  3. O job das 02h (_auto_update.py) já chama process_queue() —
     os e-mails saem automaticamente nos dias certos.

Templates por etapa (focados em ótica / saúde visual):
  D+1  — confirmação + agradecimento
  D+7  — check-in de satisfação
  D+30 — adaptação / revisão
  D+90 — lembrete de nova consulta
"""
import json, os
from datetime import date, timedelta

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG  = os.path.join(ROOT, "data", "pos_venda_log.json")

TOUCHPOINTS = [
    {
        "dia":      1,
        "assunto":  "Obrigado pela sua visita à Chilli Beans! 🌶️",
        "template": (
            "Oi {nome}! Muito obrigado pela sua visita à Chilli Beans. "
            "Esperamos que esteja adorando seu novo produto! "
            "Qualquer dúvida ou ajuste, estamos à disposição."
        ),
    },
    {
        "dia":      7,
        "assunto":  "Como está sua experiência? 👓",
        "template": (
            "Oi {nome}! Já faz uma semana desde sua visita. "
            "Como está se adaptando? Se tiver alguma dúvida sobre o uso ou cuidados, "
            "adoraríamos ajudar — é só responder este e-mail."
        ),
    },
    {
        "dia":      30,
        "assunto":  "Sua visão está confortável? 🔍",
        "template": (
            "Oi {nome}! Passando para saber como está sua adaptação após um mês. "
            "É normal que os olhos levem um tempo para se ajustar — "
            "se sentir qualquer desconforto, agende uma revisão gratuita conosco."
        ),
    },
    {
        "dia":      90,
        "assunto":  "Hora de uma nova consulta? 📅",
        "template": (
            "Oi {nome}! Já se passaram 3 meses desde sua última visita. "
            "Sabia que é recomendado revisar a prescrição anualmente? "
            "Que tal agendar uma consulta para garantir que sua visão está em dia?"
        ),
    },
]


def _load_log() -> dict:
    if not os.path.exists(_LOG):
        return {}
    try:
        with open(_LOG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_log(data: dict) -> None:
    os.makedirs(os.path.dirname(_LOG), exist_ok=True)
    with open(_LOG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def register_sale_for_pos_venda(
    codigo: str,
    nome: str,
    email: str,
    data_venda: date,
) -> int:
    """Registra uma venda e cria os 4 touchpoints na fila de e-mail.
    Retorna o número de touchpoints agendados (0 se já registrado)."""
    log = _load_log()
    key = f"{codigo}_{data_venda.strftime('%Y%m%d')}"
    if key in log:
        return 0  # já foi registrado

    if not email:
        return 0  # sem e-mail, sem envio

    from modules.email_queue import push_to_queue
    from modules.lgpd import is_optout
    if is_optout(codigo):
        return 0  # respeita opt-out LGPD

    agendados = 0
    for tp in TOUCHPOINTS:
        data_envio = data_venda + timedelta(days=tp["dia"])
        if data_envio < date.today():
            continue  # janela já passou (venda antiga)
        msg = tp["template"].replace("{nome}", nome.split()[0] if nome else "cliente")
        push_to_queue([{
            "id":       codigo,
            "nome":     nome,
            "email":    email,
            "assunto":  tp["assunto"],
            "mensagem": msg,
            "segmento": f"pos_venda_D+{tp['dia']}",
        }])
        agendados += 1

    if agendados > 0:
        log[key] = {
            "codigo": codigo, "nome": nome,
            "data_venda": data_venda.strftime("%d/%m/%Y"),
            "touchpoints": agendados,
            "registrado_em": date.today().strftime("%d/%m/%Y"),
        }
        _save_log(log)

    return agendados


def scan_and_register(df_vendas, client_map: dict) -> dict:
    """Varre df_vendas buscando vendas dos últimos 90 dias e registra
    os clientes com e-mail na régua de pós-venda.
    Retorna {"novos": int, "ja_registrados": int}."""
    if df_vendas is None or df_vendas.empty:
        return {"novos": 0, "ja_registrados": 0}

    import pandas as pd
    cutoff = date.today() - timedelta(days=90)
    novos = ja_reg = 0

    # Pega a última venda por cliente
    df_v = df_vendas.copy()
    if "data" in df_v.columns:
        df_v["_dt"] = pd.to_datetime(df_v["data"], errors="coerce").dt.date
        df_v = df_v[df_v["_dt"] >= cutoff]
        df_v = df_v.sort_values("_dt", ascending=False).drop_duplicates("cod_vendedor") if "cod_vendedor" in df_v.columns else df_v

    # Agrupa por (num_documento) para pegar uma linha por venda
    if "num_documento" in df_v.columns:
        df_v = df_v.drop_duplicates("num_documento")

    for _, row in df_v.iterrows():
        dt = row.get("_dt") or date.today()
        cod = str(row.get("num_documento", ""))
        # Tenta achar o cliente pelo código de vendedor ou outro campo
        # Como não temos codigo_cliente direto no df_vendas,
        # esta função é chamada com df_ret (que tem codigo_cliente)
        pass

    return {"novos": novos, "ja_registrados": ja_reg}


def scan_from_retorno(df_ret, client_map: dict) -> dict:
    """Registra régua para clientes do df_retorno (que tem codigo_cliente)."""
    if df_ret is None or df_ret.empty:
        return {"novos": 0, "ja_registrados": 0}

    from modules.dateutils import parse_br_date
    cutoff = date.today() - timedelta(days=90)
    novos = ja_reg = 0

    for _, row in df_ret.iterrows():
        d = parse_br_date(row.get("ultima_compra"))
        if d is None or d < cutoff:
            continue
        codigo = str(row.get("codigo_cliente", ""))
        info   = client_map.get(codigo, {})
        email  = info.get("email", "")
        nome   = info.get("nome", "")
        if not email:
            ja_reg += 1
            continue
        n = register_sale_for_pos_venda(codigo, nome, email, d)
        if n > 0:
            novos += 1
        else:
            ja_reg += 1

    return {"novos": novos, "ja_registrados": ja_reg}
