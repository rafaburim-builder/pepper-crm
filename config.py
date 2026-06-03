import json
import os

# ── Leitura de secrets do Streamlit Cloud ────────────────────────────────────────
# Quando o app roda no Streamlit Cloud (modo_cloud=True nos secrets), as credenciais
# vêm de st.secrets e NÃO do config.json local (que não existe na nuvem).
# Em modo local, st.secrets não está disponível e este bloco é ignorado silenciosamente.
def _read_cloud_secrets() -> dict:
    """Retorna credenciais do st.secrets se em modo cloud, {} caso contrário."""
    try:
        import streamlit as st
        if not st.secrets.get("app", {}).get("modo_cloud", False):
            return {}
        mx   = st.secrets.get("microvix", {})
        app  = st.secrets.get("app", {})
        return {
            "token":        mx.get("token", ""),
            "cnpj":         mx.get("cnpj", ""),
            "nome_empresa": mx.get("nome_empresa", ""),
            "base_url":     mx.get("base_url", "https://webapi.microvix.com.br/1.0/api/integracao"),
            "modo_demo":    app.get("modo_demo", False),
            "_modo_cloud":  True,
        }
    except Exception:
        return {}

_CLOUD_SECRETS = _read_cloud_secrets()

# ── Cofre de segredos fora do OneDrive (auditoria de segurança 29/05/2026) ──────
# Importação defensiva: se falhar, o Config opera em modo legado (segredos no
# config.json) e NADA quebra.
try:
    import sys as _sys
    _ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
    if _ROOT_DIR not in _sys.path:
        _sys.path.insert(0, _ROOT_DIR)
    from modules import secure_store
    _SECURE = True
except Exception:
    secure_store = None
    _SECURE = False

_BASE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_BASE, "data")
_FILE = os.path.join(_DATA, "config.json")

_DEFAULT_TIERS = [
    {"label": "Econômico",     "min": 0,   "max": 200},
    {"label": "Básico",        "min": 200, "max": 300},
    {"label": "Intermediário", "min": 300, "max": 400},
    {"label": "Premium",       "min": 400, "max": 500},
    {"label": "Luxo",          "min": 500, "max": 99999},
]

_DEFAULT_ESTOQUE_IDEAL = {
    "LV": 20,   # Armações de Grau
    "OC": 15,   # Óculos Solar
    "ML": 10,   # Armações Multi
}


class Config:
    def __init__(self):
        os.makedirs(_DATA, exist_ok=True)
        self._d = self._load()

    @staticmethod
    def _write_config_file(data: dict) -> None:
        """Grava o config.json de forma atômica. Quando o cofre seguro está
        disponível, os campos sensíveis vão VAZIOS para o disco (ficam só no
        cofre local, fora do OneDrive)."""
        on_disk = secure_store.split_disk(data) if _SECURE else dict(data)
        tmp = _FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(on_disk, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _FILE)

    def _load(self):
        _defaults = {
            "token": "",
            "cnpj": "",
            "nome_empresa": "",
            "base_url": "https://webapi.microvix.com.br/1.0/api/integracao",
            "modo_demo": True,
            "faixas_preco": _DEFAULT_TIERS,
            "estoque_ideal": _DEFAULT_ESTOQUE_IDEAL,
            "estoque_virtual": {"LV": 0, "OC": 0, "ML": 0},
            "sug_faixas_saved": None,
        }

        # ── Modo cloud: credenciais vêm do st.secrets ─────────────────────────
        if _CLOUD_SECRETS:
            data = dict(_defaults)
            data.update(_CLOUD_SECRETS)
            # Tenta carregar configurações não-sensíveis do Supabase (ex: faixas_preco)
            try:
                from modules.cloud_storage import load_json
                _cfg_cloud = load_json("config_operacional.json", {})
                for k, v in _cfg_cloud.items():
                    if k not in ("token", "cnpj", "nome_empresa", "base_url"):
                        data[k] = v
            except Exception:
                pass
            return data

        if os.path.exists(_FILE):
            with open(_FILE, encoding="utf-8") as f:
                data = json.load(f)
            # Preenche chaves novas que podem faltar em configs existentes
            changed = False
            for k, v in _defaults.items():
                if k not in data:
                    data[k] = v
                    changed = True

            # ── Segredos: migra texto-puro -> cofre local e sobrepõe na memória ──
            if _SECURE:
                try:
                    secrets = secure_store.load_secrets()
                    if secure_store.has_plaintext(data):
                        # config.json ainda tem segredo em texto puro: move p/ cofre
                        moved = dict(secrets)
                        for k in secure_store.SENSITIVE_KEYS:
                            if data.get(k):
                                moved[k] = data[k]
                        if secure_store.save_secrets(moved):
                            secrets = moved
                            changed = True   # força reescrita do config.json já limpo
                    # sobrepõe segredos do cofre na config em memória
                    for k in secure_store.SENSITIVE_KEYS:
                        if secrets.get(k):
                            data[k] = secrets[k]
                except Exception:
                    pass  # qualquer falha: mantém comportamento legado

            if changed:
                try:
                    self._write_config_file(data)
                except Exception:
                    # fallback total: grava do jeito antigo para não perder nada
                    with open(_FILE, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
            return data

        # config.json ainda não existe — sobrepõe segredos do cofre, se houver
        data = dict(_defaults)
        if _SECURE:
            try:
                secrets = secure_store.load_secrets()
                for k in secure_store.SENSITIVE_KEYS:
                    if secrets.get(k):
                        data[k] = secrets[k]
            except Exception:
                pass
        return data

    def save(self):
        # 1) grava segredos no cofre local (fora do OneDrive), se disponível
        stored_ok = False
        if _SECURE:
            try:
                secrets = secure_store.load_secrets()
                for k in secure_store.SENSITIVE_KEYS:
                    secrets[k] = self._d.get(k, "")   # espelha o estado atual
                stored_ok = secure_store.save_secrets(secrets)
            except Exception:
                stored_ok = False

        # 2) grava config.json — limpo se os segredos foram guardados; senão, legado
        try:
            if stored_ok:
                self._write_config_file(self._d)   # campos sensíveis vão vazios
            else:
                tmp = _FILE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._d, f, ensure_ascii=False, indent=2)
                os.replace(tmp, _FILE)
        except Exception:
            # último recurso: escrita direta (comportamento original)
            with open(_FILE, "w", encoding="utf-8") as f:
                json.dump(self._d, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        return self._d.get(key, default)

    def set(self, key, value):
        self._d[key] = value

    @property
    def modo_demo(self):
        return self._d.get("modo_demo", True)

    @property
    def is_configured(self):
        return all([self._d.get("token"), self._d.get("cnpj"), self._d.get("nome_empresa")])
