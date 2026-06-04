"""
user_profile.py — Perfil estendido do usuário.

Armazena em data/profiles.json:
  {login: {nome_completo, cpf, nascimento, endereco, telefone, email,
           avatar_tipo ("upload"|"galeria"|None), avatar_data (base64 ou slug)}}

O avatar pode ser:
  - "upload" + base64 da imagem (≤ 200KB após compressão)
  - "galeria" + slug do avatar escolhido (ex: "av_oculos_01")
  - None (usa iniciais do nome como fallback)
"""
import base64
import io
import json
import os
from datetime import date
from typing import Optional

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _get_path() -> str:
    try:
        from modules.data_dir import data_path
        return data_path("profiles.json")
    except Exception:
        return os.path.join(ROOT, "data", "profiles.json")


# ── Galeria de avatares pré-definidos ─────────────────────────────────────────
# Cada avatar é um emoji grande + cor de fundo
GALERIA_AVATARES = [
    {"slug": "av_oculos_01", "emoji": "👓", "bg": "#E84300", "label": "Óculos laranja"},
    {"slug": "av_oculos_02", "emoji": "🕶️", "bg": "#1C1816", "label": "Solar clássico"},
    {"slug": "av_star",      "emoji": "⭐", "bg": "#F59E0B", "label": "Estrela"},
    {"slug": "av_chilli",    "emoji": "🌶️", "bg": "#BF3700", "label": "Chilli"},
    {"slug": "av_camera",    "emoji": "📷", "bg": "#2563EB", "label": "Câmera"},
    {"slug": "av_rocket",    "emoji": "🚀", "bg": "#7C3AED", "label": "Foguete"},
    {"slug": "av_lion",      "emoji": "🦁", "bg": "#D97706", "label": "Leão"},
    {"slug": "av_diamond",   "emoji": "💎", "bg": "#0891B2", "label": "Diamante"},
    {"slug": "av_fire",      "emoji": "🔥", "bg": "#DC2626", "label": "Fogo"},
    {"slug": "av_trophy",    "emoji": "🏆", "bg": "#059669", "label": "Troféu"},
    {"slug": "av_lightning", "emoji": "⚡", "bg": "#7C3AED", "label": "Raio"},
    {"slug": "av_crown",     "emoji": "👑", "bg": "#B45309", "label": "Coroa"},
]


# ── CRUD ──────────────────────────────────────────────────────────────────────

def _load() -> dict:
    path = _get_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _cloud_sync(data: dict) -> None:
    try:
        from modules.cloud_storage import save_json as _csave, _is_cloud
        if _is_cloud():
            _csave("profiles.json", data)
    except Exception:
        pass


def _save(data: dict) -> None:
    path = _get_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except (PermissionError, OSError):
        pass
    _cloud_sync(data)   # auto-sync Supabase


def get_profile(login: str) -> dict:
    return _load().get(login, {})


def save_profile(
    login: str,
    nome_completo: str = "",
    nome_social: str = "",
    cpf: str = "",
    nascimento: str = "",
    telefone: str = "",
    email: str = "",
    endereco: dict = None,
    avatar_tipo: str = None,
    avatar_data: str = None,
) -> None:
    profiles = _load()
    existing = profiles.get(login, {})
    profiles[login] = {
        **existing,
        "nome_completo": nome_completo or existing.get("nome_completo", ""),
        "nome_social":   nome_social   if nome_social is not None else existing.get("nome_social", ""),
        "cpf":           cpf           or existing.get("cpf", ""),
        "nascimento":    nascimento     or existing.get("nascimento", ""),
        "telefone":      telefone       or existing.get("telefone", ""),
        "email":         email          or existing.get("email", ""),
        "endereco":      endereco       or existing.get("endereco", {}),
        "avatar_tipo":   avatar_tipo    if avatar_tipo is not None else existing.get("avatar_tipo"),
        "avatar_data":   avatar_data    if avatar_data is not None else existing.get("avatar_data"),
        "atualizado_em": date.today().strftime("%d/%m/%Y"),
    }
    _save(profiles)


def is_profile_complete(login: str) -> tuple:
    """Retorna (completo: bool, campos_faltando: list)."""
    p = get_profile(login)
    obrigatorios = {
        "nome_completo": "Nome completo",
        "cpf":           "CPF",
        "nascimento":    "Data de nascimento",
        "telefone":      "Telefone",
        "email":         "E-mail",
    }
    faltando = [label for key, label in obrigatorios.items() if not p.get(key, "").strip()]
    return len(faltando) == 0, faltando


def compress_avatar(image_bytes: bytes, max_size_kb: int = 200) -> str:
    """Comprime a imagem e retorna base64. Lança ValueError se muito grande."""
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")
    # Redimensiona para no máximo 256x256
    img.thumbnail((256, 256), Image.LANCZOS)
    buf = io.BytesIO()
    quality = 85
    while True:
        buf.seek(0); buf.truncate()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= max_size_kb * 1024 or quality <= 20:
            break
        quality -= 10
    return base64.b64encode(buf.getvalue()).decode()


def get_avatar_html(login: str, size: int = 36) -> str:
    """Retorna HTML do avatar (foto ou galeria ou iniciais)."""
    p = get_profile(login)
    tipo = p.get("avatar_tipo")
    data = p.get("avatar_data", "")

    if tipo == "upload" and data:
        return (
            f'<img src="data:image/jpeg;base64,{data}" '
            f'style="width:{size}px;height:{size}px;border-radius:50%;object-fit:cover;" '
            f'alt="avatar">'
        )
    if tipo == "galeria" and data:
        av = next((a for a in GALERIA_AVATARES if a["slug"] == data), None)
        if av:
            return (
                f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
                f'background:{av["bg"]};display:flex;align-items:center;justify-content:center;'
                f'font-size:{int(size*0.55)}px;line-height:1;">{av["emoji"]}</div>'
            )
    # Fallback: iniciais
    nome = p.get("nome_completo", login)
    iniciais = "".join(w[0].upper() for w in nome.split()[:2]) or "?"
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
        f'background:#E84300;display:flex;align-items:center;justify-content:center;'
        f'color:white;font-weight:700;font-size:{int(size*0.42)}px;">{iniciais}</div>'
    )
