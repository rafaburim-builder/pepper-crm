"""
secure_store.py — Armazenamento de segredos FORA da pasta sincronizada (OneDrive).

Motivação (auditoria de segurança 29/05/2026 — builder):
  data/config.json ficava em uma pasta do OneDrive e continha, em texto puro, o
  token do Microvix, o certificado digital A1 (.pfx) e a senha do certificado.
  Qualquer pessoa com acesso ao arquivo/Conta OneDrive poderia assinar documentos
  fiscais em nome da empresa.

Solução:
  Os campos sensíveis passam a ser gravados em um arquivo LOCAL da máquina,
  fora do OneDrive (por padrão %LOCALAPPDATA%\\Pepper\\secrets.json no Windows).
  O config.json sincronizado mantém apenas configurações não-sensíveis; os
  campos sensíveis ficam vazios nele.

Princípios de robustez (app em produção):
  • Tudo é "best-effort": se o cofre local não puder ser lido/escrito, o
    config.py volta ao comportamento antigo (segredo no config.json) — NUNCA
    quebra o app nem perde o certificado.
  • Escrita atômica (tmp + os.replace).
  • Local do cofre pode ser sobrescrito por variável de ambiente PEPPER_SECRETS_DIR
    (útil para servidor/testes).
"""
import json
import os
import tempfile

# Campos que NUNCA devem ser persistidos no config.json sincronizado.
SENSITIVE_KEYS = ("token", "sefaz_cert_b64", "sefaz_cert_password")


def secrets_dir() -> str:
    """Diretório do cofre local (fora do OneDrive). Cria se necessário."""
    override = os.environ.get("PEPPER_SECRETS_DIR")
    if override:
        base = override
    else:
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), ".pepper"
        )
        base = os.path.join(base, "Pepper")
    os.makedirs(base, exist_ok=True)
    return base


def secrets_path() -> str:
    return os.path.join(secrets_dir(), "secrets.json")


def load_secrets() -> dict:
    """Lê o cofre local. Retorna {} se não existir ou em qualquer erro."""
    try:
        path = secrets_path()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_secrets(secrets: dict) -> bool:
    """Grava o cofre local de forma atômica. Retorna True se gravou com sucesso."""
    try:
        path = secrets_path()
        directory = os.path.dirname(path)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".secrets-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(secrets, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
        # Best-effort: restringe permissões (no Windows tem efeito limitado;
        # o ajuste forte de ACL é feito 1x via icacls na migração).
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return True
    except Exception:
        return False


def split_disk(full: dict) -> dict:
    """Retorna uma cópia de `full` com os campos sensíveis esvaziados
    (o que deve ir para o config.json sincronizado)."""
    on_disk = dict(full)
    for k in SENSITIVE_KEYS:
        if k in on_disk:
            on_disk[k] = ""
    return on_disk


def has_plaintext(full: dict) -> bool:
    """True se algum campo sensível tem valor preenchido (ainda em texto puro)."""
    return any(full.get(k) for k in SENSITIVE_KEYS)
