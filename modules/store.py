"""
store.py — Gestão de lojas, redes e atribuições por hierarquia.

Estrutura de dados (data/stores.json):
  {
    "loja_id": {
      "id":           str,
      "nome":         str,
      "cnpj":         str,
      "endereco":     dict,
      "rede_id":      str | None,
      "configurada":  bool,         # True = passou pelo wizard de onboarding
      "microvix": {
        "token":        str,         # armazenado no cofre secure_store por loja
        "cnpj_emp":     str,
        "nome_empresa": str,
        "base_url":     str,
      },
      "atribuicoes": {
        "login_usuario": "perfil"   # ex: "rafaburim": "admin"
      },
      "criada_em": str,
    }
  }

Estrutura de redes (data/redes.json):
  {
    "rede_id": {
      "id":        str,
      "nome":      str,        # ex: "Rede Rafa Óticas"
      "logo_b64":  str | None, # logo da rede em base64
      "admin_login": str,      # login do Admin responsável
    }
  }
"""
import json
import os
from datetime import date
from typing import Optional, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_path(filename: str) -> str:
    try:
        from modules.data_dir import data_path
        return data_path(filename)
    except Exception:
        return os.path.join(ROOT, "data", filename)


def _load(filename: str) -> dict:
    path = _get_path(filename)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _cloud_sync(filename: str, data: dict) -> None:
    try:
        from modules.cloud_storage import save_json as _csave, _is_cloud
        if _is_cloud():
            _csave(filename, data)
    except Exception:
        pass


def _save_file(filename: str, data: dict) -> None:
    path = _get_path(filename)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except (PermissionError, OSError):
        pass
    _cloud_sync(filename, data)   # auto-sync Supabase


# ── Redes ─────────────────────────────────────────────────────────────────────

def load_redes() -> dict:
    return _load("redes.json")

def save_rede(rede_id: str, nome: str, logo_b64: str = None, admin_login: str = "") -> None:
    redes = load_redes()
    redes[rede_id] = {
        "id":          rede_id,
        "nome":        nome,
        "logo_b64":    logo_b64,
        "admin_login": admin_login,
        "criada_em":   date.today().strftime("%d/%m/%Y"),
    }
    _save_file("redes.json", redes)

def get_rede(rede_id: str) -> Optional[dict]:
    return load_redes().get(rede_id)

def get_rede_do_admin(admin_login: str) -> Optional[dict]:
    for r in load_redes().values():
        if r.get("admin_login") == admin_login:
            return r
    return None


# ── Lojas ─────────────────────────────────────────────────────────────────────

def load_stores() -> dict:
    return _load("stores.json")

def save_store(loja: dict) -> None:
    stores = load_stores()
    stores[loja["id"]] = loja
    _save_file("stores.json", stores)

def get_store(loja_id: str) -> Optional[dict]:
    return load_stores().get(loja_id)

def create_store(
    loja_id: str,
    nome: str,
    cnpj: str,
    rede_id: str = None,
    endereco: dict = None,
) -> dict:
    loja = {
        "id":          loja_id,
        "nome":        nome,
        "cnpj":        cnpj,
        "rede_id":     rede_id,
        "endereco":    endereco or {},
        "configurada": False,
        "microvix":    {"token": "", "cnpj_emp": "", "nome_empresa": "", "base_url": ""},
        "atribuicoes": {},
        "criada_em":   date.today().strftime("%d/%m/%Y"),
    }
    save_store(loja)
    return loja


# ── Atribuições usuário ↔ loja ────────────────────────────────────────────────

def get_lojas_do_usuario(login: str) -> List[dict]:
    """Retorna as lojas às quais este usuário está atribuído."""
    stores = load_stores()
    return [
        s for s in stores.values()
        if login in s.get("atribuicoes", {})
    ]

def atribuir_usuario(loja_id: str, login: str, perfil: str) -> bool:
    """Atribui um usuário a uma loja com um perfil."""
    loja = get_store(loja_id)
    if not loja:
        return False
    loja.setdefault("atribuicoes", {})[login] = perfil
    save_store(loja)
    return True

def remover_atribuicao(loja_id: str, login: str) -> bool:
    loja = get_store(loja_id)
    if not loja:
        return False
    loja.get("atribuicoes", {}).pop(login, None)
    save_store(loja)
    return True

def get_perfil_na_loja(loja_id: str, login: str) -> Optional[str]:
    loja = get_store(loja_id)
    if not loja:
        return None
    return loja.get("atribuicoes", {}).get(login)

def todas_as_lojas_do_admin(admin_login: str) -> List[dict]:
    """Admin vê todas as lojas da sua rede."""
    rede = get_rede_do_admin(admin_login)
    if not rede:
        return get_lojas_do_usuario(admin_login)
    return [s for s in load_stores().values() if s.get("rede_id") == rede["id"]]


# ── Credenciais Microvix por loja ─────────────────────────────────────────────

def set_microvix_config(loja_id: str, token: str, cnpj_emp: str,
                        nome_empresa: str, base_url: str = "") -> bool:
    loja = get_store(loja_id)
    if not loja:
        return False
    loja["microvix"] = {
        "token":        token,
        "cnpj_emp":     cnpj_emp,
        "nome_empresa": nome_empresa,
        "base_url":     base_url or "https://webapi.microvix.com.br/1.0/api/integracao",
    }
    save_store(loja)
    return True

def get_microvix_config(loja_id: str) -> dict:
    loja = get_store(loja_id)
    if not loja:
        return {}
    return loja.get("microvix", {})

def marcar_configurada(loja_id: str) -> None:
    loja = get_store(loja_id)
    if loja:
        loja["configurada"] = True
        save_store(loja)


# ── Verificação de permissão para criar usuário em loja ──────────────────────

def pode_criar_usuario_na_loja(criador_login: str, criador_perfil: str,
                                 loja_id: str, novo_perfil: str) -> tuple:
    """
    Verifica se o criador pode adicionar um usuário com novo_perfil na loja.
    Retorna (pode: bool, motivo: str).
    """
    from modules.auth import NIVEL

    loja = get_store(loja_id)
    if not loja:
        return False, "Loja não encontrada."

    # Verifica se o criador está atribuído a essa loja (exceto Dev e Admin que veem tudo)
    if criador_perfil not in ("dev", "admin"):
        if criador_login not in loja.get("atribuicoes", {}):
            return False, "Você não tem acesso a esta loja."

    # Regras de quem pode criar quem
    criador_nivel = NIVEL.get(criador_perfil, 0)
    novo_nivel    = NIVEL.get(novo_perfil, 0)
    if criador_nivel <= novo_nivel:
        return False, f"Você ({criador_perfil}) não pode criar um usuário de nível {novo_perfil}."

    # Gerente e vendedor não criam usuários
    if criador_perfil in ("gerente", "vendedor", "captador"):
        return False, "Seu perfil não tem permissão para criar usuários."

    # Gerente só pode ter 1 por loja
    if novo_perfil == "gerente":
        gerentes_na_loja = [l for l, p in loja.get("atribuicoes", {}).items() if p == "gerente"]
        if gerentes_na_loja:
            return False, f"Esta loja já tem um gerente ({gerentes_na_loja[0]})."

    return True, ""
