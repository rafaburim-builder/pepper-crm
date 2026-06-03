"""
marketing.py — Campaign management and WhatsApp link generation for Pepper.

Campanhas ficam em data/campaigns.json.
Cada campanha: {nome, objetivo, template}
Variáveis do template: {nome}, {categoria}, {data}, {dias}
"""
import json
import os
import re
import urllib.parse

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FILE = os.path.join(_BASE, "data", "campaigns.json")

DEFAULT_TEMPLATE = (
    "Oi {nome}! Aqui é a Chilli Beans 🌶️ Faz {dias} dias que não te vemos — "
    "sua última {categoria} foi em {data}. "
    "Que tal dar uma passada para conferir as coleções novas? "
    "Temos novidades esperando por você! 😎"
)

_DEFAULT_THRESHOLDS = {"LV": 12, "OC": 12, "ML": 12, "LE": 6, "LC": 3}

_CAT_LABEL = {
    "LV":                 "armação de grau",
    "OC":                 "óculos solar",
    "ML":                 "armação multi",
    "LE":                 "lente",
    "LC":                 "lente de contato",
    "AC":                 "acessório",
    "Armações de Grau":   "armação de grau",
    "Óculos Solar":       "óculos solar",
    "Armações Multi":     "armação multi",
    "Lentes":             "lente",
    "Lentes de Contato":  "lente de contato",
    "Acessórios":         "acessório",
}


def load_campaigns() -> list:
    """Carrega campanhas do disco com backfill de campos novos.
    Se não existir arquivo, retorna a campanha padrão."""
    if os.path.exists(_FILE):
        try:
            with open(_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                # Backfill campos adicionados em v1.3.0/v1.4.0
                changed = False
                for c in data:
                    if "thresholds" not in c:
                        c["thresholds"] = dict(_DEFAULT_THRESHOLDS)
                        changed = True
                    else:
                        # Backfill novos campos LE/LC adicionados em v1.4.0
                        for _k, _v in _DEFAULT_THRESHOLDS.items():
                            if _k not in c["thresholds"]:
                                c["thresholds"][_k] = _v
                                changed = True
                    if "expiry" not in c:
                        c["expiry"] = None
                        changed = True
                    if "filtros" not in c:
                        c["filtros"] = {}
                        changed = True
                if changed:
                    save_campaigns(data)
                return data
        except Exception:
            pass
    # Arquivo não existe ou está corrompido — retorna padrão
    default = [{
        "nome":       "Reativação Padrão",
        "objetivo":   "Reativar clientes sem compra no período configurado",
        "template":   DEFAULT_TEMPLATE,
        "thresholds": dict(_DEFAULT_THRESHOLDS),
        "expiry":     None,
        "filtros":    {},
    }]
    save_campaigns(default)
    return default


def save_campaigns(campaigns: list) -> None:
    os.makedirs(os.path.dirname(_FILE), exist_ok=True)
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(campaigns, f, ensure_ascii=False, indent=2)


def format_message(template: str, nome: str, categoria: str, data: str, dias: int) -> str:
    """Substitui {nome}, {categoria}, {data}, {dias} no template."""
    cat_label  = _CAT_LABEL.get(categoria, categoria.lower())
    first_name = nome.strip().split()[0] if nome.strip() else nome
    return (
        template
        .replace("{nome}",      first_name)
        .replace("{categoria}", cat_label)
        .replace("{data}",      data)
        .replace("{dias}",      str(dias))
    )


def normalize_phone(fone: str, default_ddd: str = "") -> str:
    """Normaliza telefone para apenas dígitos, adicionando DDD se necessário.

    Retorna o número normalizado (sem código do país) ou "" se inválido.

    Regras:
    - Remove tudo que não é dígito
    - Se começar com 55 e tiver >= 12 dígitos: remove o prefixo 55
    - 11 dígitos: celular com DDD  (11 9XXXX-XXXX)
    - 10 dígitos: fixo   com DDD  (11 XXXX-XXXX)
    -  9 dígitos: celular sem DDD → adiciona DDD padrão
    -  8 dígitos: fixo   sem DDD → adiciona DDD padrão
    - Demais: inválido → ""
    """
    digits = re.sub(r"\D", "", fone or "")
    if not digits:
        return ""
    # Remove código do país se presente
    if digits.startswith("55") and len(digits) >= 12:
        digits = digits[2:]
    if len(digits) in (10, 11):
        return digits
    if len(digits) in (8, 9):
        ddd = re.sub(r"\D", "", default_ddd or "")[:2]
        if len(ddd) == 2:
            return ddd + digits
        return ""
    return ""


def make_whatsapp_link(fone: str, message: str, default_ddd: str = "") -> str:
    """Gera link wa.me/55<fone>?text=<mensagem codificada>.
    Retorna "" se o telefone for inválido."""
    phone = normalize_phone(fone, default_ddd)
    if not phone:
        return ""
    encoded = urllib.parse.quote(message)
    return f"https://wa.me/55{phone}?text={encoded}"
