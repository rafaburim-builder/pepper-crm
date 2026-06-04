"""
email_sender.py — Disparo de e-mails via Brevo (ex-Sendinblue).

Configuração necessária: API key do Brevo em data/email_config.json
  {"brevo_api_key": "xkeysib-...", "sender_email": "seuemail@dominio.com", "sender_name": "Ótica P. Ferreira"}

Documentação Brevo Transactional API:
  POST https://api.brevo.com/v3/smtp/email

Uso:
  from modules.email_sender import BrevoClient
  client = BrevoClient.from_config()
  ok, msg = client.send_email("cliente@email.com", "Nome", "Assunto", "Corpo em texto")
"""

import json
import os
from typing import Optional, Tuple

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CFG_PATH = os.path.join(ROOT, "data", "email_config.json")

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def load_email_config() -> dict:
    """Carrega configuração de e-mail. Retorna {} se não configurado."""
    if not os.path.exists(_CFG_PATH):
        return {}
    try:
        with open(_CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_email_config(config: dict) -> None:
    os.makedirs(os.path.dirname(_CFG_PATH), exist_ok=True)
    with open(_CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def is_email_configured() -> bool:
    cfg = load_email_config()
    return bool(cfg.get("brevo_api_key") and cfg.get("sender_email"))


def _texto_para_html(texto: str) -> str:
    """Converte texto plano para HTML simples, remove links wa.me."""
    import re
    # Remove links WhatsApp
    texto = re.sub(r'https?://wa\.me/\S+', '', texto)
    # Parágrafos
    html = "".join(f"<p>{p.strip()}</p>" for p in texto.split("\n") if p.strip())
    return f"""
<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#1C1816;max-width:600px;margin:auto">
{html}
<br><p style="font-size:11px;color:#999">
Você está recebendo este e-mail por ser cliente da Ótica P. Ferreira.
</p>
</body></html>"""


class BrevoClient:
    def __init__(self, api_key: str, sender_email: str, sender_name: str):
        self.api_key     = api_key
        self.sender_email = sender_email
        self.sender_name  = sender_name

    @classmethod
    def from_config(cls) -> Optional["BrevoClient"]:
        """
        Cria client buscando credenciais em (ordem de prioridade):
          1. st.secrets["brevo"] — Streamlit Cloud / secrets.toml
          2. data/email_config.json — configuração local
        Retorna None se nenhuma fonte tiver API key.
        """
        # 1. st.secrets
        try:
            import streamlit as st
            brevo = st.secrets.get("brevo", {})
            if brevo.get("api_key"):
                return cls(
                    api_key      = brevo["api_key"],
                    sender_email = brevo.get("sender_email", ""),
                    sender_name  = brevo.get("sender_name", "Pepper CRM"),
                )
        except Exception:
            pass
        # 2. email_config.json
        cfg = load_email_config()
        if not cfg.get("brevo_api_key") or not cfg.get("sender_email"):
            return None
        return cls(
            api_key      = cfg["brevo_api_key"],
            sender_email = cfg["sender_email"],
            sender_name  = cfg.get("sender_name", "Ótica P. Ferreira"),
        )

    def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        body_text: str,
    ) -> Tuple[bool, str]:
        """
        Envia um e-mail via Brevo.

        Retorna (True, "") em caso de sucesso ou (False, mensagem_de_erro).
        """
        if not to_email or "@" not in to_email:
            return False, "E-mail inválido ou ausente."

        payload = {
            "sender":     {"name": self.sender_name, "email": self.sender_email},
            "to":         [{"email": to_email, "name": to_name}],
            "subject":    subject,
            "htmlContent": _texto_para_html(body_text),
            "textContent": body_text,
        }
        headers = {
            "accept":       "application/json",
            "content-type": "application/json",
            "api-key":      self.api_key,
        }
        try:
            resp = requests.post(_BREVO_URL, json=payload, headers=headers, timeout=15)
            if resp.status_code in (200, 201):
                return True, ""
            return False, f"Brevo {resp.status_code}: {resp.text[:120]}"
        except requests.Timeout:
            return False, "Timeout ao conectar ao Brevo."
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    def send_bulk(
        self,
        recipients: list,  # [{"email": str, "nome": str, "mensagem": str}]
        subject: str,
    ) -> dict:
        """
        Envia e-mails em lote.
        Retorna {"enviados": int, "falhas": int, "erros": [str]}.
        """
        enviados = 0
        falhas   = 0
        erros    = []
        for r in recipients:
            ok, msg = self.send_email(
                to_email   = r.get("email", ""),
                to_name    = r.get("nome", ""),
                subject    = subject,
                body_text  = r.get("mensagem", ""),
            )
            if ok:
                enviados += 1
            else:
                falhas += 1
                erros.append(f"{r.get('nome','?')}: {msg}")
        return {"enviados": enviados, "falhas": falhas, "erros": erros}


def test_connection(api_key: str, sender_email: str) -> Tuple[bool, str]:
    """Testa a conexão com o Brevo consultando informações da conta."""
    try:
        resp = requests.get(
            "https://api.brevo.com/v3/account",
            headers={"api-key": api_key, "accept": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            plan = data.get("plan", [{}])
            plan_name = plan[0].get("type", "—") if plan else "—"
            return True, f"Conta verificada — plano: {plan_name} | remetente: {sender_email}"
        return False, f"Brevo retornou {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return False, f"Erro de conexão: {e}"
