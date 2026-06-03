"""
data_dir.py — Resolve o diretório de dados correto para leitura/escrita.

Local:  <ROOT>/data/  (padrão — comportamento original)
Cloud:  /tmp/pepper-data/  (Streamlit Cloud monta o repo como read-only;
        os arquivos são baixados do Supabase para este diretório writable
        na inicialização do app)

Uso nos módulos:
    from modules.data_dir import data_path
    _PATH = data_path("users.json")
"""
import os

_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCAL  = os.path.join(_ROOT, "data")
_CLOUD  = "/tmp/pepper-data"
_ENV_KEY = "PEPPER_DATA_DIR"


def get_data_dir() -> str:
    """Retorna o diretório de dados activo."""
    d = os.environ.get(_ENV_KEY)
    if d:
        os.makedirs(d, exist_ok=True)
        return d
    return _LOCAL


def data_path(filename: str) -> str:
    """Retorna o caminho completo para um arquivo de dados."""
    return os.path.join(get_data_dir(), filename)


def init_cloud_data_dir() -> bool:
    """
    Chamado UMA VEZ no startup do app quando em modo cloud.
    1. Cria /tmp/pepper-data/
    2. Baixa todos os arquivos JSON do Supabase para lá
    3. Define PEPPER_DATA_DIR no environment
    Retorna True se inicializado com sucesso.
    """
    try:
        import streamlit as st
        if not st.secrets.get("app", {}).get("modo_cloud", False):
            return False   # modo local — não faz nada
    except Exception:
        return False

    os.makedirs(_CLOUD, exist_ok=True)
    os.environ[_ENV_KEY] = _CLOUD

    # Baixa arquivos do Supabase
    FILES = [
        "client_map.json", "produto_map.json", "produto_map_meta.json",
        "familias.json", "loja_config.json", "qualidade_alertas.json",
        "fornecedor_lentes.json", "prescricoes.json", "funil.json",
        "email_queue.json", "email_queue_history.json",
        "pos_venda_log.json", "lgpd_optout.json", "users.json",
    ]
    try:
        import streamlit as st
        from supabase import create_client
        sb_cfg = st.secrets.get("supabase", {})
        sb     = create_client(sb_cfg["url"], sb_cfg["key"])
        bucket = sb_cfg.get("bucket", "pepper-data")
        loja   = st.secrets.get("app", {}).get("loja_id", "default")

        downloaded = 0
        for fname in FILES:
            dest = os.path.join(_CLOUD, fname)
            if os.path.exists(dest):
                downloaded += 1
                continue   # já baixado nesta sessão
            try:
                content = sb.storage.from_(bucket).download(f"{loja}/{fname}")
                with open(dest, "wb") as f:
                    f.write(content)
                downloaded += 1
            except Exception:
                pass   # arquivo não existe no Supabase ainda — ok
        return True
    except Exception:
        return True   # diretório criado, mesmo sem Supabase
