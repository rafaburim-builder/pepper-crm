"""
auth.py — Autenticação e hierarquia de perfis do Pepper.

Hierarquia (nível numérico, maior = mais acesso):
  6  dev        — Rafael Burim; único; acesso total + painel de sistema
  5  admin      — Franqueado; acesso total à(s) sua(s) loja(s)
  4  supervisor — Gerência regional; leitura de N lojas, sem Configurações
  3  gerente    — Responsável por uma loja; operação completa
  2  vendedor   — Vê só sua carteira e sua fila diária
  1  captador   — Foco em captação: Bom Dia + registro de visitas

Senha padrão para novos usuários: pepper{ano_atual}
  Ex: pepper2026 — deve ser trocada no primeiro login.

Armazena em data/users.json (senhas com sha256).
"""
import hashlib
import json
import os
import re
from datetime import date, datetime
from typing import Optional

def _get_path() -> str:
    try:
        from modules.data_dir import data_path
        return data_path("users.json")
    except Exception:
        _r = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(_r, "data", "users.json")

# Hierarquia: nome do perfil → nível numérico
NIVEL = {
    "dev":        6,
    "admin":      5,
    "supervisor": 4,
    "gerente":    3,
    "vendedor":   2,
    "captador":   1,
}
PERFIS = list(NIVEL.keys())   # ordem da hierarquia

# Labels para exibição
PERFIL_LABEL = {
    "dev":        "Dev",
    "admin":      "Admin (Franqueado)",
    "supervisor": "Supervisor",
    "gerente":    "Gerente",
    "vendedor":   "Vendedor",
    "captador":   "Captador",
}

PERFIL_ICON = {
    "dev":        "🛠️",
    "admin":      "🏢",
    "supervisor": "👔",
    "gerente":    "🏪",
    "vendedor":   "🛍️",
    "captador":   "🎯",
}


def _hash(senha: str) -> str:
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def senha_padrao() -> str:
    """Retorna a senha padrão do ano atual: pepper{ano}"""
    return f"pepper{date.today().year}"


def _load() -> list:
    path = _get_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(users: list) -> None:
    path = _get_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except (PermissionError, OSError):
        pass   # Cloud: read-only filesystem — dados já estão no Supabase


def ensure_default_admin() -> bool:
    """
    Cria usuário dev padrão se não houver nenhum usuário.
    Login: admin | Senha: pepper{ano} | Perfil: gerente
    (Rafael deve trocar para dev e criar seu login próprio na primeira execução)
    """
    users = _load()
    if users:
        return False
    users.append({
        "login":                "admin",
        "nome":                 "Administrador",
        "senha_hash":           _hash(senha_padrao()),
        "perfil":               "gerente",
        "cod_vendedor_microvix": "",
        "loja":                 "",
        "ativo":                True,
        "primeiro_acesso":      True,
        "criado_em":            datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    _save(users)
    return True


def authenticate(login: str, senha: str) -> Optional[dict]:
    """Retorna o usuário autenticado ou None se falha."""
    users = _load()
    h = _hash(senha)
    for u in users:
        if (u.get("login") == login.strip()
                and u.get("senha_hash") == h
                and u.get("ativo", True)):
            return u
    return None


def change_password(login: str, nova_senha: str) -> bool:
    users = _load()
    for u in users:
        if u.get("login") == login:
            u["senha_hash"]      = _hash(nova_senha)
            u["primeiro_acesso"] = False
            _save(users)
            return True
    return False


def list_users() -> list:
    return _load()


def create_user(
    login: str,
    nome: str,
    perfil: str,
    cod_vendedor_microvix: str = "",
    loja: str = "",
    senha: Optional[str] = None,
) -> tuple:
    """
    Cria usuário com senha padrão pepper{ano} e primeiro_acesso=True.
    Retorna (True, "") ou (False, mensagem_erro).
    """
    if perfil not in PERFIS:
        return False, f"Perfil inválido: '{perfil}'. Use: {', '.join(PERFIS)}"
    if not re.match(r"^\w{3,30}$", login):
        return False, "Login deve ter entre 3 e 30 caracteres alfanuméricos/underscore."
    users = _load()
    if any(u["login"] == login for u in users):
        return False, f"Login '{login}' já existe."
    users.append({
        "login":                login,
        "nome":                 nome,
        "senha_hash":           _hash(senha or senha_padrao()),
        "perfil":               perfil,
        "cod_vendedor_microvix": cod_vendedor_microvix,
        "loja":                 loja,
        "ativo":                True,
        "primeiro_acesso":      True,
        "criado_em":            datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    _save(users)
    return True, ""


def toggle_user(login: str, ativo: bool) -> bool:
    users = _load()
    for u in users:
        if u.get("login") == login:
            u["ativo"] = ativo
            _save(users)
            return True
    return False


def update_user(login: str, **kwargs) -> bool:
    """Atualiza campos de um usuário (nome, perfil, loja, cod_vendedor_microvix)."""
    allowed = {"nome", "perfil", "loja", "cod_vendedor_microvix"}
    users = _load()
    for u in users:
        if u.get("login") == login:
            for k, v in kwargs.items():
                if k in allowed:
                    u[k] = v
            _save(users)
            return True
    return False


# ── Helpers de permissão ──────────────────────────────────────────────────────

def nivel(user: Optional[dict]) -> int:
    """Retorna o nível numérico do usuário (0 se None)."""
    if not user:
        return 0
    return NIVEL.get(user.get("perfil", ""), 0)


def can(user: Optional[dict], min_perfil: str) -> bool:
    """Retorna True se o usuário tem nível >= o perfil mínimo exigido."""
    return nivel(user) >= NIVEL.get(min_perfil, 0)


def is_dev(user: Optional[dict]) -> bool:
    return nivel(user) >= NIVEL["dev"]


def is_admin(user: Optional[dict]) -> bool:
    return nivel(user) >= NIVEL["admin"]


def is_supervisor(user: Optional[dict]) -> bool:
    return nivel(user) >= NIVEL["supervisor"]


def is_gerente(user: Optional[dict]) -> bool:
    return nivel(user) >= NIVEL["gerente"]


def is_vendedor(user: Optional[dict]) -> bool:
    return nivel(user) >= NIVEL["vendedor"]


def cod_vendedor_do_usuario(user: Optional[dict]) -> str:
    return str(user.get("cod_vendedor_microvix", "") or "") if user else ""


def perfil_display(user: Optional[dict]) -> str:
    if not user:
        return "—"
    p = user.get("perfil", "")
    icon  = PERFIL_ICON.get(p, "")
    label = PERFIL_LABEL.get(p, p.capitalize())
    return f"{icon} {label}"


def perfis_criáveis_por(user: Optional[dict]) -> list:
    """Retorna a lista de perfis que este usuário pode criar."""
    nv = nivel(user)
    if nv >= NIVEL["dev"]:
        return PERFIS                              # dev cria qualquer um
    if nv >= NIVEL["admin"]:
        return ["supervisor","gerente","vendedor","captador"]
    if nv >= NIVEL["gerente"]:
        return ["vendedor","captador"]
    return []
