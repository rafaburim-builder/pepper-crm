"""
cloud_storage.py — Adaptador de armazenamento local ↔ Supabase Storage.

Quando modo_cloud=True (Streamlit Cloud), os arquivos JSON são lidos e
gravados no Supabase Storage em vez do sistema de arquivos local.

Quando modo_cloud=False (instalação local), funciona exatamente como antes:
lê/grava arquivos locais — zero mudança no comportamento atual.

Arquivos gerenciados por este módulo:
  client_map.json, product_map.json, produto_map_meta.json,
  familias.json, loja_config.json, qualidade_alertas.json,
  fornecedor_lentes.json, prescricoes.json, funil.json,
  email_queue.json, email_queue_history.json, pos_venda_log.json,
  lgpd_optout.json, users.json

NÃO gerenciados (permanecem locais mesmo em modo_cloud):
  config.json (credenciais — fica nos secrets do Streamlit)
  pepper.db (SQLite — migração futura para Supabase Postgres)
  update_log.json (log de libs — irrelevante na nuvem)
"""
import json
import os
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_cloud() -> bool:
    """Detecta se está rodando no Streamlit Cloud."""
    try:
        import streamlit as st
        return st.secrets.get("app", {}).get("modo_cloud", False)
    except Exception:
        return False


def _get_supabase():
    """Retorna cliente Supabase configurado (lazy import)."""
    try:
        import streamlit as st
        from supabase import create_client
        sb_cfg = st.secrets.get("supabase", {})
        return create_client(sb_cfg["url"], sb_cfg["key"]), sb_cfg.get("bucket", "pepper-data")
    except Exception as e:
        raise RuntimeError(f"Supabase não configurado: {e}")


def _loja_prefix() -> str:
    """Retorna o prefixo de pasta da loja no Supabase (ex: 'porto_ferreira/')."""
    try:
        import streamlit as st
        loja_id = st.secrets.get("app", {}).get("loja_id", "default")
        return f"{loja_id}/"
    except Exception:
        return "default/"


def load_json(filename: str, default=None):
    """
    Carrega um arquivo JSON.
    Em modo cloud: lê do Supabase Storage.
    Em modo local: lê do filesystem (comportamento original).
    """
    if default is None:
        default = {}
    if not _is_cloud():
        path = os.path.join(ROOT, "data", filename)
        if not os.path.exists(path):
            return default
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    # Cloud: Supabase Storage
    try:
        sb, bucket = _get_supabase()
        obj_path   = _loja_prefix() + filename
        resp       = sb.storage.from_(bucket).download(obj_path)
        return json.loads(resp.decode("utf-8"))
    except Exception:
        return default


def save_json(filename: str, data) -> None:
    """
    Grava um arquivo JSON.
    Em modo cloud: escreve no Supabase Storage.
    Em modo local: escreve no filesystem.
    """
    content = json.dumps(data, ensure_ascii=False, indent=2)
    if not _is_cloud():
        path = os.path.join(ROOT, "data", filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return
    # Cloud: Supabase Storage
    sb, bucket = _get_supabase()
    obj_path   = _loja_prefix() + filename
    sb.storage.from_(bucket).upload(
        obj_path,
        content.encode("utf-8"),
        {"upsert": "true", "content-type": "application/json"},
    )


def sync_to_cloud(filename: str) -> bool:
    """
    Sobe um arquivo local para o Supabase Storage.
    Útil para migração inicial: executa uma vez para enviar os dados locais.
    Retorna True se bem-sucedido.
    """
    path = os.path.join(ROOT, "data", filename)
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _is_cloud_bak = True
        # Força modo cloud para este upload
        import streamlit as st
        sb_cfg = st.secrets.get("supabase", {})
        from supabase import create_client
        sb     = create_client(sb_cfg["url"], sb_cfg["key"])
        bucket = sb_cfg.get("bucket", "pepper-data")
        loja   = st.secrets.get("app", {}).get("loja_id", "default")
        obj    = f"{loja}/{filename}"
        sb.storage.from_(bucket).upload(
            obj,
            json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
            {"upsert": "true", "content-type": "application/json"},
        )
        return True
    except Exception as e:
        print(f"[cloud_storage] sync_to_cloud({filename}) falhou: {e}")
        return False


# Lista de arquivos que devem ser sincronizados na migração
SYNC_FILES = [
    "client_map.json",
    "product_map.json",
    "produto_map_meta.json",
    "familias.json",
    "loja_config.json",
    "qualidade_alertas.json",
    "fornecedor_lentes.json",
    "prescricoes.json",
    "funil.json",
    "email_queue.json",
    "lgpd_optout.json",
    "users.json",
]
