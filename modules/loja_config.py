"""
loja_config.py — Configuração da loja e rastreamento de dados incorretos.

Armazena em data/loja_config.json:
  {
    "nome_loja":     "Ótica P. Ferreira",
    "cnpj":          "58.179.991/0001-00",
    "telefones_loja": ["19996470011"],        # nunca usar como contato de cliente
    "telefones_bloqueados": {                 # fone → {tipo, responsavel, motivo}
      "19996470011": {"tipo": "loja", ...},
      "19997639515": {"tipo": "pessoal_usuario", "usuario": "rafaburim", ...}
    }
  }

Alertas de qualidade de dados:
  Quando um novo cliente é importado com telefone ou e-mail que consta na lista
  de bloqueados, o sistema registra em data/qualidade_alertas.json e notifica
  os superiores na Tela de Bom Dia.
"""
import json
import os
from datetime import date, datetime
from typing import Optional

ROOT          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CFG_PATH     = os.path.join(ROOT, "data", "loja_config.json")
_ALERTAS_PATH = os.path.join(ROOT, "data", "qualidade_alertas.json")


# ── Loja config ───────────────────────────────────────────────────────────────

def load_loja_config() -> dict:
    if not os.path.exists(_CFG_PATH):
        return {}
    try:
        with open(_CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_loja_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(_CFG_PATH), exist_ok=True)
    with open(_CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_telefones_bloqueados() -> dict:
    """Retorna {fone_normalizado: {tipo, motivo, usuario?}} de todos os telefones bloqueados."""
    cfg = load_loja_config()
    return cfg.get("telefones_bloqueados", {})


def registrar_telefone_bloqueado(
    fone: str,
    tipo: str,           # "loja" | "pessoal_usuario"
    motivo: str = "",
    usuario: str = "",   # login do usuário (se tipo=pessoal_usuario)
) -> None:
    """Adiciona um telefone à lista de bloqueados (loja ou pessoal de funcionário)."""
    from modules.marketing import normalize_phone
    fone_norm = normalize_phone(fone, "")
    if not fone_norm:
        return
    cfg = load_loja_config()
    bloqueados = cfg.get("telefones_bloqueados", {})
    bloqueados[fone_norm] = {
        "fone_original": fone,
        "tipo":          tipo,
        "motivo":        motivo or ("Telefone da loja" if tipo == "loja" else "Telefone pessoal de funcionário"),
        "usuario":       usuario,
        "registrado_em": date.today().strftime("%d/%m/%Y"),
    }
    cfg["telefones_bloqueados"] = bloqueados
    # Garante que telefones da loja também ficam na lista rápida
    if tipo == "loja":
        tels = cfg.get("telefones_loja", [])
        if fone_norm not in tels:
            tels.append(fone_norm)
        cfg["telefones_loja"] = tels
    save_loja_config(cfg)


def is_telefone_bloqueado(fone: str) -> Optional[dict]:
    """Retorna o registro de bloqueio se o telefone estiver bloqueado, None caso contrário."""
    from modules.marketing import normalize_phone
    fone_norm = normalize_phone(fone, "")
    if not fone_norm:
        return None
    return get_telefones_bloqueados().get(fone_norm)


# ── Alertas de qualidade de dados ────────────────────────────────────────────

def load_alertas() -> list:
    if not os.path.exists(_ALERTAS_PATH):
        return []
    try:
        with open(_ALERTAS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_alertas(alertas: list) -> None:
    os.makedirs(os.path.dirname(_ALERTAS_PATH), exist_ok=True)
    with open(_ALERTAS_PATH, "w", encoding="utf-8") as f:
        json.dump(alertas[-200:], f, ensure_ascii=False, indent=2)


def registrar_alerta(
    tipo: str,          # "telefone_bloqueado" | "email_placeholder" | "email_duplicado"
    cliente_codigo: str,
    cliente_nome: str,
    detalhe: str,
    gravidade: str = "media",   # "alta" | "media" | "baixa"
) -> None:
    """Registra um alerta de qualidade de dados para revisão pelos superiores."""
    alertas = load_alertas()
    alertas.insert(0, {
        "tipo":           tipo,
        "codigo":         cliente_codigo,
        "nome":           cliente_nome,
        "detalhe":        detalhe,
        "gravidade":      gravidade,
        "registrado_em":  datetime.now().strftime("%d/%m/%Y %H:%M"),
        "resolvido":      False,
    })
    _save_alertas(alertas)


def resolver_alerta(index: int) -> None:
    alertas = load_alertas()
    if 0 <= index < len(alertas):
        alertas[index]["resolvido"] = True
        alertas[index]["resolvido_em"] = date.today().strftime("%d/%m/%Y")
        _save_alertas(alertas)


def alertas_pendentes() -> list:
    return [a for a in load_alertas() if not a.get("resolvido")]


def verificar_cliente_novo(codigo: str, nome: str, fone: str, email: str) -> list:
    """
    Verifica um cliente recém-importado contra as regras de qualidade.
    Retorna lista de alertas gerados (pode ser vazia).
    """
    novos = []

    # Verifica telefone bloqueado
    if fone:
        bloqueio = is_telefone_bloqueado(fone)
        if bloqueio:
            detalhe = (
                f"Telefone {fone} registrado como '{bloqueio['tipo']}' "
                f"({bloqueio.get('motivo', '')})"
            )
            registrar_alerta("telefone_bloqueado", codigo, nome, detalhe, "alta")
            novos.append(detalhe)

    return novos


def contar_alertas_hoje() -> int:
    hoje = date.today().strftime("%d/%m/%Y")
    return sum(
        1 for a in load_alertas()
        if not a.get("resolvido") and a.get("registrado_em", "").startswith(hoje)
    )
