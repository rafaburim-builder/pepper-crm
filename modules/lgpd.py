"""
lgpd.py — Gerenciamento de consentimento LGPD por cliente.

Dois arquivos separados:
  data/lgpd_optout.json  — clientes que pediram OPT-OUT (não receber comunicações)
  data/lgpd_consent.json — clientes que deram OPT-IN  (consentimento positivo)

Prazo legal: 24h para remover da base após solicitação de opt-out (LGPD 2026).

Uso:
  from modules.lgpd import is_optout, set_optout, has_consent, set_consent, lgpd_status
  if has_consent(codigo) and not is_optout(codigo):
      # pode enviar via API automática
"""
import json, os
from datetime import date

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH   = os.path.join(ROOT, "data", "lgpd_optout.json")

def _get_optout_path() -> str:
    try:
        from modules.data_dir import data_path
        return data_path("lgpd_optout.json")
    except Exception:
        return _PATH

def _get_consent_path() -> str:
    try:
        from modules.data_dir import data_path
        return data_path("lgpd_consent.json")
    except Exception:
        return os.path.join(ROOT, "data", "lgpd_consent.json")

# ── Canais de coleta de consentimento ─────────────────────────────────────────
CANAIS_CONSENT = {
    "tablet_loja":          "📱 Tablet na loja (no ato da venda)",
    "verbal_vendedor":      "🗣️ Verbal — registrado pelo vendedor",
    "formulario_fisico":    "📄 Formulário físico assinado",
    "whatsapp_confirmacao": "💬 Confirmado pelo WhatsApp",
}


# ── OPT-OUT (clientes que NÃO querem receber comunicações) ───────────────────

def load_optout() -> dict:
    path = _get_optout_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    path = _get_optout_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        from modules.cloud_storage import save_json as _csave, _is_cloud
        if _is_cloud():
            _csave("lgpd_optout.json", data)
    except Exception:
        pass


def is_optout(codigo: str) -> bool:
    return str(codigo) in load_optout()


def set_optout(codigo: str, nome: str = "", motivo: str = "") -> None:
    """Registra opt-out. Deve ser processado em até 24h."""
    data = load_optout()
    data[str(codigo)] = {
        "nome":    nome,
        "motivo":  motivo,
        "data":    date.today().strftime("%d/%m/%Y"),
        "prazo":   "24h — remover de todas as listas de contato",
    }
    _save(data)
    # Se havia consentimento positivo, revoga automaticamente
    revoke_consent(codigo)


def remove_optout(codigo: str) -> None:
    """Remove opt-out (cliente re-consentiu)."""
    data = load_optout()
    data.pop(str(codigo), None)
    _save(data)


def filter_optout(codigos: list) -> list:
    """Retorna apenas os códigos que NÃO estão em opt-out."""
    optouts = load_optout()
    return [c for c in codigos if str(c) not in optouts]


def optout_count() -> int:
    return len(load_optout())


# ── OPT-IN / CONSENTIMENTO POSITIVO (clientes que AUTORIZARAM comunicações) ──

def load_consent() -> dict:
    """Carrega todos os consentimentos positivos registrados."""
    path = _get_consent_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_consent(data: dict) -> None:
    path = _get_consent_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        from modules.cloud_storage import save_json as _csave, _is_cloud
        if _is_cloud():
            _csave("lgpd_consent.json", data)
    except Exception:
        pass


def has_consent(codigo: str) -> bool:
    """Retorna True se o cliente deu consentimento positivo para comunicações."""
    return str(codigo) in load_consent()


def set_consent(
    codigo: str,
    nome: str = "",
    canal: str = "verbal_vendedor",
    operador: str = "",
) -> None:
    """
    Registra consentimento positivo do cliente.
    Canal: ver CANAIS_CONSENT para opções válidas.
    """
    data = load_consent()
    data[str(codigo)] = {
        "nome":      nome,
        "canal":     canal,
        "operador":  operador,
        "data":      date.today().strftime("%d/%m/%Y"),
    }
    _save_consent(data)


def revoke_consent(codigo: str) -> None:
    """Revoga consentimento positivo (cliente retirou autorização)."""
    data = load_consent()
    if str(codigo) in data:
        data.pop(str(codigo), None)
        _save_consent(data)


def consent_count() -> int:
    """Total de clientes com consentimento positivo registrado."""
    return len(load_consent())


def filter_consented(codigos: list) -> list:
    """Retorna apenas os códigos COM consentimento positivo e SEM opt-out."""
    consents = load_consent()
    optouts  = load_optout()
    return [
        c for c in codigos
        if str(c) in consents and str(c) not in optouts
    ]


def lgpd_status(codigo: str) -> str:
    """
    Retorna o status LGPD consolidado do cliente para exibição em listas:
      🚫 Opt-out   — pediu para sair (NÃO enviar nada)
      ✅ Consentiu — deu autorização positiva (pode enviar via API automática)
      ⬜ Pendente  — nenhum registro ainda (envio manual ok, automação bloqueada)
    """
    c = str(codigo)
    if is_optout(c):
        return "🚫 Opt-out"
    if has_consent(c):
        return "✅ Consentiu"
    return "⬜ Pendente"
