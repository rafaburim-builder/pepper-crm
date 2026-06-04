"""
reset_tokens.py — Tokens de recuperação de senha com validade de 2h e uso único.

Fluxo:
  1. create_token(login, email)  → gera token UUID, salva em reset_tokens.json
  2. validate_token(token)       → verifica se existe, não expirou, não foi usado
                                   retorna dict {login, email} ou levanta ValueError
  3. consume_token(token)        → marca como usado (invalida para futuros acessos)

Tokens expiram em 2h e só podem ser consumidos uma única vez.
Armazena em data/reset_tokens.json (sincronizado no Supabase).
"""

import json
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EXPIRY_HOURS = 2


def _get_path() -> str:
    try:
        from modules.data_dir import data_path
        return data_path("reset_tokens.json")
    except Exception:
        return os.path.join(ROOT, "data", "reset_tokens.json")


def _load() -> dict:
    path = _get_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    path = _get_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except (PermissionError, OSError):
        pass
    # Auto-sync Supabase
    try:
        from modules.cloud_storage import save_json as _cs, _is_cloud
        if _is_cloud():
            _cs("reset_tokens.json", data)
    except Exception:
        pass


def _purge_expired(tokens: dict) -> dict:
    """Remove tokens expirados para manter o arquivo limpo."""
    now = datetime.now()
    return {
        k: v for k, v in tokens.items()
        if datetime.fromisoformat(v["expiry"]) > now
    }


def create_token(login: str, email: str) -> str:
    """
    Cria e persiste um token de recuperação. Retorna o token (str URL-safe).
    Remove tokens antigos do mesmo login antes de criar o novo.
    """
    token  = secrets.token_urlsafe(32)
    expiry = (datetime.now() + timedelta(hours=_EXPIRY_HOURS)).isoformat()

    tokens = _load()
    tokens = _purge_expired(tokens)

    # Remove tokens antigos do mesmo login
    tokens = {k: v for k, v in tokens.items() if v.get("login") != login}

    tokens[token] = {
        "login":   login,
        "email":   email,
        "expiry":  expiry,
        "used":    False,
        "created": datetime.now().isoformat(),
    }
    _save(tokens)
    return token


def validate_token(token: str) -> dict:
    """
    Valida o token. Retorna {login, email} se válido.
    Levanta ValueError com mensagem amigável se inválido/expirado/usado.
    """
    tokens = _load()
    entry  = tokens.get(token)

    if not entry:
        raise ValueError("Link inválido ou já expirado. Solicite um novo link.")

    if entry.get("used"):
        raise ValueError(
            "Este link já foi utilizado. Por segurança, cada link funciona apenas uma vez.\n"
            "Solicite um novo link de recuperação."
        )

    expiry = datetime.fromisoformat(entry["expiry"])
    if datetime.now() > expiry:
        raise ValueError(
            f"Link expirado. Os links têm validade de {_EXPIRY_HOURS}h.\n"
            "Solicite um novo link de recuperação."
        )

    return {"login": entry["login"], "email": entry["email"]}


def consume_token(token: str) -> None:
    """Marca o token como usado. Deve ser chamado logo após redefinir a senha."""
    tokens = _load()
    if token in tokens:
        tokens[token]["used"] = True
        _save(tokens)


def get_login_by_email(email: str) -> Optional[str]:
    """Busca o login de um usuário pelo e-mail cadastrado no perfil."""
    try:
        from modules.user_profile import get_profile
        from modules.auth import list_users
        email_lower = email.strip().lower()
        for u in list_users():
            login = u.get("login", "")
            p = get_profile(login)
            if p.get("email", "").lower() == email_lower:
                return login
    except Exception:
        pass
    return None


def app_base_url() -> str:
    """Retorna a URL base do app (Streamlit Cloud ou localhost)."""
    try:
        import streamlit as st
        # No Streamlit Cloud, a URL está nos headers da sessão
        headers = st.context.headers if hasattr(st, 'context') else {}
        host = headers.get("host", "")
        if host and "localhost" not in host:
            proto = "https"
            return f"{proto}://{host}"
    except Exception:
        pass
    return "http://localhost:8501"
