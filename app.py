"""
Pepper — Análise e Sugestão de Compras  v1.8.8
Chilli Beans · Óticas
Rodado com: streamlit run app.py
"""
# ── Cloud init (PRIMEIRO bloco de qualquer coisa) ─────────────────────────────
# Redireciona I/O para /tmp quando em Streamlit Cloud (repo read-only).
try:
    from modules.data_dir import init_cloud_data_dir as _init_cloud
    _init_cloud()
except Exception:
    pass

import base64
import json
import math
import os
import sys
from datetime import date, datetime, timedelta
from io import BytesIO

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

print("[Pepper] streamlit importado OK", flush=True)

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from api.microvix import (
    MicrovixAPI, MicrovixAPIError,
    mock_compras, mock_estoque, mock_inventario, mock_retorno, mock_vendas,
    mock_sales_header, mock_seller_goals, mock_nfe,
)
from api.sefaz import SefazClient, SefazError
from config import Config
from modules.db import Database
from modules.price_pyramid import (
    build_category_summary,
    build_pyramid_summary,
    pyramid_from_data,
)
from modules.client_map import (
    import_from_csv as import_client_csv,
    import_from_api_data as import_client_api,
    load_clients, load_client_meta, save_clients,
)
from modules.product_map import import_from_df, import_from_api_data as import_product_api, load_map
from modules.marketing import (
    load_campaigns, save_campaigns,
    format_message, make_whatsapp_link,
    DEFAULT_TEMPLATE,
)
from modules.rfm import score_rfm, segment_summary, SEGMENT_COLORS
from modules.lens_brands import detect_brand, BRAND_COLORS as LENS_BRAND_COLORS, ALL_BRANDS as LENS_ALL_BRANDS

# ── Logo SVG inline (dedo-de-moça 3D — ilustração) ─────────────────────────
_LOGO_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 210" width="52" height="109">
  <defs>
    <linearGradient id="pepper_g1" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="#640000"/>
      <stop offset="18%"  stop-color="#BF1010"/>
      <stop offset="40%"  stop-color="#EE2E2E"/>
      <stop offset="58%"  stop-color="#CB0F0F"/>
      <stop offset="82%"  stop-color="#9D0707"/>
      <stop offset="100%" stop-color="#580000"/>
    </linearGradient>
    <linearGradient id="pepper_g2" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="#194E19"/>
      <stop offset="50%"  stop-color="#389438"/>
      <stop offset="100%" stop-color="#194E19"/>
    </linearGradient>
  </defs>
  <!-- Stem -->
  <path d="M50 48 Q55 32 64 28 Q62 38 54 47"
        fill="url(#pepper_g2)" stroke="#124012" stroke-width="1.5"/>
  <!-- 5 sepals (calyx) -->
  <path d="M50 54 L47 36 Q50 30 53 36 Z" fill="#2B8B2B" stroke="#196019" stroke-width="0.7"/>
  <path d="M50 54 L32 40 Q30 35 36 38 Z"  fill="#268226" stroke="#196019" stroke-width="0.7"/>
  <path d="M50 54 L28 57 Q27 52 32 52 Z"  fill="#2B8B2B" stroke="#196019" stroke-width="0.7"/>
  <path d="M50 54 L72 57 Q73 52 68 52 Z"  fill="#268226" stroke="#196019" stroke-width="0.7"/>
  <path d="M50 54 L68 40 Q70 35 64 38 Z"  fill="#2B8B2B" stroke="#196019" stroke-width="0.7"/>
  <!-- Calyx disk -->
  <ellipse cx="50" cy="54" rx="12" ry="5"  fill="#2D8A2D"/>
  <ellipse cx="48" cy="52" rx="7"  ry="2.5" fill="#46BB46" opacity="0.50"/>
  <!-- Drop shadow (offset copy) -->
  <path d="M44 54 C40 70,38 97,38 127 C38 150,43 170,50 192 C57 170,62 150,62 127 C62 97,60 70,56 54 Z"
        fill="#360000" opacity="0.28" transform="translate(5,7)"/>
  <!-- Pepper body -->
  <path d="M44 54 C40 70,38 97,38 127 C38 150,43 170,50 192 C57 170,62 150,62 127 C62 97,60 70,56 54 Z"
        fill="url(#pepper_g1)" stroke="#800000" stroke-width="1.2"/>
  <!-- Wide glow (left side) -->
  <path d="M41 66 C37 82,36 106,36 130 C36 149,39 165,44 178"
        fill="none" stroke="rgba(255,140,140,0.26)" stroke-width="9" stroke-linecap="round"/>
  <!-- Narrow specular highlight -->
  <path d="M41 68 C38 84,37 108,37 132 C37 150,40 166,45 178"
        fill="none" stroke="rgba(255,255,255,0.50)" stroke-width="2" stroke-linecap="round"/>
  <!-- Specular dot near top -->
  <ellipse cx="41" cy="76" rx="2.8" ry="5" fill="rgba(255,255,255,0.36)" transform="rotate(-10,41,76)"/>
  <!-- Tip glow -->
  <ellipse cx="50" cy="189" rx="4" ry="2.5" fill="rgba(255,100,100,0.48)"/>
</svg>
"""

# ── Page setup ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Pepper · Chilli Beans",
    page_icon="🌶️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── PWA + Meta tags mobile ────────────────────────────────────────────────────
st.markdown("""
<link rel="manifest" href="/app/static/manifest.json">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Pepper">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<link rel="apple-touch-icon" href="/app/static/icon-192.png">
""", unsafe_allow_html=True)

# ── CSS mobile (injeta antes do render) ──────────────────────────────────────
try:
    from modules.mobile_ui import inject_mobile_css
    inject_mobile_css()
except Exception:
    pass

st.markdown("""
<style>
  /* ── Google Fonts: Poppins ── */
  @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap');

  html, body, [class*="css"], button, input, select, textarea {
      font-family: 'Poppins', sans-serif !important;
  }

  /* ── Main background ── */
  [data-testid="stAppViewContainer"] > .main { background-color: #FAFAF5; }
  [data-testid="stHeader"] { background-color: #FAFAF5; }

  /* ── Sidebar — laranja vibrante ── */
  [data-testid="stSidebar"] {
      background: linear-gradient(175deg, #E84300 0%, #C04000 100%) !important;
  }
  [data-testid="stSidebar"] * { color: #FFFFFF !important; }
  [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.30) !important; }
  [data-testid="stSidebar"] [data-testid="stRadio"] label {
      background: rgba(255,255,255,0.10);
      border-radius: 8px;
      padding: 4px 10px;
      margin-bottom: 2px;
      transition: background .15s;
  }
  [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
      background: rgba(255,255,255,0.22) !important;
  }
  [data-testid="stSidebar"] [aria-checked="true"] {
      background: rgba(255,255,255,0.28) !important;
      font-weight: 700 !important;
  }

  /* ── Buttons ── */
  div.stButton > button:first-child {
      background-color: #E84300 !important;
      color: white !important;
      border: none !important;
      font-weight: 600 !important;
      border-radius: 8px !important;
      font-family: 'Poppins', sans-serif !important;
  }
  div.stButton > button:first-child:hover { background-color: #BF3700 !important; }

  /* ── Page title / subtitle ── */
  .cb-title {
      color: #E84300;
      font-weight: 800;
      font-size: 1.85rem;
      line-height: 1.1;
      font-family: 'Poppins', sans-serif;
      letter-spacing: -0.5px;
  }
  .cb-sub {
      color: #7A6A5A;
      font-size: 0.88rem;
      margin-bottom: 1.2rem;
      font-family: 'Poppins', sans-serif;
  }
  .section-title {
      color: #1C1816;
      font-weight: 700;
      font-size: 1.1rem;
      margin-top: 0.6rem;
      font-family: 'Poppins', sans-serif;
  }

  /* ── Status pills ── */
  .pill-demo { display:inline-block; background:rgba(255,255,255,0.25); color:#fff;
               padding:2px 12px; border-radius:12px; font-size:.72rem; font-weight:700;
               border: 1px solid rgba(255,255,255,0.5); }
  .pill-live { display:inline-block; background:#15803d; color:#fff;
               padding:2px 12px; border-radius:12px; font-size:.72rem; font-weight:700; }
  .pill-warn { display:inline-block; background:rgba(0,0,0,0.25); color:#fff;
               padding:2px 12px; border-radius:12px; font-size:.72rem; font-weight:700; }

  /* ── Metrics ── */
  [data-testid="stMetricValue"] { font-size: 1.15rem !important; color: #1C1816 !important;
                                   font-family: 'Poppins', sans-serif !important; font-weight: 700 !important; }
  [data-testid="stMetricLabel"] { color: #7A6A5A !important; font-size: .80rem !important; }

  /* ── Remove tooltip "Press Enter to submit form" em todos os campos ── */
  [data-testid="InputInstructions"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ── R3: Auth — inicializa usuários padrão e verifica sessão ──────────────────
from modules.auth import (
    ensure_default_admin, authenticate, change_password,
    list_users, create_user, toggle_user, update_user,
    is_dev, is_admin, is_supervisor, is_gerente, is_vendedor,
    can, nivel, perfil_display, perfis_criáveis_por,
    cod_vendedor_do_usuario, PERFIL_ICON, PERFIL_LABEL, senha_padrao,
    save_remembered_login, get_remembered_login, clear_remembered_login,
    get_auto_login, get_user_by_login,
)
ensure_default_admin()   # cria admin/pepper2026 na primeira execução

if "auth_user" not in st.session_state:
    st.session_state["auth_user"] = None

# ── Auto-login silencioso (sessão caiu por navegação mas "lembrar" está ativo) ─
if st.session_state["auth_user"] is None:
    _rl = get_remembered_login()
    if _rl and get_auto_login():
        _ral_user = get_user_by_login(_rl)
        if _ral_user:
            st.session_state["auth_user"] = _ral_user
            st.rerun()

if st.session_state["auth_user"] is None:
    from modules.user_profile import get_avatar_html as _gav
    from modules.reset_tokens import (
        create_token as _rt_create, validate_token as _rt_validate,
        consume_token as _rt_consume, get_login_by_email as _rt_by_email,
        app_base_url as _rt_base_url,
    )

    _sp         = senha_padrao()
    _remembered = get_remembered_login()
    _auto_ok    = get_auto_login() and bool(_remembered)

    # ── Handler de ?reset=TOKEN (link de recuperação) ─────────────────────────
    _reset_token = st.query_params.get("reset", "")
    if _reset_token:
        st.query_params.clear()
        st.session_state["_reset_token_pending"] = _reset_token

    if st.session_state.get("_reset_token_pending"):
        _tok = st.session_state["_reset_token_pending"]
        st.markdown(
            '<div style="max-width:400px;margin:80px auto;">'
            '<div style="text-align:center;margin-bottom:28px;">'
            '<span style="font-size:2.2rem;font-weight:900;color:#E84300;">🌶️ Pepper</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        try:
            _tok_info = _rt_validate(_tok)
            st.markdown("### 🔑 Criar nova senha")
            st.caption(f"Conta: **{_tok_info['login']}**")
            _np1 = st.text_input("Nova senha (mín. 6 caracteres)", type="password", key="reset_p1")
            _np2 = st.text_input("Confirmar nova senha", type="password", key="reset_p2")
            if st.button("💾 Salvar nova senha", type="primary", use_container_width=True):
                if len(_np1) < 6:
                    st.error("A senha deve ter pelo menos 6 caracteres.")
                elif _np1 != _np2:
                    st.error("As senhas não coincidem.")
                else:
                    change_password(_tok_info["login"], _np1)
                    _rt_consume(_tok)
                    del st.session_state["_reset_token_pending"]
                    st.success("✅ Senha redefinida com sucesso! Faça login.")
                    st.rerun()
        except ValueError as _ve:
            st.error(str(_ve))
            if st.button("← Voltar ao login"):
                del st.session_state["_reset_token_pending"]
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        st.stop()

    # ── Modo: Esqueci a senha ─────────────────────────────────────────────────
    if st.session_state.get("_show_forgot"):
        st.markdown(
            '<div style="max-width:380px;margin:80px auto;">'
            '<div style="text-align:center;margin-bottom:28px;">'
            '<span style="font-size:2.2rem;font-weight:900;color:#E84300;">🌶️ Pepper</span><br>'
            '<span style="font-size:.85rem;color:#7A6A5A;">Recuperação de senha</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown("Digite seu **e-mail** ou **login** cadastrado:")
        _forgot_input = st.text_input("E-mail ou login", placeholder="seuemail@exemplo.com  ou  seu.login", key="forgot_email")

        _fc1, _fc2 = st.columns(2)
        with _fc1:
            if st.button("Enviar link", type="primary", use_container_width=True, key="btn_send_reset"):
                _raw = _forgot_input.strip()
                if not _raw:
                    st.error("Preencha o campo.")
                else:
                    # Resolve login + e-mail de destino
                    _login_found  = None
                    _email_destino = ""

                    if "@" in _raw:
                        # Busca por e-mail no perfil
                        _login_found   = _rt_by_email(_raw.lower())
                        _email_destino = _raw.lower()
                    else:
                        # Busca direta por login
                        _u_found = get_user_by_login(_raw)
                        if _u_found:
                            _login_found = _u_found["login"]
                            # Pega e-mail do perfil
                            from modules.user_profile import get_profile as _gprof
                            _email_destino = _gprof(_login_found).get("email", "").strip()

                    if not _login_found:
                        st.success("Se esse cadastro existir, você receberá o link em instantes.")
                    else:
                        _tok_new  = _rt_create(_login_found, _email_destino or _raw)
                        _base_url = _rt_base_url()
                        _link     = f"{_base_url}/?reset={_tok_new}"

                        from modules.email_sender import BrevoClient as _BC
                        _brevo = _BC.from_config()

                        if _brevo and _brevo.api_key and _email_destino:
                            _body = (
                                f"Olá!\n\n"
                                f"Recebemos uma solicitação de recuperação de senha para sua conta no Pepper CRM.\n\n"
                                f"Clique no link abaixo para criar uma nova senha (válido por 2 horas, uso único):\n\n"
                                f"{_link}\n\n"
                                f"Se você não solicitou a recuperação, ignore este e-mail.\n\n"
                                f"Pepper CRM — Chilli Beans"
                            )
                            _ok, _err = _brevo.send_email(
                                to_email=_email_destino, to_name=_login_found,
                                subject="Recuperação de senha — Pepper CRM",
                                body_text=_body,
                            )
                            if _ok:
                                st.success("✅ Link enviado! Verifique sua caixa de entrada.")
                            else:
                                st.warning(f"Falha no envio ({_err}). Copie o link:")
                                st.code(_link)
                        else:
                            # Sem e-mail no perfil ou Brevo não configurado: exibe link
                            st.info("Link de recuperação (copie e acesse):")
                            st.code(_link)
                            st.caption("Válido por 2 horas · uso único")
        with _fc2:
            if st.button("← Voltar", use_container_width=True, key="btn_back_forgot"):
                del st.session_state["_show_forgot"]
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)
        st.stop()

    # ── Cabeçalho da tela de login ────────────────────────────────────────────
    st.markdown(
        '<div style="max-width:380px;margin:60px auto 0;">'
        '<div style="text-align:center;margin-bottom:32px;">'
        '<span style="font-size:2.5rem;font-weight:900;color:#E84300;">🌶️ Pepper</span><br>'
        '<span style="font-size:.9rem;color:#7A6A5A;font-weight:500;">Chilli Beans · CRM</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    if _auto_ok:
        # ── MODO AUTO-LOGIN: avatar centralizado + botão de um clique ─────────
        _av_lg    = _gav(_remembered, size=80)
        _user_obj = get_user_by_login(_remembered)
        _nome_auto = (_user_obj or {}).get("nome", _remembered)

        # Centraliza o avatar com flex
        st.markdown(
            '<div style="display:flex;flex-direction:column;align-items:center;'
            'text-align:center;margin-bottom:20px;">'
            + _av_lg
            + '<div style="margin:12px 0 4px;font-size:1.1rem;font-weight:700;color:#1C1816;">'
            + _nome_auto
            + '</div>'
            '<div style="font-size:.75rem;color:#9E8E7E;">Toque para entrar</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        if st.button("Entrar", type="primary", use_container_width=True, key="btn_autologin"):
            _u = get_user_by_login(_remembered)
            if _u:
                st.session_state["auth_user"] = _u
                st.rerun()
            else:
                st.error("Usuário não encontrado. Use login e senha.")

        _ca, _cb = st.columns(2)
        with _ca:
            if st.button("Usar outra conta", use_container_width=True, key="btn_outra_conta"):
                clear_remembered_login()
                st.rerun()
        with _cb:
            if st.button("Esqueci a senha", use_container_width=True, key="btn_forgot_auto"):
                st.session_state["_show_forgot"] = True
                st.rerun()

    else:
        # ── MODO NORMAL: formulário com login + senha ─────────────────────────
        if _remembered:
            _av_sm = _gav(_remembered, size=48)
            st.markdown(
                '<div style="display:flex;flex-direction:column;align-items:center;'
                'margin-bottom:16px;">'
                '<div style="display:inline-flex;flex-direction:column;align-items:center;'
                'gap:6px;background:#F8F4F0;border-radius:12px;padding:12px 24px;">'
                + _av_sm
                + '<span style="font-size:.8rem;font-weight:600;color:#1C1816;">'
                + _remembered + '</span>'
                '<span style="font-size:.68rem;color:#9E8E7E;">Login salvo</span>'
                '</div></div>',
                unsafe_allow_html=True,
            )

        with st.form("login_form"):
            _login_in    = st.text_input("Login", value=_remembered, placeholder="seu.login")
            _senha_in    = st.text_input("Senha", type="password", placeholder="••••••")
            _remember_me = st.checkbox("Lembrar meu login neste dispositivo", value=bool(_remembered))
            _submit      = st.form_submit_button("Entrar →", type="primary", width="stretch")

        st.markdown(
            f'<p style="text-align:center;font-size:.75rem;color:#9E8E7E;margin-top:4px;">'
            f'Primeiro acesso? Senha padrão: <b>{_sp}</b></p>',
            unsafe_allow_html=True,
        )

        if st.button("Esqueci a senha", key="btn_forgot_normal", use_container_width=False):
            st.session_state["_show_forgot"] = True
            st.rerun()

        if _submit:
            _user = authenticate(_login_in.strip(), _senha_in)
            if _user:
                save_remembered_login(_login_in.strip(), auto_login=_remember_me)
                if not _remember_me:
                    clear_remembered_login()
                st.session_state["auth_user"] = _user
                st.rerun()
            else:
                st.error("Login ou senha incorretos.")

    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# Usuário autenticado — atalho global
_auth_user = st.session_state["auth_user"]

# ── Timeout de inatividade: 2 horas ──────────────────────────────────────────
import time as _time
_TIMEOUT_SEGUNDOS = 7200   # 2 h
_agora_ts = _time.time()
_ultima_at = st.session_state.get("_last_activity", _agora_ts)
if _agora_ts - _ultima_at > _TIMEOUT_SEGUNDOS:
    st.session_state["auth_user"] = None
    st.session_state.pop("_last_activity", None)
    st.warning("⏱️ Sua sessão expirou por inatividade. Faça login novamente.")
    st.rerun()
st.session_state["_last_activity"] = _agora_ts

# ── Troca de senha obrigatória no primeiro acesso ─────────────────────────────
if _auth_user.get("primeiro_acesso"):
    _sp2 = senha_padrao()
    _p_display = perfil_display(_auth_user)
    st.markdown(
        f'<div style="max-width:420px;margin:60px auto;">'
        f'<div style="text-align:center;margin-bottom:20px;">'
        f'<span style="font-size:1.8rem;">🔑</span><br>'
        f'<b style="font-size:1.1rem;">Bem-vindo, {_auth_user["nome"]}!</b><br>'
        f'<span style="color:#7A6A5A;font-size:.85rem;">{_p_display}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.info(
        f"Sua senha atual é a padrão **`{_sp2}`**.  \n"
        "Por segurança, escolha uma senha pessoal antes de continuar."
    )
    with st.form("change_pw_form"):
        _np1 = st.text_input("Nova senha (mín. 6 caracteres)", type="password")
        _np2 = st.text_input("Confirmar nova senha", type="password")
        _ok  = st.form_submit_button("💾 Salvar e entrar", type="primary", width="stretch")
    st.markdown('</div>', unsafe_allow_html=True)

    if _ok:
        if len(_np1) < 6:
            st.error("A senha deve ter pelo menos 6 caracteres.")
        elif _np1 != _np2:
            st.error("As senhas não coincidem. Tente novamente.")
        elif _np1 == _sp2:
            st.error(f"A nova senha não pode ser igual à senha padrão `{_sp2}`.")
        else:
            change_password(_auth_user["login"], _np1)
            _auth_user["primeiro_acesso"] = False
            st.session_state["auth_user"] = _auth_user
            st.success("✅ Senha definida com sucesso!")
            st.rerun()
    st.stop()

# ── State init ────────────────────────────────────────────────────────────────
for _k, _v in [
    ("cfg",             None),
    ("df_vendas",       None),
    ("df_compras",      None),
    ("df_estoque",      None),
    ("sug_faixas",      None),
    ("autoload_done",   False),
    ("product_map",     None),
    ("client_map",      None),
    ("df_retorno",      None),
    ("retorno_ts",      ""),
    ("campaigns",       None),
    ("vendas_loaded_at", None),
    ("ret_camp_prev",   ""),
    # v1.6.0 — novos relatórios
    ("df_vendedores",   None),
    ("df_metas",        None),
    ("df_nfe",          None),
    # v1.7.0
    ("df_inventario",   None),
    ("lens_meta",       None),
    # v1.8.4 — Tela de Bom Dia
    ("_bom_dia_feitos", set()),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

if st.session_state.cfg is None:
    st.session_state.cfg = Config()
if st.session_state.product_map is None:
    st.session_state.product_map = load_map()
if st.session_state.client_map is None:
    st.session_state.client_map = load_clients()
if st.session_state.campaigns is None:
    st.session_state.campaigns = load_campaigns()

cfg = st.session_state.cfg
db  = Database()

# ══════════════════════════════════════════════════════════════════════════════
# ALERTAS DE STARTUP — verificações críticas de segurança/validade
# Executam uma vez por sessão; pushs persistem até admin clicar "Estou ciente"
# ══════════════════════════════════════════════════════════════════════════════

# ── A) Aviso de rotação do token Microvix (apenas após 6 meses do 1º uso) ────
# token_last_rotation e token_configured_at são salvos em loja_config.json
# (sincronizado no Supabase) para persistir entre sessões no Cloud.
if cfg.is_configured and not cfg.modo_demo and not st.session_state.get("_token_warn_dismissed"):
    try:
        import json as _jcfg_mod
        _loja_cfg_path = __import__('modules.data_dir', fromlist=['data_path']).data_path("loja_config.json")
        try:
            with open(_loja_cfg_path, encoding="utf-8") as _lf:
                _loja_cfg = _jcfg_mod.load(_lf)
        except Exception:
            _loja_cfg = {}

        _rot    = _loja_cfg.get("token_last_rotation", "")
        _conf_at = _loja_cfg.get("token_configured_at", "")

        # Primeira vez: apenas registra a data de configuração, sem aviso
        if not _conf_at and not _rot:
            _loja_cfg["token_configured_at"] = date.today().strftime("%d/%m/%Y")
            try:
                with open(_loja_cfg_path, "w", encoding="utf-8") as _lf:
                    _jcfg_mod.dump(_loja_cfg, _lf, ensure_ascii=False, indent=2)
            except Exception:
                pass
        else:
            # Só avisa se já tem 180+ dias desde a última rotação (ou da configuração inicial)
            _ref_date_str = _rot or _conf_at
            try:
                _ref_dt = datetime.strptime(_ref_date_str, "%d/%m/%Y")
                if (datetime.now() - _ref_dt).days >= 180:
                    st.warning(
                        "🔑 **Rotação do token Microvix recomendada.**  \n"
                        f"Última rotação/configuração: **{_ref_date_str}** — há mais de 6 meses.  \n"
                        "Acesse o painel **admin do Microvix → Integrações → Chave de API**, "
                        "gere um novo token e atualize em ⚙️ Configurações → Credenciais."
                    )
                    _tc1, _tc2 = st.columns([2, 5])
                    with _tc1:
                        if st.button("✅ Estou ciente", key="dismiss_token_warn"):
                            _loja_cfg["token_last_rotation"] = date.today().strftime("%d/%m/%Y")
                            try:
                                with open(_loja_cfg_path, "w", encoding="utf-8") as _lf:
                                    _jcfg_mod.dump(_loja_cfg, _lf, ensure_ascii=False, indent=2)
                            except Exception:
                                pass
                            st.session_state["_token_warn_dismissed"] = True
                            st.rerun()
            except Exception:
                pass
    except Exception:
        pass

# ── B) Push de expiração do Certificado A1 (aviso 4 semanas antes) ───────────
_cert_b64 = cfg.get("sefaz_cert_b64", "")
if _cert_b64 and not st.session_state.get("_cert_warn_dismissed"):
    try:
        import base64 as _b64m
        from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates as _load_pfx
        from cryptography.hazmat.backends import default_backend as _def_back
        _pfx   = _b64m.b64decode(_cert_b64)
        _senha = (cfg.get("sefaz_cert_senha") or "").encode()
        _, _cert_obj, _ = _load_pfx(_pfx, _senha, _def_back())
        _exp = getattr(_cert_obj, "not_valid_after_utc", None)
        if _exp is None:
            from datetime import timezone as _tz
            _exp = _cert_obj.not_valid_after.replace(tzinfo=_tz.utc)
        from datetime import timezone as _tzz
        _dias_cert = (_exp - datetime.now(_tzz.utc)).days
        if _dias_cert <= 28:
            _cor  = "🔴" if _dias_cert <= 7 else ("🟡" if _dias_cert <= 14 else "⚠️")
            st.error(
                f"{_cor} **CERTIFICADO DIGITAL A1 VENCE EM {_dias_cert} DIA(S)!**  \n"
                f"Data de vencimento: **{_exp.strftime('%d/%m/%Y')}**  \n"
                "Solicite a reemissão na sua Autoridade Certificadora (AC) **antes do vencimento** — "
                "após expirar, a consulta de NF-e na SEFAZ fica bloqueada. "
                "Depois atualize o arquivo .pfx em ⚙️ Configurações → Credenciais."
            )
            _cc1, _cc2 = st.columns([2, 5])
            with _cc1:
                if st.button("✅ Estou ciente", key="dismiss_cert_warn"):
                    st.session_state["_cert_warn_dismissed"] = True
                    st.rerun()
    except Exception:
        pass

# ── Auto-load ─────────────────────────────────────────────────────────────────
if not st.session_state.autoload_done and not cfg.modo_demo and cfg.is_configured:
    _dt_ini = str(date.today() - timedelta(days=365))
    _dt_fim = str(date.today())
    with st.spinner("🌶️ Conectando ao Microvix e carregando dados..."):
        try:
            _api = MicrovixAPI(
                token=cfg.get("token"), cnpj=cfg.get("cnpj"),
                nome_empresa=cfg.get("nome_empresa"), base_url=cfg.get("base_url"),
            )
            _pmap = st.session_state.product_map
            st.session_state.df_vendas  = _api.get_sales(_dt_ini, _dt_fim, _pmap)
            st.session_state.df_compras = _api.get_purchases(_dt_ini, _dt_fim, _pmap)
            st.session_state.df_vendedores = st.session_state.df_vendas
            try:
                st.session_state.df_metas = _api.get_seller_daily_goals(_dt_ini, _dt_fim)
            except MicrovixAPIError:
                st.session_state.df_metas = pd.DataFrame()
            st.session_state.vendas_loaded_at = datetime.now()
        except MicrovixAPIError as e:
            st.error(f"Não foi possível carregar dados automaticamente: {e}")
        finally:
            st.session_state.autoload_done = True

# ── Dados globais de usuário + rede ───────────────────────────────────────────
from modules.store import get_rede_do_admin, get_lojas_do_usuario
from modules.user_profile import get_avatar_html
_au   = st.session_state.get("auth_user", {})
_p    = _au.get("perfil", "")
_rede = get_rede_do_admin(_au.get("login","")) if _p in ("admin","dev") else None
_rede_nome    = _rede["nome"] if _rede else "Chilli Beans · CRM"
_label_perfil = PERFIL_LABEL.get(_p, _p.capitalize())
_avatar_html  = get_avatar_html(_au.get("login",""), size=32)
_avatar_html_lg = get_avatar_html(_au.get("login",""), size=52)
_nome_first   = (_au.get("nome","") or "?").split()[0]
_lojas_user   = get_lojas_do_usuario(_au.get("login",""))
_loja_dd      = _lojas_user[0]["nome"] if _lojas_user else (_rede_nome if _p in ("admin","dev") else "")

# ── Navegação filtrada por hierarquia ─────────────────────────────────────────
_nav = ["🌄  Bom Dia"]
if can(_au, "gerente") or can(_au, "vendedor"):
    _nav.append("📊  Análise de Contexto")
if can(_au, "supervisor"):
    _nav.append("📋  Relatórios")
if st.session_state.client_map and (can(_au, "gerente") or can(_au, "vendedor")):
    _nav.append("🎯  Campanhas Ativas")
if can(_au, "gerente"):
    _nav.append("📣  Marketing")
if can(_au, "gerente") and st.session_state.client_map:
    _nav.append("🗺️  Cobertura")
if can(_au, "admin"):
    _nav.append("⚙️  Configurações")

# ── CSS global: oculta sidebar + estilos da top bar fixa laranja ─────────────
st.markdown("""
<style>
[data-testid="stSidebar"],
[data-testid="collapsedControl"],
[data-testid="stHeader"] { display: none !important; }

/* Empurra o conteúdo abaixo da top bar */
.main .block-container {
  padding-top: 62px !important;
  padding-left: 1rem !important;
  padding-right: 1rem !important;
}

/* ── TOP BAR HTML (logo + user dropdown) ── */
.pepper-topbar {
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 52px;
  background: #E84300;
  display: flex;
  align-items: center;
  justify-content: space-between;
  z-index: 9999;
  box-shadow: 0 2px 6px rgba(0,0,0,.2);
  font-family: 'Poppins', sans-serif;
  overflow: visible;
  pointer-events: none;   /* deixa cliques passarem para o radio abaixo */
}
.pepper-topbar .ptb-logo,
.pepper-topbar .ptb-user-wrap { pointer-events: all; }

.ptb-logo {
  display: flex; align-items: center; gap: 8px;
  padding: 0 16px 0 14px;
  white-space: nowrap; flex-shrink: 0;
  height: 100%;
}
.ptb-logo b     { font-size: 1rem; font-weight: 900; color: white; letter-spacing: -.5px; }
.ptb-logo small { font-size: .58rem; color: rgba(255,255,255,.75); display: block; }

/* ── Navegação st.radio posicionada na barra laranja ── */
/* O radio fica logo abaixo do topo mas com margem negativa entra na barra */
div[data-testid="stRadio"] {
  position: fixed !important;
  top: 0 !important;
  left: 220px !important;
  right: 160px !important;
  height: 52px !important;
  z-index: 10000 !important;
  display: flex !important;
  align-items: center !important;
}
div[data-testid="stRadio"] > div {
  display: flex !important;
  align-items: center !important;
  gap: 2px !important;
  flex-wrap: nowrap !important;
}
div[data-testid="stRadio"] label {
  color: rgba(255,255,255,.85) !important;
  background: transparent !important;
  border: none !important;
  border-radius: 6px !important;
  padding: 6px 10px !important;
  font-size: 1.2rem !important;
  cursor: pointer !important;
  transition: background .15s !important;
  white-space: nowrap !important;
}
div[data-testid="stRadio"] label:hover {
  background: rgba(0,0,0,.12) !important;
  color: white !important;
}
div[data-testid="stRadio"] label[data-selected="true"],
div[data-testid="stRadio"] label[aria-checked="true"] {
  background: rgba(0,0,0,.2) !important;
  color: white !important;
  font-weight: 700 !important;
}
/* Esconde TUDO relacionado ao indicador circular do radio */
div[data-testid="stRadio"] input[type="radio"]      { display: none !important; }
div[data-testid="stRadio"] label > div:first-child  { display: none !important; }
div[data-testid="stRadio"] [role="radio"]            { display: none !important; }
div[data-testid="stRadio"] [data-baseweb="radio"]
  > div:first-child                                  { display: none !important; }
div[data-testid="stRadio"] label {
  padding-left: 6px !important;   /* remove o espaço que sobrava do círculo */
}

/* Esconde a barra/spinner de "pensando" durante reruns */
[data-testid="stStatusWidget"]      { display: none !important; }
[data-testid="stToolbar"]           { display: none !important; }
div.stSpinner                       { display: none !important; }
div[data-testid="stSpinner"]        { display: none !important; }

/* Botão do usuário */
.ptb-user-wrap {
  position: relative; flex-shrink: 0; margin-left: auto;
  padding: 0 12px; height: 100%;
  display: flex; align-items: center;
  border-left: 1px solid rgba(255,255,255,.2);
}
.ptb-user-btn {
  display: flex; align-items: center; gap: 8px;
  background: rgba(0,0,0,.14); border: none; border-radius: 8px;
  padding: 5px 12px; cursor: pointer;
  color: white; font-family: 'Poppins',sans-serif;
  font-size: .82rem; font-weight: 600; white-space: nowrap;
  transition: background .15s;
}
.ptb-user-btn:hover  { background: rgba(0,0,0,.22); }
.ptb-user-btn:focus  { outline: none; background: rgba(0,0,0,.25); }
.ptb-av {
  width: 26px; height: 26px; border-radius: 50%;
  background: rgba(255,255,255,.3);
  display: flex; align-items: center; justify-content: center;
  font-size: .68rem; font-weight: 800; color: white; flex-shrink: 0;
}
/* Dropdown — abre com :focus-within (puro CSS, sem JavaScript) */
.ptb-dd {
  display: none; position: absolute;
  top: calc(100% + 4px); right: 0;
  min-width: 240px; background: white;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,.16);
  border: 1px solid #EBE5DE;
  z-index: 10001; overflow: hidden;
}
.ptb-user-wrap:focus-within .ptb-dd { display: block; }
.ptb-dd-head { display: flex; align-items: center; gap: 12px; padding: 14px 16px 12px; background: #FDF8F5; }
.ptb-dd-av   { width: 42px; height: 42px; border-radius: 50%; background: #E84300; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: .95rem; font-weight: 800; color: white; }
.ptb-dd-nome { font-size: .87rem; font-weight: 700; color: #1C1816; white-space: nowrap; }
.ptb-dd-sub  { font-size: .7rem; color: #7A6A5A; white-space: nowrap; }
.ptb-dd-loja { font-size: .68rem; color: #9E8E7E; white-space: nowrap; }
.ptb-dd-sep  { height: 1px; background: #EBE5DE; margin: 2px 0; }
.ptb-dd-btn  { display: flex; align-items: center; gap: 10px; width: 100%; padding: 11px 16px; background: none; border: none; text-align: left; font-size: .83rem; font-family: 'Poppins',sans-serif; color: #1C1816; cursor: pointer; white-space: nowrap; transition: background .1s; text-decoration: none; box-sizing: border-box; }
.ptb-dd-btn:hover   { background: #F8F4F0; color: #1C1816; }
.ptb-dd-btn.danger  { color: #DC2626; }
.ptb-dd-btn.danger:hover { background: #FEF2F2; color: #DC2626; }

@media (max-width: 768px) {
  .pepper-topbar { display: none !important; }
  .main .block-container { padding-top: 8px !important; }
}
</style>
""", unsafe_allow_html=True)

# ── Roteamento: ?nav=N determina a página ─────────────────────────────────────
_qp_page = st.query_params.get("page", "")
_qp_nav  = st.query_params.get("nav",  "")

if _qp_page == "sair":
    st.query_params.clear()
    st.session_state["auth_user"] = None
    # Desativa auto-login para que o logout seja efetivo
    _rl_sair = get_remembered_login()
    if _rl_sair:
        save_remembered_login(_rl_sair, auto_login=False)
    st.rerun()
elif _qp_page == "perfil":
    st.query_params.clear()
    st.session_state["_show_perfil"] = True
elif _qp_page == "senha":
    st.query_params.clear()
    st.session_state["_show_senha"] = True

# ── Top bar: logo + user dropdown (HTML estático) ────────────────────────────
_initials = "".join(w[0].upper() for w in (_au.get("nome") or "?").split()[:2]) or "?"
_loja_row = ('<div class="ptb-dd-loja">🏪 ' + _loja_dd + '</div>') if _loja_dd else ''

st.markdown(
    '<div class="pepper-topbar">'
    + '<div class="ptb-logo">'
        '<span style="font-size:1.4rem;flex-shrink:0;">🌶️</span>'
        '<div><b>Pepper</b><small>' + _rede_nome + '</small></div>'
    '</div>'
    + '<div class="ptb-user-wrap">'
        '<button class="ptb-user-btn">'
          '<div class="ptb-av">' + _initials + '</div>'
          + _nome_first + ' ▾'
        '</button>'
        '<div class="ptb-dd">'
          '<div class="ptb-dd-head">'
            '<div class="ptb-dd-av">' + _initials + '</div>'
            '<div>'
              '<div class="ptb-dd-nome">' + (_au.get('nome') or '') + '</div>'
              '<div class="ptb-dd-sub">' + _label_perfil + '</div>'
              + _loja_row +
            '</div>'
          '</div>'
          '<div class="ptb-dd-sep"></div>'
          '<a href="?page=perfil" target="_self" class="ptb-dd-btn">✏️  Editar perfil</a>'
          '<a href="?page=senha"  target="_self" class="ptb-dd-btn">🔑  Trocar senha</a>'
          '<div class="ptb-dd-sep"></div>'
          '<a href="?page=sair"   target="_self" class="ptb-dd-btn danger">🚪  Sair</a>'
        '</div>'
    '</div>'
    + '</div>',
    unsafe_allow_html=True,
)

# ── Navegação com st.radio (nativo Streamlit — não perde sessão) ──────────────
# Só emojis como rótulos para caber na barra laranja
_nav_icons = [n.strip().split()[0] for n in _nav]          # ["🌄","📊","📋",...]
_nav_labels_full = [" ".join(n.strip().split()[1:]) for n in _nav]  # ["Bom Dia",...]

_nav_sel = st.radio(
    "nav",
    _nav_icons,
    horizontal=True,
    label_visibility="collapsed",
    key="topbar_nav",
)
page = _nav[_nav_icons.index(_nav_sel)] if _nav_sel in _nav_icons else _nav[0]

# ── Paleta e helpers ──────────────────────────────────────────────────────────
CAT_NAMES  = {
    "LV": "Armações de Grau",
    "OC": "Óculos Solar",
    "ML": "Armações Multi",
    "LE": "Lentes",
    "LC": "Lentes de Contato",
    "AC": "Acessórios",
    "RE": "Relógios",
    "OT": "Outros",
    "?":  "Sem catálogo",
}
CAT_COLORS = {
    "LV": "#E84300", "OC": "#BF3700", "ML": "#F5845A",
    "LE": "#2563EB", "LC": "#7C3AED", "AC": "#059669",
    "RE": "#0891B2", "OT": "#78716C",
    "?":  "#AAA",
}
TIER_COLORS = ["#7C1C00", "#BF3700", "#E84300", "#F05A1A", "#F5A07A"]

# ── Janelas de reativação ─────────────────────────────────────────────────────
# LV / OC / ML / LE: 5 janelas fixas, de 6 em 6 meses, a partir de 12 meses.
# Após a 5ª janela sem recompra → Perdido (ex-cliente).
JANELAS_MESES        = [12, 18, 24, 30, 36]          # meses de cada janela
JANELAS_CATS         = {"LV", "OC", "ML", "LE"}       # categorias com este ciclo
JANELA_PERDIDO_MESES = 42                              # além da última janela
JANELA_CORES = ["#059669","#F59E0B","#E84300","#BF3700","#7C1C00","#6B7280"]

# Mensagens focadas em saúde visual — uma por janela
TEMPLATES_JANELA: dict = {
    1: (
        "Oi {nome}! 👁️ Já faz um ano desde sua última visita à Chilli Beans. "
        "Como está sua saúde visual? Com o tempo, mudanças sutis na visão são comuns — "
        "vale a pena uma avaliação para garantir que suas lentes ainda são as ideais para você!"
    ),
    2: (
        "Oi {nome}! Estamos passando para saber como você está. "
        "Você tem sentido alguma dificuldade para enxergar de perto ou de longe, "
        "dores de cabeça ou cansaço visual? São sinais de que pode ser hora de "
        "atualizar suas lentes. 👓 Adoraríamos ajudar!"
    ),
    3: (
        "Oi {nome}! Com o uso diário, é natural que as lentes percam eficiência com o tempo — "
        "especialistas recomendam avaliação a cada 1-2 anos. "
        "Você tem sentido alguma diferença na qualidade da sua visão ultimamente? 😊"
    ),
    4: (
        "Oi {nome}! Sua saúde visual é muito importante para nós. "
        "Já faz um bom tempo desde sua última visita — como você está enxergando no dia a dia? "
        "Pequenos ajustes nas lentes podem fazer uma grande diferença no conforto e qualidade de vida."
    ),
    5: (
        "Oi {nome}! ❤️ Este é um contato especial porque valorizamos muito você como cliente. "
        "Sabia que após alguns anos a maioria das pessoas precisa de uma atualização nas lentes? "
        "Que tal conversarmos sobre como podemos cuidar melhor da sua saúde visual?"
    ),
}

def _get_janela(dias: int, cat: str):
    """Retorna (num_janela, label) para dias sem comprar.
    num=1-5: janela ativa; num=6: Perdido; num=0: ainda não atingiu a 1ª janela."""
    if cat not in JANELAS_CATS:
        return 0, "—"
    meses = dias / 30.44
    if meses >= JANELA_PERDIDO_MESES:
        return 6, "❌ Perdido"
    for i, m in enumerate(JANELAS_MESES):
        prox = JANELAS_MESES[i + 1] if i + 1 < len(JANELAS_MESES) else JANELA_PERDIDO_MESES
        if m <= meses < prox:
            return i + 1, f"J{i+1} — {m}m"
    return 0, "⏳ Aguardando"
_TEXT  = "#1C1816"
_MUTED = "#7A6A5A"
_GRID  = "#DDD"
_CATS_ALL     = ["Todas", "LV", "OC", "ML", "LE", "LC", "AC", "RE", "OT"]
_CATS_ARMACAO = ["LV", "OC", "ML"]   # categorias com lógica de estoque ideal


def get_api():
    if cfg.modo_demo or not cfg.is_configured:
        return None
    return MicrovixAPI(
        token=cfg.get("token"), cnpj=cfg.get("cnpj"),
        nome_empresa=cfg.get("nome_empresa"), base_url=cfg.get("base_url"),
    )


def fmt_brl(v) -> str:
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return "R$ —"
        return f"R$ {f:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ —"


def to_excel(sheets: dict) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
    return buf.getvalue()


def _price_label(tier: dict) -> str:
    """Returns the full tier label: 'Econômico (até R$200)'."""
    if tier["min"] == 0:
        return f"{tier['label']}  •  até R\\${tier['max']:.0f}"
    if tier["max"] >= 99999:
        return f"{tier['label']}  •  R\\${tier['min']:.0f}+"
    return f"{tier['label']}  •  R\\${tier['min']:.0f} – R\\${tier['max']:.0f}"


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _base_layout(height=280):
    return dict(
        height=height,
        margin=dict(t=40, b=30, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=_TEXT, family="Poppins, sans-serif", size=12),
        legend=dict(font=dict(color=_TEXT)),
    )


def chart_donut(df_cat: pd.DataFrame, title: str) -> go.Figure:
    labels = [CAT_NAMES.get(c, c) for c in df_cat["categoria"]]
    colors = [CAT_COLORS.get(c, "#999") for c in df_cat["categoria"]]
    fig = go.Figure(go.Pie(
        labels=labels, values=df_cat["receita"], hole=0.52,
        marker_colors=colors,
        textinfo="percent", textfont_size=11,   # só % no interior — evita labels cortados
        hovertemplate="%{label}<br>Receita: R$ %{value:,.2f}<br>%{percent}<extra></extra>",
    ))
    fig.update_layout(title=dict(text=title, font=dict(color=_TEXT)), **_base_layout(280))
    fig.update_layout(legend=dict(orientation="v", x=1.02, y=0.5, font=dict(color=_TEXT, size=11)))
    return fig


def chart_pyramid_bar(df_pyr: pd.DataFrame, title: str) -> go.Figure:
    agg = df_pyr.groupby(["faixa", "faixa_ordem"], as_index=False).agg(
        receita=("receita", "sum"), volume=("volume", "sum")
    )
    total = agg["receita"].sum()
    agg["pct"] = agg["receita"] / total * 100 if total > 0 else 0
    agg = agg.sort_values("faixa_ordem", ascending=True)
    palette = [TIER_COLORS[min(i, len(TIER_COLORS)-1)] for i in range(len(agg))]
    fig = go.Figure(go.Bar(
        x=agg["pct"], y=agg["faixa"], orientation="h",
        marker_color=palette,
        text=[f"{v:.1f}%" for v in agg["pct"]],
        textposition="inside", textfont=dict(color="white", size=11),
        hovertemplate="%{y}: %{x:.1f}% da receita<br>%{customdata} itens<extra></extra>",
        customdata=agg["volume"],
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(color=_TEXT)),
        xaxis=dict(range=[0, 70], title="% da Receita", color=_MUTED, gridcolor=_GRID),
        yaxis=dict(color=_TEXT),
        **_base_layout(240),
    )
    return fig


def chart_suggestion_bar(targets: dict, tiers: list, title: str) -> go.Figure:
    labels = [t["label"] for t in tiers]
    values = [targets.get(t["label"], 0) for t in tiers]
    palette = [TIER_COLORS[min(i, len(TIER_COLORS)-1)] for i in range(len(labels))]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=palette,
        marker_line=dict(color="#E84300", width=1.5),
        text=[f"{v:.1f}%" for v in values],
        textposition="inside", textfont=dict(color="white", size=11),
        hovertemplate="%{y}: %{x:.1f}% (meta)<extra></extra>",
        opacity=0.90,
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(color=_TEXT)),
        xaxis=dict(range=[0, 70], title="% da Receita (Meta)", color=_MUTED, gridcolor=_GRID),
        yaxis=dict(color=_TEXT),
        **_base_layout(240),
    )
    return fig


# ── PAGE: Análise de Contexto ─────────────────────────────────────────────────

def page_analysis():
    st.markdown('<div class="cb-title">📊 Análise de Contexto</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="cb-sub">Armações, Lentes e visão geral — todas as informações no período selecionado</div>',
        unsafe_allow_html=True,
    )

    tiers = cfg.get("faixas_preco", [])

    # ── Filtros de data ───────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([2, 2, 1.5])
    with c1:
        dt_ini = st.date_input("De", value=date.today().replace(day=1), key="pyr_ini")
    with c2:
        dt_fim = st.date_input("Até", value=date.today(), key="pyr_fim")
    with c3:
        st.write(""); st.write("")
        load = st.button("🔄 Carregar", key="pyr_load", width="stretch")

    if load:
        with st.spinner("Buscando dados..."):
            # Recarrega catálogo do disco a cada Carregar — garante que ampliações
            # feitas em Configurações sejam imediatamente refletidas sem reiniciar.
            st.session_state.product_map = load_map()
            api = get_api()
            try:
                if api:
                    df = api.get_sales(str(dt_ini), str(dt_fim), st.session_state.product_map)
                else:
                    df = mock_vendas(str(dt_ini), str(dt_fim))
                st.session_state.df_vendas       = df
                st.session_state.sug_faixas      = None
                st.session_state.vendas_loaded_at = datetime.now()
                _n_loaded = len(df)
                if _n_loaded == 0 and api and st.session_state.product_map:
                    _map_size = len(st.session_state.product_map)
                    st.warning(
                        f"⚠️ **0 registros retornados.** O catálogo tem {_map_size} produto(s) mapeado(s). "
                        "Se o catálogo está desatualizado, atualize em **⚙️ Configurações → Catálogo de Produtos → Importar via API**."
                    )
                else:
                    st.success(f"✅ {_n_loaded:,} registros carregados.".replace(",", "."))
            except MicrovixAPIError as e:
                st.error(str(e)); return

    df = st.session_state.df_vendas
    _pmap = st.session_state.product_map

    # R3 — filtro de visibilidade por perfil: vendedor vê só suas vendas
    _au_cod = cod_vendedor_do_usuario(st.session_state.get("auth_user"))
    if df is not None and _au_cod and "cod_vendedor" in df.columns:
        df = df[df["cod_vendedor"].astype(str) == _au_cod].copy()

    if df is None:
        if not cfg.modo_demo and not _pmap:
            st.warning("⚠️ Catálogo ainda não importado. Vá em **⚙️ Configurações → Catálogo de Produtos**.")
        else:
            st.info("Clique em **🔄 Carregar** para visualizar a análise.")
        return

    if not cfg.modo_demo and _pmap and len(_pmap) < 10:
        st.warning(
            f"⚠️ **Catálogo com apenas {len(_pmap)} produto(s).** "
            "O catálogo parece incompleto — reimporte em **⚙️ Configurações → Catálogo de Produtos**."
        )

    # ── Filtro de data — aplica sobre os dados carregados ────────────────────
    # O autoload carrega 365 dias; os date pickers podem definir um período menor.
    # Sem este filtro as 3 abas mostram todos os dados do autoload,
    # mas o caption indicaria apenas o mês atual — inconsistência crítica de UX.
    if "data" in df.columns:
        _datas = pd.to_datetime(df["data"], errors="coerce").dt.date
        _mask  = (_datas >= dt_ini) & (_datas <= dt_fim)
        df = df[_mask].copy()

    if df.empty:
        st.warning(f"Nenhuma venda encontrada entre {dt_ini.strftime('%d/%m/%Y')} e {dt_fim.strftime('%d/%m/%Y')}. "
                   "Clique em **🔄 Carregar** para buscar dados nesse período.")
        return

    st.caption(f"📅 Período analisado: **{dt_ini.strftime('%d/%m/%Y')}** a **{dt_fim.strftime('%d/%m/%Y')}** "
               f"— {len(df)} registros")

    # ── 3 Abas ────────────────────────────────────────────────────────────────
    tab_arm, tab_len, tab_geral = st.tabs(["🕶️ Armações", "👓 Lentes", "📊 Geral"])

    # ════════════════════════════════════════════════════════════════════════
    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  ABA 1 — ARMAÇÕES (LV / OC / ML) — SEÇÃO BLOQUEADA                    ║
    # ║  Autorizado por: Rafael Burim Ramo — Franqueado                        ║
    # ║  Data de bloqueio: 29/05/2026                                          ║
    # ║                                                                          ║
    # ║  REGRA IMUTÁVEL: nenhuma alteração de informação, código, layout ou    ║
    # ║  produto final desta sub-aba pode ser feita sem:                        ║
    # ║    1. Apresentar ao Rafael O QUE será alterado (antes × depois)        ║
    # ║    2. Perguntar explicitamente se ele ACEITA a edição                   ║
    # ║    3. Aguardar confirmação antes de aplicar qualquer mudança            ║
    # ║                                                                          ║
    # ║  Linhas protegidas: app.py ~598 a ~1350 (with tab_arm: até tab_len:)   ║
    # ╚══════════════════════════════════════════════════════════════════════════╝
    # ABA 1 — ARMAÇÕES (LV / OC / ML)
    # ════════════════════════════════════════════════════════════════════════
    with tab_arm:
        df_arm = df[df["categoria"].isin(_CATS_ARMACAO)].copy()
        if df_arm.empty:
            st.info("Sem vendas de armações no período selecionado.")
        else:
            df_pyr = build_pyramid_summary(df_arm, tiers)
            df_cat = build_category_summary(df_arm)

            # KPIs — ticket médio = receita ÷ itens (divisão simples)
            total_rec = df_arm["vlr_total"].sum()
            n_itens   = int(df_arm["quantidade"].sum())
            ticket    = (total_rec / n_itens) if n_itens else 0.0
            m1, m2, m3 = st.columns(3)
            m1.metric("Receita Total",  fmt_brl(total_rec))
            m2.metric("Ticket Médio",   fmt_brl(ticket))
            m3.metric("Itens Vendidos", f"{n_itens:,}".replace(",", "."))

            # Distribuição
            st.divider()
            st.markdown('<div class="section-title">📊 Distribuição de Vendas</div>', unsafe_allow_html=True)
            col_d, col_p = st.columns([1, 1], gap="large")
            with col_d:
                st.plotly_chart(chart_donut(df_cat, "Mix por Categoria"), width="stretch", key="donut_arm")
            with col_p:
                st.plotly_chart(chart_pyramid_bar(df_pyr, "Distribuição por Faixa de Preço"), width="stretch", key="pyr_arm")

            with st.expander("📄 Detalhes por faixa de preço"):
                agg = (
                    df_pyr.groupby(["faixa", "faixa_ordem"], as_index=False)
                    .agg(receita=("receita", "sum"), volume=("volume", "sum"))
                    .sort_values("faixa_ordem")
                )
                total_agg = agg["receita"].sum()
                if total_agg > 0:
                    agg["% Receita"] = (agg["receita"] / total_agg * 100).round(1).astype(str) + "%"
                else:
                    agg["% Receita"] = "—"
                agg["Receita"] = agg["receita"].apply(fmt_brl)
                st.dataframe(
                    agg[["faixa", "Receita", "% Receita", "volume"]].rename(
                        columns={"faixa": "Faixa", "volume": "Itens"}),
                    width="stretch", hide_index=True,
                )

            # Comparativo Meta de Mix
            st.divider()
            st.markdown('<div class="section-title">🎯 Comparativo Atual × Meta de Mix</div>', unsafe_allow_html=True)
            st.caption("Configure a distribuição ideal em **⚙️ Configurações → 🎯 Meta de Mix**.")

            _saved_sug = cfg.get("sug_faixas_saved")
            if not _saved_sug or not isinstance(_saved_sug, dict):
                st.info(
                    "💡 Nenhuma meta de mix configurada ainda.  \n"
                    "Vá em **⚙️ Configurações → 🎯 Meta de Mix** para definir a distribuição ideal por faixa de preço."
                )
            else:
                _agg_c = (
                    df_pyr.groupby(["faixa", "faixa_ordem"], as_index=False)
                    .agg(receita=("receita", "sum")).sort_values("faixa_ordem")
                )
                _total_c = _agg_c["receita"].sum()
                _rows_c  = []
                _labels_c, _atual_vals, _meta_vals = [], [], []
                for _, _row_c in _agg_c.iterrows():
                    _atual = _row_c["receita"] / _total_c * 100 if _total_c > 0 else 0
                    _meta  = _saved_sug.get(_row_c["faixa"], 0)
                    _diff  = _meta - _atual
                    _arrow = "↑" if _diff > 0.1 else ("↓" if _diff < -0.1 else "—")
                    _rows_c.append({
                        "Faixa": _row_c["faixa"],
                        "Atual": f"{_atual:.1f}%",
                        "Meta":  f"{_meta:.1f}%",
                        "Δ":     f"{_arrow} {abs(_diff):.1f}%" if _arrow != "—" else "—",
                    })
                    _labels_c.append(_row_c["faixa"])
                    _atual_vals.append(round(_atual, 1))
                    _meta_vals.append(round(_meta, 1))

                _col_tbl, _col_fig = st.columns([1, 1], gap="large")
                with _col_tbl:
                    st.dataframe(pd.DataFrame(_rows_c), width="stretch", hide_index=True)
                with _col_fig:
                    _fig_comp = go.Figure()
                    _fig_comp.add_trace(go.Bar(
                        name="Atual", x=_labels_c, y=_atual_vals,
                        marker_color="#E84300",
                        text=[f"{v:.1f}%" for v in _atual_vals], textposition="outside",
                    ))
                    _fig_comp.add_trace(go.Bar(
                        name="Meta", x=_labels_c, y=_meta_vals,
                        marker_color="#F5A07A",
                        text=[f"{v:.1f}%" for v in _meta_vals], textposition="outside",
                    ))
                    _fig_comp.update_layout(
                        barmode="group",
                        title=dict(text="Atual × Meta por Faixa", font=dict(color=_TEXT, size=13)),
                        yaxis=dict(title="% Receita", color=_MUTED, gridcolor=_GRID),
                        **_base_layout(260),
                    )
                    st.plotly_chart(_fig_comp, width="stretch", key="comp_meta_arm")

            # ── Sugestão de Compra Semanal ────────────────────────────────────
            st.divider()
            st.markdown('<div class="section-title">🛒 Sugestão de Compra Semanal</div>', unsafe_allow_html=True)
            st.caption("Sugestão baseada na venda semanal histórica e no estoque ideal configurado.")

            _CAT_DISPLAY  = {k: v for k, v in CAT_NAMES.items() if k in _CATS_ARMACAO}
            estoque_ideal = cfg.get("estoque_ideal", {"LV": 20, "OC": 15, "ML": 10})
            estoque_min   = cfg.get("estoque_minimo", {
                k: max(1, round(estoque_ideal.get(k, 10) * 0.5)) for k in _CATS_ARMACAO
            })
            _est_virtual  = cfg.get("estoque_virtual", {"LV": 0, "OC": 0, "ML": 0})
            _manual_stock: dict = {_c: int(_est_virtual.get(_c, 0)) for _c in _CATS_ARMACAO}

            # ── Ajuste de estoque em tempo real via LinxMovimento ────────────
            # LinxPedidosCompra está vazio nesta conta.
            # Usamos get_stock_from_movements() que lê entradas (op=E, COMPRA)
            # diretamente do LinxMovimento — funciona com a chave atual.
            # Fórmula: saldo = inventário_base + entradas_compra − saídas_venda
            _est_base_date = cfg.get("estoque_base_data", "")
            if _est_base_date:
                try:
                    from datetime import datetime as _dt, date as _today_cls
                    _base_dt      = _dt.strptime(_est_base_date, "%d/%m/%Y").date()
                    _base_dt_iso  = str(_base_dt)

                    # ── Entradas (compras recebidas desde a data base) ─────────
                    _entradas_mvt: dict = {}
                    _api_stk = get_api()
                    if _api_stk and not cfg.modo_demo:
                        try:
                            _entradas_mvt = _api_stk.get_stock_from_movements(
                                _base_dt_iso, st.session_state.product_map
                            )
                        except Exception:
                            _entradas_mvt = {}

                    # ── Saídas (vendas desde a data base) ─────────────────────
                    # Usa o df_vendas completo (sem filtro de data do período selecionado)
                    _df_vnd_full = st.session_state.df_vendas
                    for _c in _CATS_ARMACAO:
                        _entradas_c = _entradas_mvt.get(_c, 0)
                        _saidas_c   = 0
                        if _df_vnd_full is not None and "data" in _df_vnd_full.columns:
                            _mask_vnd = (
                                (_df_vnd_full["categoria"] == _c) &
                                (pd.to_datetime(_df_vnd_full["data"], errors="coerce").dt.date >= _base_dt)
                            )
                            _saidas_c = int(_df_vnd_full.loc[_mask_vnd, "quantidade"].sum())
                        _manual_stock[_c] = max(0, _manual_stock[_c] + _entradas_c - _saidas_c)

                    if _entradas_mvt:
                        _ent_txt = " · ".join(
                            f"{c} +{_entradas_mvt[c]}" for c in _CATS_ARMACAO if _entradas_mvt.get(c, 0) > 0
                        )
                        st.caption(f"📦 Entradas desde {_est_base_date}: {_ent_txt} (via LinxMovimento)")
                except Exception:
                    pass

            # ── Estoque atual — 3 níveis: mínimo / atual / ideal ─────────────
            st.markdown("**Estoque Atual por Categoria** *(ajuste em ⚙️ Configurações → Estoque)*")
            _cols_est = st.columns(len(_CATS_ARMACAO))
            for _i, _cat in enumerate(_CATS_ARMACAO):
                with _cols_est[_i]:
                    _min_cat   = estoque_min.get(_cat, 0)
                    _ideal_cat = estoque_ideal.get(_cat, 0)
                    _atual_est = _manual_stock.get(_cat, 0)
                    if _atual_est < _min_cat:
                        _status_icon = "🔴"
                        _delta_txt   = f"abaixo do mínimo ({_min_cat})"
                        _delta_color = "inverse"
                    elif _atual_est < _ideal_cat:
                        _status_icon = "🟡"
                        _delta_txt   = f"{_atual_est - _ideal_cat:+d} vs ideal ({_ideal_cat})"
                        _delta_color = "off"
                    else:
                        _status_icon = "✅"
                        _delta_txt   = f"{_atual_est - _ideal_cat:+d} vs ideal ({_ideal_cat})"
                        _delta_color = "normal"
                    st.metric(
                        label=f"{_status_icon} {_CAT_DISPLAY.get(_cat, _cat)}",
                        value=f"{_atual_est} pç",
                        delta=_delta_txt,
                        delta_color=_delta_color,
                        help=f"🟡 Mínimo: {_min_cat} pç  |  🟢 Ideal: {_ideal_cat} pç",
                    )

            # Semanas no período
            if "data" in df_arm.columns:
                _valid_dates = pd.to_datetime(df_arm["data"], errors="coerce").dropna()
            else:
                _valid_dates = pd.Series([], dtype="datetime64[ns]")
            if not _valid_dates.empty:
                _period_days     = max(1, (_valid_dates.max() - _valid_dates.min()).days + 1)
                _weeks_in_period = max(1.0, _period_days / 7.0)
            else:
                _weeks_in_period = 52.0

            # Tabela de sugestão
            rows_sug     = []
            total_lost   = 0.0
            total_weekly = 0.0
            cat_weekly: dict = {}

            for cat in _CATS_ARMACAO:
                cat_df = df_arm[df_arm["categoria"] == cat]
                wunits = float(cat_df["quantidade"].sum()) / _weeks_in_period
                wrev   = float(cat_df["vlr_total"].sum())  / _weeks_in_period
                total_weekly += wrev
                cat_weekly[cat] = {"wunits": wunits, "wrev": wrev}

                atual     = _manual_stock.get(cat, 0)
                minimo    = estoque_min.get(cat, 0)
                ideal     = estoque_ideal.get(cat, 0)
                gap       = max(0, ideal - atual)
                gap_min   = max(0, minimo - atual)   # deficit em relação ao mínimo
                suggested = gap + math.ceil(wunits) if gap > 0 else math.ceil(wunits)
                loss_frac = (gap / ideal) if ideal > 0 else 0.0
                lost_rev  = loss_frac * wrev
                total_lost += lost_rev
                # Status com 3 níveis
                if atual < minimo:
                    status = "🔴 Urgente"
                elif atual < ideal:
                    status = "🟡 Repor"
                else:
                    status = "✅ OK"

                rows_sug.append({
                    "Status":           status,
                    "Categoria":        _CAT_DISPLAY.get(cat, cat),
                    "🟡 Mínimo":       minimo,
                    "🟢 Ideal":        ideal,
                    "Em Estoque":       atual,
                    "Déficit Mínimo":   gap_min,
                    "Déficit Ideal":    gap,
                    "Venda/Sem (pç)":   round(wunits, 1),
                    "Pedido Sugerido":  suggested,
                    "Receita/Sem":      fmt_brl(wrev),
                    "Receita Perdida":  fmt_brl(lost_rev) if lost_rev > 0 else "—",
                })

            st.markdown("**Resultado da Análise de Estoque**")
            st.dataframe(
                pd.DataFrame(rows_sug), width="stretch", hide_index=True,
                column_config={
                    "Status":          st.column_config.TextColumn("", width="medium"),
                    "Categoria":       st.column_config.TextColumn("Categoria"),
                    "🟡 Mínimo":      st.column_config.NumberColumn("🟡 Mínimo", format="%d pç",
                                           help="Abaixo deste valor → compra urgente na semana"),
                    "🟢 Ideal":       st.column_config.NumberColumn("🟢 Ideal",  format="%d pç",
                                           help="Meta de reposição"),
                    "Em Estoque":      st.column_config.NumberColumn("Em Estoque", format="%d pç"),
                    "Déficit Mínimo":  st.column_config.NumberColumn("Déf. Mínimo", format="%d pç",
                                           help="Peças faltando para atingir o mínimo — prioridade urgente"),
                    "Déficit Ideal":   st.column_config.NumberColumn("Déf. Ideal",  format="%d pç",
                                           help="Peças faltando para atingir o ideal"),
                    "Venda/Sem (pç)":  st.column_config.NumberColumn("Venda/Sem", format="%.1f pç"),
                    "Pedido Sugerido": st.column_config.NumberColumn("Pedido Sug.", format="%d pç"),
                },
            )

            # KPIs receita perdida
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("💸 Receita Perdida Est./Semana", fmt_brl(total_lost),
                help="Estimativa de receita não realizada por desalinhamento de estoque.")
            kpi2.metric("📉 % da Receita Semanal",
                f"{(total_lost / total_weekly * 100):.1f}%" if total_weekly > 0 else "—",
                help="Fração da receita semanal projetada que está sendo perdida.")
            kpi3.metric("📆 Projeção Mensal Perdida", fmt_brl(total_lost * 4.33),
                help="Total mensal estimado (semanas × 4.33).")

            # ── Alertas com 3 níveis usando mínimo e ideal ───────────────────
            # Calcula déficits separados por limiar
            _cats_abaixo_min  = [c for c in _CATS_ARMACAO
                                  if _manual_stock.get(c,0) < estoque_min.get(c,0)]
            _cats_abaixo_ideal = [c for c in _CATS_ARMACAO
                                   if _manual_stock.get(c,0) < estoque_ideal.get(c,0)]
            _deficit_min   = sum(max(0, estoque_min.get(c,0)   - _manual_stock.get(c,0)) for c in _CATS_ARMACAO)
            _deficit_ideal = sum(max(0, estoque_ideal.get(c,0) - _manual_stock.get(c,0)) for c in _CATS_ARMACAO)
            lost_pct = (total_lost / total_weekly) if total_weekly > 0 else 0.0

            if _cats_abaixo_min:
                _cats_txt = ", ".join(f"**{CAT_NAMES.get(c,c)}** ({_manual_stock.get(c,0)} / mín {estoque_min.get(c,0)})"
                                      for c in _cats_abaixo_min)
                st.error(
                    f"🔴 **COMPRA URGENTE — esta semana!**  \n"
                    f"Categorias abaixo do estoque mínimo: {_cats_txt}.  \n"
                    f"Déficit mínimo total: **{_deficit_min} peças**. "
                    f"Realize o pedido agora para evitar ruptura de estoque."
                )
            if _cats_abaixo_ideal and not _cats_abaixo_min:
                _cats_txt2 = ", ".join(f"**{CAT_NAMES.get(c,c)}**" for c in _cats_abaixo_ideal)
                st.warning(
                    f"🟡 **Reposição recomendada.**  \n"
                    f"Categorias abaixo do estoque ideal: {_cats_txt2}.  \n"
                    f"Déficit para o ideal: **{_deficit_ideal} peças**. "
                    f"Inclua no próximo pedido semanal."
                )
            elif _cats_abaixo_ideal and _cats_abaixo_min:
                # Já mostrou o erro — adiciona info sobre ideal
                _resto = [c for c in _cats_abaixo_ideal if c not in _cats_abaixo_min]
                if _resto:
                    _cats_txt3 = ", ".join(f"**{CAT_NAMES.get(c,c)}**" for c in _resto)
                    st.warning(f"🟡 Também abaixo do ideal (não urgente): {_cats_txt3} — inclua no pedido.")
            if not _cats_abaixo_ideal:
                _weekly_ideal = sum(
                    cat_weekly[c]["wrev"] for c in _CATS_ARMACAO
                    if estoque_ideal.get(c, 0) > 0 and cat_weekly[c]["wunits"] >= estoque_ideal.get(c, 0) * 0.8
                )
                if total_weekly > 0 and _weekly_ideal > 0 and total_weekly > _weekly_ideal * 1.08:
                    st.warning(
                        "🏆 **Desempenho acima do esperado!**  \n"
                        "Faturamento supera o projetado com estoque alinhado. "
                        "**Comunique ao consultor da franquia** para revisão de metas."
                    )
                else:
                    st.success(
                        "✅ **Estoque bem alinhado!**  \n"
                        "Sem déficit físico detectado e perda estimada < 3% da receita semanal."
                    )

            # ── Lista de Compras ──────────────────────────────────────────────
            st.divider()
            st.markdown('<div class="section-title">📋 Lista de Compras por Referência</div>', unsafe_allow_html=True)
            st.caption("Déficit distribuído proporcionalmente à demanda dos últimos 3 meses por SKU.")

            _col_budget, _col_budget_info = st.columns([2, 3])
            with _col_budget:
                _orcamento = st.number_input(
                    "💰 Orçamento de compra",
                    min_value=0.0, value=0.0, step=100.0, format="%.2f",
                    key="orcamento_compras",
                    help="Digite o valor em reais. Ex: 2000 = R$ 2.000,00",
                )
                # Exibe o valor formatado no padrão brasileiro logo abaixo do campo
                if _orcamento > 0:
                    st.caption(f"**{fmt_brl(_orcamento)}** — 0 = sem limite")
                else:
                    st.caption("R$ 0,00 — sem limite de orçamento")
            with _col_budget_info:
                if _orcamento > 0:
                    st.info(
                        f"**Orçamento ativo: {fmt_brl(_orcamento)}**  \n"
                        "Lista limitada pelo custo de atacado, distribuída proporcionalmente entre categorias."
                    )
                else:
                    st.caption("Sem orçamento definido — exibe a quantidade necessária para atingir o estoque ideal.")

            if "referencia" in df_arm.columns:
                # ── Demanda: últimos 3 meses (ou todo o período se menor) ──────
                if "data" in df_arm.columns and not df_arm.empty:
                    _dt_max_arm = pd.to_datetime(df_arm["data"], errors="coerce").max()
                    _dt_3m_ini  = _dt_max_arm - pd.Timedelta(days=90)
                    _df_arm_3m  = df_arm[pd.to_datetime(df_arm["data"], errors="coerce") >= _dt_3m_ini]
                else:
                    _df_arm_3m = df_arm
                _semanas_3m = max(1.0, min(13.0, len(_df_arm_3m) / 7.0)) if not _df_arm_3m.empty else 13.0

                # ── Demanda: 3m principal → período completo → histórico geral ──
                # Fallback garante que categorias com déficit mas sem venda
                # recente (ex: ML em meses de baixo giro) apareçam na lista.
                def _build_demand(source_df, label):
                    if source_df.empty:
                        return pd.DataFrame(), 1.0, label
                    _agg = (
                        source_df.groupby(["referencia", "categoria"], as_index=False)
                        .agg(total_vendido=("quantidade", "sum"), receita=("vlr_total", "sum"))
                    )
                    if "data" in source_df.columns:
                        _dts = pd.to_datetime(source_df["data"], errors="coerce").dropna()
                        _sem = max(1.0, (_dts.max() - _dts.min()).days / 7.0 + 1) if not _dts.empty else 13.0
                    else:
                        _sem = 13.0
                    _agg["venda_semana"] = (_agg["total_vendido"] / _sem).round(4)
                    return _agg, _sem, label

                _df_ref,  _sem_3m,  _ = _build_demand(_df_arm_3m, "3m")
                _df_ref_p, _sem_per, _ = _build_demand(df_arm,     "período")
                # Fallback nível 3: histórico completo em memória (autoload)
                _df_hist_arm = st.session_state.df_vendas
                if _df_hist_arm is not None and "categoria" in _df_hist_arm.columns:
                    _df_hist_arm = _df_hist_arm[_df_hist_arm["categoria"].isin(_CATS_ARMACAO)].copy()
                else:
                    _df_hist_arm = pd.DataFrame()
                _df_ref_h, _sem_hist, _ = _build_demand(_df_hist_arm, "histórico")

                # ── Mapa de preços (preco_original > vlr_unitario) ───────────
                # Usa df_arm + histórico para maximizar cobertura de preços
                _price_lookup: dict = {}
                for _src_df in (df_arm, _df_hist_arm):
                    for _col_p in ("preco_original", "vlr_unitario"):
                        if _col_p in _src_df.columns:
                            _grp = _src_df[_src_df[_col_p] > 0].groupby("referencia")[_col_p].mean()
                            for _r, _p in _grp.items():
                                if _r not in _price_lookup:
                                    _price_lookup[_r] = float(_p)
                _has_prices = bool(_price_lookup)

                # ── Preço médio LV.MU (proxy para ML.* sem histórico) ────────
                _lv_mu_precos = [
                    _price_lookup[r]
                    for r in _price_lookup
                    if str(r).upper().startswith("LV.MU") and _price_lookup[r] > 0
                ]
                _avg_preco_lv_mu = (sum(_lv_mu_precos) / len(_lv_mu_precos)) if _lv_mu_precos else None

                # Níveis de estoque para urgência na lista de compras
                _qtd_min = cfg.get("qtd_minima_compra", {"LV": 1, "OC": 1, "ML": 1})
                # estoque_min e estoque_ideal já carregados acima

                def _make_row(ref, rcat, demanda, venda_sem, sug_q, preco, atac, fonte):
                    _vv   = round(sug_q * preco, 2) if preco else None
                    _at   = round(atac, 2) if atac else None
                    _qmin = _qtd_min.get(rcat, 1)
                    # Urgência baseada no limiar mínimo
                    _atual_cat = _manual_stock.get(rcat, 0)
                    _min_cat   = estoque_min.get(rcat, 0)
                    _urgencia  = "🔴 Urgente" if _atual_cat < _min_cat else "🟡 Repor"
                    return {
                        "Urgência":           _urgencia,
                        "Referência":         ref,
                        "Categoria":          CAT_NAMES.get(rcat, rcat),
                        "Qtd. Mínima":        _qmin,
                        "Demanda 3m":         int(demanda),
                        "Venda/Semana":       round(venda_sem, 2),
                        "Sugerido Comprar":   sug_q,
                        "Preço Atacado":      fmt_brl(_at) if _at else "—",
                        "Custo Total":        fmt_brl(sug_q * _at) if _at else "—",
                        "Valor de Venda":     fmt_brl(_vv) if _vv else "—",
                        "Fonte":              fonte,
                        "_preco":             float(preco) if preco else None,
                        "_preco_atacado_num": _at,
                        "_custo_total_num":   round(sug_q * _at, 2) if _at else 0.0,
                        "_vlr_venda_num":     _vv or 0.0,
                        "_venda_semana_num":  float(venda_sem),
                        "_urgencia_ord":      0 if _atual_cat < _min_cat else 1,
                    }

                _ref_rows = []
                for _rcat in _CATS_ARMACAO:
                    _deficit_r = max(0, estoque_ideal.get(_rcat, 0) - int(_manual_stock.get(_rcat, 0)))
                    if _deficit_r == 0:
                        continue

                    # ── Tratamento especial: ML inclui LV.MU (histórico) + ML.* (novos) ──
                    # ML.* são modelos recentes com 0 vendas — não aparecem no histórico.
                    # Gera linha genérica de orçamento para eles, separada dos LV.MU.
                    if _rcat == "ML":
                        # Separa histórico por prefixo de referência
                        for _src, _lbl in [(_df_ref, "3m"), (_df_ref_p, "período"), (_df_ref_h, "histórico")]:
                            _dfc_ml = _src[_src["categoria"] == "ML"]
                            if not _dfc_ml.empty:
                                break
                        else:
                            _dfc_ml = pd.DataFrame()

                        # LV.MU.* — sugestão por SKU baseada no histórico
                        _dfc_lv = _dfc_ml[_dfc_ml["referencia"].str.upper().str.startswith("LV.MU")] if not _dfc_ml.empty else pd.DataFrame()
                        _dfc_lv = _dfc_lv.sort_values("total_vendido", ascending=False)
                        _total_lv_sold = _dfc_lv["total_vendido"].sum() if not _dfc_lv.empty else 0

                        # Proporção do déficit para LV.MU vs ML.*
                        # ML.* sem histórico → recebe no mínimo 30% do déficit como sugestão genérica
                        _ml_star_share = 0.30
                        _deficit_lv_mu = round(_deficit_r * (1 - _ml_star_share))
                        _deficit_ml_st = _deficit_r - _deficit_lv_mu

                        # Distribui LV.MU proporcionalmente às vendas
                        if not _dfc_lv.empty and _deficit_lv_mu > 0:
                            _rem = _deficit_lv_mu
                            for _, _rrow in _dfc_lv.iterrows():
                                if _rem <= 0:
                                    break
                                _prop  = (_rrow["total_vendido"] / _total_lv_sold) if _total_lv_sold > 0 else (1 / len(_dfc_lv))
                                _sug_q = min(_rem, max(1, round(_prop * _deficit_lv_mu)))
                                if _sug_q <= 0:
                                    continue
                                _rem -= _sug_q
                                _pc   = _price_lookup.get(str(_rrow["referencia"]))
                                _ref_rows.append(_make_row(
                                    _rrow["referencia"], "ML",
                                    int(_rrow["total_vendido"]), float(_rrow["venda_semana"]),
                                    _sug_q, _pc, (_pc / 3) if _pc else None, _lbl,
                                ))

                        # ML.* — linha genérica de orçamento (sem SKU específico)
                        if _deficit_ml_st > 0:
                            _preco_proxy  = _avg_preco_lv_mu    # usa LV.MU como referência de preço
                            _atac_proxy   = round(_preco_proxy / 3, 2) if _preco_proxy else None
                            _custo_gen    = round(_deficit_ml_st * _atac_proxy, 2) if _atac_proxy else None
                            _venda_gen    = round(_deficit_ml_st * _preco_proxy, 2) if _preco_proxy else None
                            _ref_rows.append({
                                "Referência":         "ML.* — novos modelos (genérico)",
                                "Categoria":          "Armações Multi",
                                "Demanda 3m":         0,
                                "Venda/Semana":       0.0,
                                "Sugerido Comprar":   _deficit_ml_st,
                                "Preço Atacado":      fmt_brl(_atac_proxy) if _atac_proxy else "—",
                                "Custo Total":        fmt_brl(_custo_gen) if _custo_gen else "—",
                                "Valor de Venda":     fmt_brl(_venda_gen) if _venda_gen else "—",
                                "Fonte":              "💡 novo",
                                "_preco":             _preco_proxy,
                                "_preco_atacado_num": _atac_proxy,
                                "_custo_total_num":   _custo_gen or 0.0,
                                "_vlr_venda_num":     _venda_gen or 0.0,
                                "_venda_semana_num":  0.0,
                            })
                        continue  # ← pula o loop padrão para ML

                    # ── Demais categorias: fluxo normal com fallback ──────────
                    _dfc = _df_ref[_df_ref["categoria"] == _rcat]
                    _fonte_label = "3m"
                    if _dfc.empty:
                        _dfc = _df_ref_p[_df_ref_p["categoria"] == _rcat]
                        _fonte_label = "período"
                    if _dfc.empty:
                        _dfc = _df_ref_h[_df_ref_h["categoria"] == _rcat]
                        _fonte_label = "histórico"
                    if _dfc.empty:
                        _ref_rows.append(_make_row(
                            f"({CAT_NAMES.get(_rcat, _rcat)} — sem histórico)", _rcat,
                            0, 0.0, _deficit_r, None, None, "sem dados",
                        ))
                        continue

                    _dfc = _dfc.sort_values("total_vendido", ascending=False)
                    _total_sold = _dfc["total_vendido"].sum()
                    _remaining  = _deficit_r
                    for _, _rrow in _dfc.iterrows():
                        if _remaining <= 0:
                            break
                        _prop  = (_rrow["total_vendido"] / _total_sold) if _total_sold > 0 else (1 / max(len(_dfc), 1))
                        _sug_q = min(_remaining, max(1, round(_prop * _deficit_r)))
                        if _sug_q <= 0:
                            continue
                        _remaining -= _sug_q
                        _pc = _price_lookup.get(str(_rrow["referencia"]))
                        _ref_rows.append(_make_row(
                            _rrow["referencia"], _rcat,
                            int(_rrow["total_vendido"]), float(_rrow["venda_semana"]),
                            _sug_q, _pc, (_pc / 3) if _pc else None, _fonte_label,
                        ))

                if _ref_rows:
                    if _orcamento > 0 and _has_prices:
                        # ── Alocação PROPORCIONAL por categoria ───────────────
                        # Garante que TODOS os grupos com déficit apareçam na lista,
                        # com orçamento distribuído proporcionalmente ao custo do déficit.
                        # Sem isso, uma categoria cara pode consumir todo o orçamento.
                        from collections import defaultdict
                        _cat_rows   = defaultdict(list)
                        _cat_cost   = defaultdict(float)
                        for _item in _ref_rows:
                            _c = str(_item.get("Categoria", ""))
                            _p = _item.get("_preco_atacado_num") or 0
                            _cat_rows[_c].append(_item)
                            _cat_cost[_c] += _item.get("Sugerido Comprar", 0) * _p

                        _custo_total_def = sum(_cat_cost.values()) or 1.0
                        _ref_rows_final  = []
                        _acum_custo      = 0.0

                        for _c, _items in _cat_rows.items():
                            # Fatia do orçamento proporcional ao custo do déficit desta categoria
                            _budget_cat = _orcamento * (_cat_cost[_c] / _custo_total_def)
                            _acum_cat   = 0.0
                            _items_ord  = sorted(_items, key=lambda x: x["Demanda 3m"], reverse=True)
                            for _item in _items_ord:
                                _p = _item.get("_preco_atacado_num") or 0
                                if _p <= 0:
                                    _ref_rows_final.append(_item); continue
                                _qmin = _qtd_min.get(
                                    next((k for k, v in CAT_NAMES.items() if v == _c), ""), 1
                                )
                                _custo_item = _item["Sugerido Comprar"] * _p
                                if _acum_cat + _custo_item <= _budget_cat:
                                    _acum_cat   += _custo_item
                                    _acum_custo += _custo_item
                                    _ref_rows_final.append(_item)
                                elif _acum_cat < _budget_cat:
                                    _qtd_parcial = max(_qmin, int((_budget_cat - _acum_cat) / _p))
                                    if _qtd_parcial > 0:
                                        _cp = round(_qtd_parcial * _p, 2)
                                        _vp = round(_qtd_parcial * (_item["_preco"] or 0), 2)
                                        _acum_cat   += _cp
                                        _acum_custo += _cp
                                        _item["Sugerido Comprar"] = _qtd_parcial
                                        _item["Custo Total"]      = fmt_brl(_cp)
                                        _item["Valor de Venda"]   = fmt_brl(_vp)
                                        _item["_custo_total_num"] = _cp
                                        _item["_vlr_venda_num"]   = _vp
                                        _ref_rows_final.append(_item)

                        st.caption(f"Orçamento utilizado: {fmt_brl(_acum_custo)} de {fmt_brl(_orcamento)} "
                                   f"— distribuído proporcionalmente entre {len(_cat_rows)} categorias.")
                    elif _orcamento > 0 and not _has_prices:
                        _ref_rows_final = _ref_rows
                        st.caption("Preços não disponíveis — importe o catálogo com coluna de preço.")
                    else:
                        _ref_rows_final = _ref_rows

                    # ── Remove linhas vazias / sem sugestão ───────────────────
                    _ref_rows_final = [
                        r for r in _ref_rows_final
                        if r.get("Sugerido Comprar", 0) > 0
                        and str(r.get("Referência", "")).strip() not in ("", "nan")
                    ]

                    _df_ref_tbl = (
                        pd.DataFrame(_ref_rows_final)
                        .sort_values(["Categoria", "Demanda 3m"], ascending=[True, False])
                        .reset_index(drop=True)
                    )
                    # Ordena: urgentes primeiro, depois por categoria e demanda
                    _df_ref_tbl = (
                        pd.DataFrame(_ref_rows_final)
                        .sort_values(["_urgencia_ord", "Categoria", "Demanda 3m"],
                                     ascending=[True, True, False])
                        .reset_index(drop=True)
                    )
                    # Remove colunas auxiliares ANTES de exibir
                    _aux_cols = ["_preco", "_preco_atacado_num", "_custo_total_num",
                                 "_vlr_venda_num", "_venda_semana_num", "_urgencia_ord"]
                    _df_ref_tbl = _df_ref_tbl.drop(columns=_aux_cols, errors="ignore")
                    # Ordem das colunas — Urgência e Qtd. Mínima logo após Categoria
                    _col_order = ["Urgência", "Referência", "Categoria", "Fonte", "Qtd. Mínima",
                                  "Demanda 3m", "Venda/Semana", "Sugerido Comprar",
                                  "Preço Atacado", "Custo Total", "Valor de Venda"]
                    _df_ref_tbl = _df_ref_tbl[[c for c in _col_order if c in _df_ref_tbl.columns]]

                    # ── Totais ────────────────────────────────────────────────
                    _total_sug   = int(sum(r.get("Sugerido Comprar", 0) for r in _ref_rows_final))
                    _total_custo = sum(r.get("_custo_total_num", 0) or 0 for r in _ref_rows_final)
                    _total_venda = sum(r.get("_vlr_venda_num",   0) or 0 for r in _ref_rows_final)
                    _total_itens = len(_df_ref_tbl)
                    _markup_ratio = round(_total_venda / _total_custo, 2) if _total_custo > 0 else 0.0

                    # ── Tempo de Reposição ────────────────────────────────────
                    # Fórmula: qtd_proxima_compra / (vendas_desde_ultima_compra / dias_desde_ultima_compra)
                    # Usa get_purchase_movements() para achar a última compra por categoria
                    _tempo_repos_semanas = None
                    try:
                        _api_tr = get_api()
                        _est_bd = cfg.get("estoque_base_data", "")
                        if _api_tr and not cfg.modo_demo and _est_bd:
                            from datetime import datetime as _dtt, date as _date_cls
                            _base_iso_tr = str(_dtt.strptime(_est_bd, "%d/%m/%Y").date())
                            _mvt_info = _api_tr.get_purchase_movements(_base_iso_tr, st.session_state.product_map)
                            _df_vnd_all = st.session_state.df_vendas
                            _total_qtd_compra = 0; _total_dias_venda = 0; _total_vendas_ult = 0
                            for _c in _CATS_ARMACAO:
                                _c_sug  = sum(r.get("Sugerido Comprar", 0) for r in _ref_rows_final
                                              if CAT_NAMES.get(_c,"") in str(r.get("Categoria","")))
                                if _c_sug <= 0:
                                    continue
                                _ult_dt = _mvt_info.get(_c, {}).get("ultima_compra")
                                if _ult_dt is None:
                                    continue
                                _dias = max(1, (_date_cls.today() - _ult_dt).days)
                                _vnd_ult = 0
                                if _df_vnd_all is not None and "data" in _df_vnd_all.columns:
                                    _mk = (
                                        (_df_vnd_all["categoria"] == _c) &
                                        (pd.to_datetime(_df_vnd_all["data"], errors="coerce").dt.date >= _ult_dt)
                                    )
                                    _vnd_ult = int(_df_vnd_all.loc[_mk, "quantidade"].sum())
                                if _vnd_ult > 0:
                                    _total_qtd_compra += _c_sug
                                    _total_dias_venda += _dias
                                    _total_vendas_ult += _vnd_ult
                            if _total_vendas_ult > 0 and _total_dias_venda > 0:
                                _taxa_diaria = _total_vendas_ult / _total_dias_venda
                                _tempo_repos_semanas = round(_total_qtd_compra / (_taxa_diaria * 7), 1)
                    except Exception:
                        pass
                    # Fallback: usa velocidade 3m se não conseguiu calcular desde última compra
                    if _tempo_repos_semanas is None:
                        _vel_semanal = sum(r.get("_venda_semana_num", 0) or 0 for r in _ref_rows_final)
                        _tempo_repos_semanas = round(_total_sug / _vel_semanal, 1) if _vel_semanal > 0 else None

                    st.dataframe(
                        _df_ref_tbl, width="stretch", hide_index=True,
                        height=min(600, 80 + len(_df_ref_tbl) * 35),
                        column_config={
                            "Urgência":         st.column_config.TextColumn("", width="small",
                                                    help="🔴 Urgente = abaixo do mínimo, comprar esta semana  |  "
                                                         "🟡 Repor = abaixo do ideal, incluir no próximo pedido"),
                            "Fonte":            st.column_config.TextColumn("Fonte", width="small",
                                                    help="Janela da demanda: '3m' / 'período' / 'histórico'"),
                            "Qtd. Mínima":      st.column_config.NumberColumn("Qtd. Mín.", format="%d pç",
                                                    help="Quantidade mínima por pedido nesta categoria."),
                            "Demanda 3m":       st.column_config.NumberColumn("Demanda 3m", format="%d un"),
                            "Venda/Semana":     st.column_config.NumberColumn("Venda/Sem.", format="%.2f"),
                            "Sugerido Comprar": st.column_config.NumberColumn("Sugerido", format="%d pç"),
                            "Preço Atacado":    st.column_config.TextColumn("Preço Atacado"),
                            "Custo Total":      st.column_config.TextColumn("Custo Total"),
                            "Valor de Venda":   st.column_config.TextColumn("Valor Venda"),
                        },
                    )

                    # ── KPIs linha 1: volumes ─────────────────────────────────
                    _tc1, _tc2, _tc3 = st.columns(3)
                    _tc1.metric("📦 Total de SKUs",         f"{_total_itens} ref.")
                    _tc2.metric("🛒 Total a Comprar",       f"{_total_sug} pç")
                    _tc3.metric("💰 Custo Total (atacado)", fmt_brl(_total_custo) if _total_custo else "—")

                    # ── KPIs linha 2: financeiro + tempo de reposição ─────────
                    _fc1, _fc2, _fc3 = st.columns(3)
                    _fc1.metric(
                        "🏷️ Valor de Venda Est.",
                        fmt_brl(_total_venda) if _total_venda else "—",
                        help="Receita esperada ao vender todas as peças pelo preço de tabela.",
                    )
                    _fc2.metric(
                        "📈 Markup",
                        f"{_markup_ratio:.2f}".replace(".", ",") if _total_custo > 0 else "—",
                        help="Valor de Venda ÷ Valor de Custo (ex: 3,00 = vende pelo triplo do que compra).",
                    )
                    _fc3.metric(
                        "⏱️ Tempo de Reposição",
                        f"{_tempo_repos_semanas:.1f} sem." if _tempo_repos_semanas else "—",
                        help="Estimativa de semanas até o estoque comprado se esgotar, "
                             "baseada na velocidade de vendas desde a última compra por categoria.",
                    )

                    st.download_button(
                        "📥 Exportar Lista de Compras",
                        data=to_excel({"Lista de Compras": _df_ref_tbl.copy()}),
                        file_name=f"lista_compras_{date.today().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_lista_compras",
                    )
                else:
                    st.info("Sem déficit de estoque nas categorias de armações — nenhuma compra sugerida.")
            else:
                st.info("Dados de referência não disponíveis. Importe o catálogo nas Configurações.")

            with st.expander("ℹ️ Como é calculada a receita perdida?"):
                st.markdown("""
**Modelo utilizado: Nível de Serviço (Service-Level Model)**

Para cada categoria (LV / OC / ML):
> **Receita Perdida = (Déficit ÷ Estoque Ideal) × Receita Semanal da Categoria**

- **Déficit** = max(0, Estoque Ideal − Estoque Atual)
- **Receita Semanal** = receita histórica da categoria ÷ semanas no período analisado

**Interpretação:** se você está com 30% do estoque ideal, estima-se que 30% das vendas
potenciais estão sendo perdidas por ruptura de estoque.
                """)

    # ════════════════════════════════════════════════════════════════════════
    # ╚══ FIM DA SEÇÃO BLOQUEADA — ABA ARMAÇÕES ═══════════════════════════════╝

    # ABA 2 — LENTES (LE / LC)
    # ════════════════════════════════════════════════════════════════════════
    with tab_len:
        df_len = df[df["categoria"].isin(["LE", "LC"])].copy()
        if df_len.empty:
            st.info("Sem vendas de lentes no período selecionado.")
        else:
            _le_receita = df_len["vlr_total"].sum()
            _le_itens   = int(df_len["quantidade"].sum())
            _le_ticket  = (_le_receita / _le_itens) if _le_itens else 0.0

            m1, m2, m3 = st.columns(3)
            m1.metric("Receita de Lentes", fmt_brl(_le_receita))
            m2.metric("Itens Vendidos",    f"{_le_itens:,}".replace(",", "."))
            m3.metric("Ticket Médio",      fmt_brl(_le_ticket))

            # Distribuição por tipo
            st.divider()
            st.markdown('<div class="section-title">📊 Distribuição por Tipo</div>', unsafe_allow_html=True)

            def _le_tipo(ref: str) -> str:
                r = str(ref).upper()
                if r.startswith("LE.VI"): return "Visão Simples (LE.VI)"
                if r.startswith("LE.VA"): return "Progressivas/Varifocais (LE.VA)"
                if r.startswith("LE.CO"): return "Lentes de Contato (LE.CO)"
                if r.startswith("LE.CT"): return "Lentes de Contato (LE.CT)"
                return "Outros"

            if "referencia" in df_len.columns:
                df_len["tipo_le"] = df_len["referencia"].apply(_le_tipo)
            else:
                df_len["tipo_le"] = "Outros"

            _tipo_agg = (
                df_len.groupby("tipo_le")
                .agg(receita=("vlr_total", "sum"), itens=("quantidade", "sum"))
                .reset_index().sort_values("receita", ascending=False)
            )
            _tipo_agg["% Receita"] = (_tipo_agg["receita"] / _le_receita * 100).round(1).astype(str) + "%" if _le_receita > 0 else "—"
            _tipo_agg["Receita"]   = _tipo_agg["receita"].apply(fmt_brl)

            _col_tipo1, _col_tipo2 = st.columns([1, 1], gap="large")
            with _col_tipo1:
                _fig_tipo = go.Figure(go.Pie(
                    labels=_tipo_agg["tipo_le"],
                    values=_tipo_agg["receita"],
                    hole=0.45,
                    marker_colors=["#2563EB", "#7C3AED", "#059669", "#0891B2", "#9CA3AF"],
                    textinfo="percent",           # só % dentro — evita labels cortados
                    hovertemplate="%{label}<br>%{percent}<br>R$ %{value:,.2f}<extra></extra>",
                ))
                _fig_tipo.update_layout(**_base_layout(280))
                _fig_tipo.update_layout(legend=dict(orientation="v", x=1.02, y=0.5, font=dict(color=_TEXT, size=11)))
                st.plotly_chart(_fig_tipo, width="stretch", key="donut_lentes_tipo")
            with _col_tipo2:
                st.dataframe(
                    _tipo_agg[["tipo_le", "Receita", "% Receita", "itens"]].rename(
                        columns={"tipo_le": "Tipo", "itens": "Itens"}
                    ),
                    width="stretch", hide_index=True,
                )

            # Análise por Fornecedor
            st.divider()
            st.markdown('<div class="section-title">🏭 Análise por Fornecedor</div>', unsafe_allow_html=True)

            _FORN_PATH = os.path.join(ROOT, "data", "fornecedor_lentes.json")

            def _load_forn_map() -> dict:
                if os.path.exists(_FORN_PATH):
                    try:
                        with open(_FORN_PATH, "r", encoding="utf-8") as _ff:
                            return json.load(_ff)
                    except Exception:
                        return {}
                return {}

            def _save_forn_map(m: dict):
                os.makedirs(os.path.dirname(_FORN_PATH), exist_ok=True)
                with open(_FORN_PATH, "w", encoding="utf-8") as _ff:
                    json.dump(m, _ff, ensure_ascii=False, indent=2)

            def _lookup_forn(ref: str, fmap: dict) -> str:
                r = str(ref).strip()
                if r in fmap:
                    return fmap[r]
                for i in range(len(r), 1, -1):
                    if r[:i] in fmap:
                        return fmap[r[:i]]
                return detect_brand(ref)

            _forn_map = _load_forn_map()

            if "referencia" in df_len.columns:
                df_len["fornecedor"] = df_len["referencia"].apply(lambda r: _lookup_forn(r, _forn_map))
            else:
                df_len["fornecedor"] = "Outros"

            _forn_agg = (
                df_len.groupby("fornecedor")
                .agg(receita=("vlr_total", "sum"), itens=("quantidade", "sum"))
                .reset_index().sort_values("receita", ascending=False)
            )
            _forn_pct = (_forn_agg["receita"] / _le_receita * 100).round(1) if _le_receita > 0 else 0
            _forn_agg["% Receita"] = _forn_pct.astype(str) + "%"
            _forn_agg["Receita"]   = _forn_agg["receita"].apply(fmt_brl)

            _cf1, _cf2 = st.columns([1, 1], gap="large")
            with _cf1:
                _fig_forn = go.Figure(go.Bar(
                    x=_forn_agg["fornecedor"],
                    y=_forn_pct.tolist(),
                    marker_color=[LENS_BRAND_COLORS.get(b, "#9CA3AF") for b in _forn_agg["fornecedor"]],
                    text=_forn_agg["% Receita"], textposition="outside",
                ))
                _fig_forn.update_layout(
                    title=dict(text="Receita por Fornecedor (%)", font=dict(color=_TEXT, size=13)),
                    yaxis=dict(title="% da Receita", color=_MUTED, gridcolor=_GRID),
                    **_base_layout(260),
                )
                st.plotly_chart(_fig_forn, width="stretch", key="forn_chart")
            with _cf2:
                st.dataframe(
                    _forn_agg[["fornecedor", "Receita", "% Receita", "itens"]].rename(
                        columns={"fornecedor": "Fornecedor", "itens": "Itens"}
                    ),
                    width="stretch", hide_index=True,
                )

            # Meta de mix por fornecedor
            _forn_meta = cfg.get("lens_meta_mix", {b: 0 for b in LENS_ALL_BRANDS})
            with st.expander("🎯 Meta de Mix por Fornecedor — clique para configurar"):
                st.caption("Defina a distribuição ideal de receita por fornecedor. A soma deve ser 100%.")
                _meta_cols_f = st.columns(len(LENS_ALL_BRANDS))
                _new_forn_meta: dict = {}
                for _mi, _mb in enumerate(LENS_ALL_BRANDS):
                    with _meta_cols_f[_mi]:
                        _new_forn_meta[_mb] = st.number_input(
                            _mb, min_value=0, max_value=100,
                            value=int(_forn_meta.get(_mb, 0)),
                            key=f"lens_meta_{_mb}",
                        )
                _mt = sum(_new_forn_meta.values())
                if _mt != 100:
                    st.warning(f"⚠️ Total: {_mt}% (deve ser 100%).")
                else:
                    st.success("✅ Distribuição válida (soma = 100%).")
                if st.button("💾 Salvar Meta de Mix de Lentes", key="save_lens_meta"):
                    cfg.set("lens_meta_mix", _new_forn_meta)
                    cfg.save()
                    st.success("Meta salva!")
                    st.rerun()

                # Gráfico Atual × Meta
                _all_forn_keys = list(LENS_ALL_BRANDS)
                _av_m, _mv_m = [], []
                for _bk in _all_forn_keys:
                    _rb = _forn_agg[_forn_agg["fornecedor"] == _bk]
                    _av_m.append(float(_forn_pct[_forn_agg["fornecedor"] == _bk].values[0]) if not _rb.empty else 0.0)
                    _mv_m.append(float(_forn_meta.get(_bk, 0)))
                _fig_meta_forn = go.Figure()
                _fig_meta_forn.add_trace(go.Bar(name="Atual", x=_all_forn_keys, y=_av_m, marker_color="#2563EB",
                    text=[f"{v:.1f}%" for v in _av_m], textposition="outside"))
                _fig_meta_forn.add_trace(go.Bar(name="Meta", x=_all_forn_keys, y=_mv_m, marker_color="#93C5FD",
                    text=[f"{v:.1f}%" for v in _mv_m], textposition="outside"))
                _fig_meta_forn.update_layout(barmode="group",
                    title=dict(text="Atual × Meta por Fornecedor", font=dict(color=_TEXT, size=13)),
                    yaxis=dict(title="% Receita", color=_MUTED, gridcolor=_GRID),
                    **_base_layout(280))
                st.plotly_chart(_fig_meta_forn, width="stretch", key="lens_meta_chart")

            # Upload tabela de fornecedores
            st.divider()
            st.markdown("##### 📤 Mapear Referências por Fornecedor")
            st.caption(
                "Faça upload de uma planilha com as colunas **Referência** e **Fornecedor** "
                "para identificar cada lente corretamente. O mapeamento pode ser por código exato ou prefixo."
            )
            with st.expander("📂 Upload de tabela de fornecedores"):
                if "forn_upload_key" not in st.session_state:
                    st.session_state["forn_upload_key"] = 0
                _forn_file = st.file_uploader(
                    "Planilha de fornecedores (CSV ou Excel)",
                    type=["csv", "xlsx", "xls"],
                    key=f"forn_uploader_{st.session_state['forn_upload_key']}",
                )
                if _forn_file is not None:
                    try:
                        _fname_f = _forn_file.name.lower()
                        if _fname_f.endswith((".xlsx", ".xls")):
                            import zipfile as _zf2, xml.etree.ElementTree as _ET2, re as _re3
                            from io import BytesIO as _BIO2
                            _raw2 = _forn_file.read()
                            with _zf2.ZipFile(_BIO2(_raw2)) as _z:
                                _sst2: list = []
                                _sst_c = [n for n in _z.namelist() if "sharedStrings" in n or "sharedstrings" in n.lower()]
                                if _sst_c:
                                    _sst_root2 = _ET2.fromstring(_z.read(_sst_c[0]))
                                    for _si in _sst_root2.iter():
                                        if _si.tag.endswith("}si") or _si.tag == "si":
                                            _sst2.append("".join((e.text or "") for e in _si.iter() if e.tag.endswith("}t") or e.tag == "t"))
                                _ws_c = sorted([n for n in _z.namelist() if "worksheets/sheet" in n and n.endswith(".xml")])
                                if not _ws_c: raise ValueError("Planilha não encontrada.")
                                _ws_root2 = _ET2.fromstring(_z.read(_ws_c[0]))
                                _rows2 = []
                                for _row_el in _ws_root2.iter():
                                    if not (_row_el.tag.endswith("}row") or _row_el.tag == "row"): continue
                                    _rd: dict = {}
                                    for _c in _row_el:
                                        if not (_c.tag.endswith("}c") or _c.tag == "c"): continue
                                        _ref2 = _c.get("r", "")
                                        _ltrs = _re3.sub(r"[^A-Za-z]", "", _ref2).upper()
                                        _ci = 0
                                        for _ch in _ltrs: _ci = _ci * 26 + (ord(_ch) - 64)
                                        _ci = max(0, _ci - 1)
                                        _ta = _c.get("t", "n")
                                        _v2 = next((ch for ch in _c if ch.tag.endswith("}v") or ch.tag == "v"), None)
                                        _is2 = next((ch for ch in _c if ch.tag.endswith("}is") or ch.tag == "is"), None)
                                        _val2 = ""
                                        if _is2: _val2 = "".join((e.text or "") for e in _is2.iter() if e.tag.endswith("}t") or e.tag == "t")
                                        elif _v2 and _v2.text:
                                            if _ta == "s":
                                                try: _val2 = _sst2[int(_v2.text)]
                                                except: _val2 = _v2.text
                                            else: _val2 = _v2.text
                                        _rd[_ci] = _val2
                                    if _rd:
                                        _mc2 = max(_rd.keys()) + 1
                                        _rows2.append([_rd.get(i, "") for i in range(_mc2)])
                            if not _rows2: raise ValueError("Planilha vazia.")
                            _mc3 = max(len(r) for r in _rows2)
                            _rows2 = [r + [""] * (_mc3 - len(r)) for r in _rows2]
                            _hdrs2 = [str(h).strip() or f"col_{i}" for i, h in enumerate(_rows2[0])]
                            _df_forn_raw = pd.DataFrame(_rows2[1:], columns=_hdrs2)
                        else:
                            _df_forn_raw = pd.read_csv(_forn_file, sep=None, engine="python", encoding="latin-1", dtype=str)

                        _col_ref_f  = next((c for c in _df_forn_raw.columns if "refer" in c.lower() or c.lower() in ("ref","ref.")), None)
                        _col_forn_f = next((c for c in _df_forn_raw.columns if "forn" in c.lower() or "marca" in c.lower() or "supplier" in c.lower()), None)

                        if _col_ref_f is None or _col_forn_f is None:
                            st.error(f"Colunas não detectadas. Encontradas: {list(_df_forn_raw.columns)}. O arquivo deve ter colunas 'Referência' e 'Fornecedor'.")
                        else:
                            st.markdown(f"**{len(_df_forn_raw)} linhas.** Pré-visualização:")
                            st.dataframe(_df_forn_raw.head(5), width="stretch", hide_index=True)
                            if st.button("✅ Confirmar mapeamento", type="primary", key="btn_confirm_forn"):
                                _new_forn = {}
                                for _, _fr in _df_forn_raw.iterrows():
                                    _rk = str(_fr[_col_ref_f]).strip()
                                    _fv = str(_fr[_col_forn_f]).strip()
                                    if _rk and _fv and _rk.lower() not in ("nan", "none", ""):
                                        _new_forn[_rk] = _fv
                                _merged_forn = {**_forn_map, **_new_forn}
                                _save_forn_map(_merged_forn)
                                st.success(f"✅ {len(_new_forn)} mapeamentos salvos ({len(_merged_forn)} total).")
                                st.session_state["forn_upload_key"] += 1
                                st.rerun()
                    except Exception as _ef:
                        st.error(f"Erro ao ler o arquivo: {_ef}")

                if _forn_map:
                    st.caption(f"Mapeamento atual: {len(_forn_map)} referências cadastradas.")
                    with st.expander("Ver mapeamento atual"):
                        st.dataframe(
                            pd.DataFrame([{"Referência": r, "Fornecedor": f} for r, f in sorted(_forn_map.items())]),
                            width="stretch", hide_index=True,
                        )

            # Tabela Tipo × Fornecedor
            st.divider()
            st.markdown("**Tabela: Tipo × Fornecedor**")
            _tipos_le  = sorted(df_len["tipo_le"].unique())  if "tipo_le"  in df_len.columns else []
            _forn_list = sorted(df_len["fornecedor"].unique()) if "fornecedor" in df_len.columns else []
            _pivot_len = []
            for _fn in _forn_list:
                _row_p = {"Fornecedor": _fn}
                for _tp in _tipos_le:
                    _sub = df_len[(df_len["fornecedor"] == _fn) & (df_len["tipo_le"] == _tp)]
                    _row_p[_tp] = fmt_brl(_sub["vlr_total"].sum()) if not _sub.empty else "—"
                _row_p["Total"] = fmt_brl(df_len[df_len["fornecedor"] == _fn]["vlr_total"].sum())
                _pivot_len.append(_row_p)
            if _pivot_len:
                st.dataframe(pd.DataFrame(_pivot_len), width="stretch", hide_index=True)

    # ════════════════════════════════════════════════════════════════════════
    # ABA 3 — GERAL (todas as categorias)
    # ════════════════════════════════════════════════════════════════════════
    with tab_geral:
        _total_geral  = df["vlr_total"].sum()
        _itens_geral  = int(df["quantidade"].sum())
        _ticket_geral = (_total_geral / _itens_geral) if _itens_geral else 0.0

        m1, m2, m3 = st.columns(3)
        m1.metric("Receita Total",  fmt_brl(_total_geral))
        m2.metric("Ticket Médio",   fmt_brl(_ticket_geral))
        m3.metric("Itens Vendidos", f"{_itens_geral:,}".replace(",", "."))

        st.divider()
        st.markdown('<div class="section-title">📊 Distribuição por Categoria</div>', unsafe_allow_html=True)

        _df_cat_all = build_category_summary(df)
        _col_g1, _col_g2 = st.columns([1, 1], gap="large")
        with _col_g1:
            st.plotly_chart(chart_donut(_df_cat_all, "Mix Geral por Categoria"), width="stretch", key="donut_geral")
        with _col_g2:
            _cat_geral = (
                df.groupby("categoria", as_index=False)
                .agg(receita=("vlr_total", "sum"), itens=("quantidade", "sum"))
                .sort_values("receita", ascending=False)
            )
            if _total_geral > 0:
                _cat_geral["% Receita"] = (_cat_geral["receita"] / _total_geral * 100).round(1).astype(str) + "%"
            else:
                _cat_geral["% Receita"] = "—"
            _cat_geral["Categoria"] = _cat_geral["categoria"].map(lambda c: CAT_NAMES.get(c, c))
            _cat_geral["Receita"]   = _cat_geral["receita"].apply(fmt_brl)
            # Ticket médio = receita ÷ itens (divisão simples) por categoria
            _cat_geral["Ticket Médio"] = _cat_geral.apply(
                lambda r: fmt_brl(r["receita"] / r["itens"]) if r["itens"] > 0 else "—", axis=1
            )
            st.dataframe(
                _cat_geral[["Categoria", "Receita", "% Receita", "itens", "Ticket Médio"]].rename(columns={"itens": "Itens"}),
                width="stretch", hide_index=True,
            )


# ── PAGE: Relatórios ──────────────────────────────────────────────────────────

def page_reports():
    st.markdown('<div class="cb-title">📋 Relatórios</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="cb-sub">Vendas e compras — Armações de Grau (LV), Óculos Solar (OC), Armações Multi (ML)</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns([2, 2, 1.2, 1.2])
    with c1:
        dt_ini = st.date_input("De", value=date.today().replace(day=1), key="rep_ini")
    with c2:
        dt_fim = st.date_input("Até", value=date.today(), key="rep_fim")
    with c3:
        cat_filter = st.selectbox("Categoria", _CATS_ALL, key="rep_cat")
    with c4:
        st.write(""); st.write("")
        load = st.button("🔄 Carregar", key="rep_load", width="stretch")

    if load:
        with st.spinner("Buscando dados..."):
            # Recarrega catálogo do disco — reflete ampliações sem reiniciar o app.
            st.session_state.product_map = load_map()
            api = get_api()
            try:
                if api:
                    _pmap = st.session_state.product_map
                    # ── Endpoints principais (bloqueantes) ──────────────────
                    st.session_state.df_vendas  = api.get_sales(str(dt_ini), str(dt_fim), _pmap)
                    st.session_state.df_compras = api.get_purchases(str(dt_ini), str(dt_fim), _pmap)
                    # ── Endpoints adicionais (não bloqueantes) ──────────────
                    # cod_vendedor já vem em df_vendas via LinxMovimento
                    st.session_state.df_vendedores = st.session_state.df_vendas  # reusa df_vendas
                    try:
                        st.session_state.df_metas = api.get_seller_daily_goals(str(dt_ini), str(dt_fim))
                    except MicrovixAPIError:
                        st.session_state.df_metas = pd.DataFrame()
                else:
                    st.session_state.df_vendas  = mock_vendas(str(dt_ini), str(dt_fim))
                    st.session_state.df_compras = mock_compras(str(dt_ini), str(dt_fim))
                    st.session_state.df_vendedores = st.session_state.df_vendas
                    st.session_state.df_metas   = mock_seller_goals(str(dt_ini), str(dt_fim))
                st.session_state.vendas_loaded_at = datetime.now()
                _n_v = len(st.session_state.df_vendas) if st.session_state.df_vendas is not None else 0
                _n_c = len(st.session_state.df_compras) if st.session_state.df_compras is not None else 0
                if api and (_n_v == 0 and _n_c == 0) and st.session_state.product_map:
                    _map_sz = len(st.session_state.product_map)
                    st.warning(
                        f"⚠️ **0 registros retornados.** O catálogo tem {_map_sz} produto(s) mapeado(s). "
                        "Se o catálogo está desatualizado, atualize em **⚙️ Configurações → Catálogo de Produtos → Importar via API**."
                    )
                else:
                    st.success(f"✅ Vendas: {_n_v:,} · Compras: {_n_c:,} registros carregados.".replace(",", "."))
            except MicrovixAPIError as e:
                st.error(str(e)); return

    # Aviso de dados desatualizados
    _rep_loaded = st.session_state.get("vendas_loaded_at")
    if _rep_loaded:
        _stale_days = (datetime.now() - _rep_loaded).days
        if _stale_days >= 1:
            st.warning(
                f"⚠️ Dados carregados há **{_stale_days} dia(s)** "
                f"({_rep_loaded.strftime('%d/%m/%Y %H:%M')}). "
                "Clique **🔄 Carregar** para atualizar."
            )
        else:
            st.caption(f"Dados de: {_rep_loaded.strftime('%d/%m/%Y %H:%M')}")

    df_v  = st.session_state.df_vendas
    df_c  = st.session_state.df_compras
    df_vd = st.session_state.get("df_vendedores")
    df_mt = st.session_state.get("df_metas")
    df_nf = st.session_state.get("df_nfe")

    # Aviso de catálogo suspeito (muito poucos produtos mapeados)
    _rep_pmap = st.session_state.product_map
    if not cfg.modo_demo and _rep_pmap and len(_rep_pmap) < 10:
        st.warning(
            f"⚠️ **Catálogo com apenas {len(_rep_pmap)} produto(s).** "
            "Reimporte em **⚙️ Configurações → Catálogo de Produtos → Importar via API** para ver os dados reais."
        )

    if df_v is None and df_c is None:
        st.info("Clique em **🔄 Carregar** para buscar os dados.")
        return

    tab_v, tab_c, tab_le, tab_vend, tab_nfe, tab_dev, tab_cidade = st.tabs([
        "🛒  Vendas", "📦  Compras", "👓  Lentes",
        "👥  Vendedores", "🧾  NF-e", "🔄  Devolução", "🗺️  Por Cidade",
    ])

    with tab_v:
        if df_v is None or df_v.empty:
            st.info("Sem dados de vendas para este período.")
        else:
            # Filtro client-side por data e categoria (sem re-fetch)
            dv = df_v.copy()
            if "data" in dv.columns:
                _d_series = pd.to_datetime(dv["data"], errors="coerce").dt.date
                dv = dv[(_d_series >= dt_ini) & (_d_series <= dt_fim)]
            if cat_filter != "Todas":
                dv = dv[dv["categoria"] == cat_filter]
            dv = dv.sort_values("data", ascending=False) if "data" in dv.columns else dv
            if dv.empty:
                st.info("Nenhum item para o filtro selecionado.")
            else:
                _rep_rec   = dv["vlr_total"].sum()
                _rep_itens = int(dv["quantidade"].sum())
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Receita Total",  fmt_brl(_rep_rec))
                m2.metric("Itens Vendidos", f"{_rep_itens:,}".replace(",", "."))
                m3.metric("Ticket Médio",   fmt_brl((_rep_rec / _rep_itens) if _rep_itens else 0.0))
                m4.metric("Registros",      f"{len(dv):,}".replace(",", "."))
                st.divider()
                col_r = {
                    "data": "Data", "referencia": "Referência", "descricao": "Descrição",
                    "categoria": "Cat.", "quantidade": "Qtd",
                    "vlr_unitario": "Preço Unit.", "vlr_total": "Total",
                }
                # Oculta "Descrição" se todos os valores estiverem vazios
                if "descricao" in dv.columns and not dv["descricao"].astype(str).str.strip().any():
                    col_r.pop("descricao", None)
                cols  = [c for c in col_r if c in dv.columns]
                df_sh = dv[cols].rename(columns=col_r).copy()
                if "Preço Unit." in df_sh: df_sh["Preço Unit."] = df_sh["Preço Unit."].apply(fmt_brl)
                if "Total"       in df_sh: df_sh["Total"]       = df_sh["Total"].apply(fmt_brl)
                if "Data"        in df_sh:
                    _d = pd.to_datetime(df_sh["Data"], errors="coerce")
                    df_sh["Data"] = _d.dt.strftime("%d/%m/%Y").fillna("—")
                st.dataframe(df_sh, width="stretch", hide_index=True, height=400)
                st.download_button("⬇️ Excel", data=to_excel({"Vendas": dv}),
                                   file_name=f"vendas_{dt_ini}_{dt_fim}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tab_c:
        if df_c is None or df_c.empty:
            st.info("Sem dados de compras para este período.")
        else:
            # Filtro client-side por data e categoria
            dc = df_c.copy()
            if "data" in dc.columns:
                _d_series_c = pd.to_datetime(dc["data"], errors="coerce").dt.date
                dc = dc[(_d_series_c >= dt_ini) & (_d_series_c <= dt_fim)]
            if cat_filter != "Todas":
                dc = dc[dc["categoria"] == cat_filter]
            dc = dc.sort_values("data", ascending=False) if "data" in dc.columns else dc
            if dc.empty:
                st.info("Nenhum item para o filtro selecionado.")
            else:
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Compras", fmt_brl(dc["vlr_total"].sum()))
                m2.metric("Itens Pedidos", f"{int(dc['quantidade'].sum()):,}".replace(",", "."))
                m3.metric("Registros",     f"{len(dc):,}".replace(",", "."))
                st.divider()
                col_r = {
                    "data": "Data", "referencia": "Referência", "descricao": "Descrição",
                    "categoria": "Cat.", "fornecedor": "Fornecedor", "quantidade": "Qtd",
                    "vlr_unitario": "Custo Unit.", "vlr_total": "Total", "status": "Status",
                }
                # Oculta "Descrição" se todos os valores estiverem vazios
                if "descricao" in dc.columns and not dc["descricao"].astype(str).str.strip().any():
                    col_r.pop("descricao", None)
                cols  = [c for c in col_r if c in dc.columns]
                df_sh = dc[cols].rename(columns=col_r).copy()
                if "Custo Unit." in df_sh: df_sh["Custo Unit."] = df_sh["Custo Unit."].apply(fmt_brl)
                if "Total"       in df_sh: df_sh["Total"]       = df_sh["Total"].apply(fmt_brl)
                if "Data"        in df_sh:
                    _d = pd.to_datetime(df_sh["Data"], errors="coerce")
                    df_sh["Data"] = _d.dt.strftime("%d/%m/%Y").fillna("—")
                st.dataframe(df_sh, width="stretch", hide_index=True, height=400)
                st.download_button("⬇️ Excel", data=to_excel({"Compras": dc}),
                                   file_name=f"compras_{dt_ini}_{dt_fim}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tab_le:
        _dv_le = df_v.copy() if df_v is not None and not df_v.empty else pd.DataFrame()
        if _dv_le.empty or "categoria" not in _dv_le.columns:
            st.info("Sem dados de lentes para este período. Carregue os dados primeiro.")
        else:
            if "data" in _dv_le.columns:
                _ds_le = pd.to_datetime(_dv_le["data"], errors="coerce").dt.date
                _dv_le = _dv_le[(_ds_le >= dt_ini) & (_ds_le <= dt_fim)]
            _dv_le = _dv_le[_dv_le["categoria"] == "LE"].copy()
            if _dv_le.empty:
                st.info("Nenhuma venda de lentes (LE) no período selecionado.")
            else:
                if "descricao" in _dv_le.columns:
                    _dv_le["Marca"] = _dv_le["descricao"].apply(detect_brand)
                else:
                    _dv_le["Marca"] = "Outros"

                _lm1, _lm2, _lm3 = st.columns(3)
                _lm1.metric("Receita Lentes",      fmt_brl(_dv_le["vlr_total"].sum()))
                _lm2.metric("Itens Vendidos",       f"{int(_dv_le['quantidade'].sum()):,}".replace(",", "."))
                _lm3.metric("Registros",            f"{len(_dv_le):,}".replace(",", "."))
                st.divider()

                _brands_avail = ["Todas as marcas"] + sorted(_dv_le["Marca"].unique().tolist())
                _brand_filter = st.selectbox("Filtrar por marca", _brands_avail, key="le_brand_filter")
                if _brand_filter != "Todas as marcas":
                    _dv_le = _dv_le[_dv_le["Marca"] == _brand_filter]

                _le_col_r = {
                    "data": "Data", "referencia": "Referência", "descricao": "Descrição (Microvix)",
                    "Marca": "Marca", "quantidade": "Qtd",
                    "vlr_unitario": "Preço Unit.", "vlr_total": "Total",
                }
                _cols_le = [c for c in _le_col_r if c in _dv_le.columns]
                _df_le_show = _dv_le[_cols_le].rename(columns=_le_col_r).copy()
                if "Preço Unit." in _df_le_show:
                    _df_le_show["Preço Unit."] = _df_le_show["Preço Unit."].apply(fmt_brl)
                if "Total" in _df_le_show:
                    _df_le_show["Total"] = _df_le_show["Total"].apply(fmt_brl)
                if "Data" in _df_le_show:
                    _df_le_show["Data"] = pd.to_datetime(_df_le_show["Data"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("—")
                if "Data" in _df_le_show.columns:
                    _df_le_show = _df_le_show.sort_values("Data", ascending=False)
                st.dataframe(_df_le_show, width="stretch", hide_index=True, height=400)
                st.download_button(
                    "⬇️ Excel",
                    data=to_excel({"Lentes": _dv_le.drop(columns=["Marca"], errors="ignore")}),
                    file_name=f"lentes_{dt_ini}_{dt_fim}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_lentes",
                )

    # ── Aba Vendedores ────────────────────────────────────────────────────────
    with tab_vend:
        # Usa df_vendas (LinxMovimento) que já tem cod_vendedor
        _df_vd_src = df_v  # df_vendas já carregado na aba Vendas
        if _df_vd_src is None or (hasattr(_df_vd_src, "empty") and _df_vd_src.empty):
            st.info("Clique em **🔄 Carregar** para buscar os dados de vendedores.")
        elif "cod_vendedor" not in _df_vd_src.columns:
            st.warning(
                "⚠️ Campo `cod_vendedor` não encontrado nos dados. "
                "Recarregue os dados clicando em **🔄 Carregar**."
            )
        else:
            st.markdown('<div class="section-title">👥 Desempenho por Vendedor</div>',
                        unsafe_allow_html=True)
            st.caption("Fonte: LinxMovimento (campo cod_vendedor) — agrupado por código de vendedor.")

            # Filtra pelo período selecionado
            _vd = _df_vd_src.copy()
            if "data" in _vd.columns:
                _ds_vd = pd.to_datetime(_vd["data"], errors="coerce").dt.date
                _vd = _vd[(_ds_vd >= dt_ini) & (_ds_vd <= dt_fim)]
            if cat_filter != "Todas" and "categoria" in _vd.columns:
                _vd = _vd[_vd["categoria"] == cat_filter]

            # Remove linhas sem vendedor
            _vd = _vd[_vd["cod_vendedor"].astype(str).str.strip() != ""]

            if _vd.empty:
                st.info("Nenhuma venda com código de vendedor no período selecionado.")
            else:
                # ── KPIs ──────────────────────────────────────────────────────
                _n_docs = _vd["num_documento"].nunique() if "num_documento" in _vd.columns else len(_vd)
                _vd_rec   = _vd["vlr_total"].sum()
                _vd_itens = int(_vd["quantidade"].sum())
                _vd_k1, _vd_k2, _vd_k3, _vd_k4 = st.columns(4)
                _vd_k1.metric("Vendedores ativos",  str(_vd["cod_vendedor"].nunique()))
                _vd_k2.metric("Documentos",          f"{_n_docs:,}".replace(",", "."))
                _vd_k3.metric("Receita total",       fmt_brl(_vd_rec))
                _vd_k4.metric("Ticket médio/item",   fmt_brl((_vd_rec / _vd_itens) if _vd_itens else 0.0))

                st.divider()

                # ── Ranking por vendedor ──────────────────────────────────────
                st.markdown("#### 🏆 Ranking por Código de Vendedor")
                _agg_vd = (
                    _vd.groupby("cod_vendedor", as_index=False)
                    .agg(
                        itens=("quantidade", "sum"),
                        receita=("vlr_total", "sum"),
                        ticket=("vlr_unitario", "mean"),
                    )
                    .sort_values("receita", ascending=False)
                    .reset_index(drop=True)
                )
                _total_vd = _agg_vd["receita"].sum()
                _agg_vd["% Receita"] = (
                    (_agg_vd["receita"] / _total_vd * 100).round(1).astype(str) + "%"
                    if _total_vd > 0 else "—"
                )
                _agg_vd["Posição"] = range(1, len(_agg_vd) + 1)

                # Gráfico de barras horizontal
                _fig_vd = go.Figure(go.Bar(
                    x=_agg_vd["receita"],
                    y=_agg_vd["cod_vendedor"].astype(str).apply(lambda x: f"Vendedor {x}"),
                    orientation="h",
                    marker_color="#E84300",
                    text=[fmt_brl(v) for v in _agg_vd["receita"]],
                    textposition="outside",
                ))
                _fig_vd.update_layout(
                    title="Receita por Vendedor",
                    xaxis=dict(title="Receita (R$)", color=_MUTED, gridcolor=_GRID),
                    yaxis=dict(color=_TEXT, autorange="reversed"),
                    **_base_layout(max(280, len(_agg_vd) * 40 + 60)),
                )
                st.plotly_chart(_fig_vd, width="stretch", key="chart_rank_vd")

                # Tabela detalhada
                _agg_display = _agg_vd.copy()
                _agg_display["Receita"] = _agg_display["receita"].apply(fmt_brl)
                _agg_display["Ticket"]  = _agg_display["ticket"].apply(fmt_brl)
                _agg_display["Itens"]   = _agg_display["itens"].apply(lambda x: f"{int(x):,}".replace(",", "."))
                _agg_display["Vendedor"] = _agg_display["cod_vendedor"].astype(str).apply(lambda x: f"Vendedor {x}")
                st.dataframe(
                    _agg_display[["Posição", "Vendedor", "Itens", "Receita", "% Receita", "Ticket"]],
                    width="stretch", hide_index=True,
                )

                # ── Metas (se disponível) ─────────────────────────────────────
                if df_mt is not None and not (hasattr(df_mt, "empty") and df_mt.empty):
                    st.divider()
                    st.markdown("#### 🎯 Metas × Realizado")
                    _mt = df_mt.copy()
                    if "data" in _mt.columns:
                        _ds_mt = pd.to_datetime(_mt["data"], errors="coerce").dt.date
                        _mt = _mt[(_ds_mt >= dt_ini) & (_ds_mt <= dt_fim)]
                    if not _mt.empty:
                        _agg_mt = (
                            _mt.groupby(["cod_vendedor", "nome_vendedor"], as_index=False)
                            .agg(meta_total=("meta_dia", "sum"), realizado=("vlr_vendido", "sum"))
                        )
                        # Divisão segura: 0/0 → 0, vendido/0 → 999 (clipado)
                        _agg_mt["% Atingido"] = _agg_mt.apply(
                            lambda r: 0.0 if r["meta_total"] <= 0
                            else round(min(999.0, r["realizado"] / r["meta_total"] * 100), 1),
                            axis=1,
                        )
                        _mt_fig = go.Figure()
                        _mt_fig.add_trace(go.Bar(name="Meta", x=_agg_mt["nome_vendedor"], y=_agg_mt["meta_total"], marker_color="#AAA"))
                        _mt_fig.add_trace(go.Bar(name="Realizado", x=_agg_mt["nome_vendedor"], y=_agg_mt["realizado"], marker_color="#E84300"))
                        _mt_fig.update_layout(barmode="group", title="Meta × Realizado", **_base_layout(320))
                        st.plotly_chart(_mt_fig, width="stretch", key="chart_metas_vd")

                st.divider()
                _export_vd = _vd[["data", "cod_vendedor", "categoria", "quantidade", "vlr_unitario", "vlr_total"]].copy()
                st.download_button(
                    "⬇️ Excel",
                    data=to_excel({"Vendas por Vendedor": _export_vd}),
                    file_name=f"vendedores_{dt_ini}_{dt_fim}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_vendedores",
                )

    # ── Aba NF-e ──────────────────────────────────────────────────────────────
    with tab_nfe:
        st.markdown('<div class="section-title">🧾 Notas Fiscais</div>', unsafe_allow_html=True)

        # ── Carga independente via Microvix ───────────────────────────────────
        _nfe_c1, _nfe_c2 = st.columns([4, 1])
        with _nfe_c1:
            st.caption(
                "Os dados de NF-e são carregados de forma independente — "
                "use o botão ao lado ou a busca SEFAZ abaixo."
            )
        with _nfe_c2:
            _btn_nfe_load = st.button("🔄 Carregar NF-e", key="btn_nfe_microvix", width="stretch")
        if _btn_nfe_load:
            with st.spinner("Buscando notas fiscais no Microvix..."):
                _nfe_api = get_api()
                try:
                    if _nfe_api:
                        _df_nfe_novo = _nfe_api.get_nfe(str(dt_ini), str(dt_fim))
                    else:
                        _df_nfe_novo = mock_nfe(str(dt_ini), str(dt_fim))
                    st.session_state.df_nfe = _df_nfe_novo
                    _n_nfe = len(_df_nfe_novo) if _df_nfe_novo is not None else 0
                    st.success(f"✅ {_n_nfe:,} notas carregadas.".replace(",", "."))
                except MicrovixAPIError as _nfe_err:
                    st.error(str(_nfe_err))
                    st.session_state.df_nfe = pd.DataFrame()

        def _render_nf_subtab(df_nf_sub, sub_key: str, tipo_label: str):
            """Renderiza tabela de NF com exports CSV/XML/HTML (print como PDF)."""
            if df_nf_sub is None or (hasattr(df_nf_sub, "empty") and df_nf_sub.empty):
                st.info(f"Nenhuma {tipo_label} encontrada no período. Carregue os dados ou verifique se o endpoint está habilitado.")
                return

            _nf = df_nf_sub.copy()
            if "data_emissao" in _nf.columns:
                _ds_nf = pd.to_datetime(_nf["data_emissao"], errors="coerce").dt.date
                _nf = _nf[(_ds_nf >= dt_ini) & (_ds_nf <= dt_fim)]

            if _nf.empty:
                st.info(f"Nenhuma {tipo_label} no período selecionado.")
                return

            _n_total   = len(_nf)
            _n_aut     = int((_nf["situacao"].str.contains("Autoriza", case=False, na=False)).sum()) if "situacao" in _nf.columns else 0
            _n_canc    = int((_nf["situacao"].str.contains("Cancela",  case=False, na=False)).sum()) if "situacao" in _nf.columns else 0
            _vol_total = _nf[_nf["situacao"].str.contains("Autoriza", case=False, na=False)]["vlr_total"].sum() if "situacao" in _nf.columns and "vlr_total" in _nf.columns else 0

            _nf_k1, _nf_k2, _nf_k3, _nf_k4 = st.columns(4)
            _nf_k1.metric("Total",          f"{_n_total:,}".replace(",", "."))
            _nf_k2.metric("Autorizadas",    f"{_n_aut:,}".replace(",", "."))
            _nf_k3.metric("Canceladas",     f"{_n_canc:,}".replace(",", "."))
            _nf_k4.metric("Volume Autorizado", fmt_brl(_vol_total))
            st.divider()

            _nf_show = _nf.copy()
            if "data_emissao" in _nf_show.columns:
                _nf_show["data_emissao"] = (
                    pd.to_datetime(_nf_show["data_emissao"], errors="coerce")
                    .dt.strftime("%d/%m/%Y").fillna("—")
                )
            if "vlr_total" in _nf_show.columns:
                _nf_show["vlr_total_fmt"] = _nf_show["vlr_total"].apply(fmt_brl)
            # Preserva chave completa em _nf_show; usa cópia truncada apenas para o dataframe na tela.
            _nf_col_r = {
                "numero": "Número", "serie": "Série", "data_emissao": "Data Emissão",
                "vlr_total_fmt": "Valor Total", "situacao": "Situação",
                "chave": "Chave", "cod_cliente": "Cód. Cliente",
            }
            _nf_cols = [c for c in _nf_col_r if c in _nf_show.columns]
            _df_display = _nf_show[_nf_cols].rename(columns=_nf_col_r)
            if "Data Emissão" in _df_display.columns:
                _df_display = _df_display.sort_values("Data Emissão", ascending=False)
            # _df_display preserva chave completa p/ exports (CSV/XML/HTML).
            # _df_view só trunca a chave em tela para não estourar a coluna.
            _df_view = _df_display.copy()
            if "Chave" in _df_view.columns:
                _df_view["Chave"] = _df_view["Chave"].apply(
                    lambda x: str(x)[:20] + "…" if len(str(x)) > 20 else str(x)
                )
            st.dataframe(_df_view, width="stretch", hide_index=True, height=400)

            # ── Botões de exportação ─────────────────────────────────────────
            _ec1, _ec2, _ec3 = st.columns(3)
            with _ec1:
                _csv_bytes = _nf.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button(
                    "📥 CSV",
                    data=_csv_bytes,
                    file_name=f"nfe_{sub_key}_{dt_ini}_{dt_fim}.csv",
                    mime="text/csv",
                    key=f"dl_nfe_csv_{sub_key}",
                )
            with _ec2:
                # Gera XML simples — escape correto contra &, <, >, ", '
                from xml.sax.saxutils import escape as _xescape, quoteattr as _xquoteattr
                _xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<NotasFiscais>"]
                for _, _xrow in _nf.iterrows():
                    _attrs = " ".join(
                        f"{k}={_xquoteattr(str(v))}"
                        for k, v in _xrow.items()
                        if pd.notna(v)
                    )
                    _xml_lines.append(f"  <NF {_attrs}/>")
                _xml_lines.append("</NotasFiscais>")
                _xml_bytes = "\n".join(_xml_lines).encode("utf-8")
                st.download_button(
                    "📄 XML",
                    data=_xml_bytes,
                    file_name=f"nfe_{sub_key}_{dt_ini}_{dt_fim}.xml",
                    mime="application/xml",
                    key=f"dl_nfe_xml_{sub_key}",
                )
            with _ec3:
                # Gera HTML para impressão como PDF — escape contra <, >, &, ", '
                from html import escape as _hescape
                _html_rows = "".join(
                    "<tr>" + "".join(f"<td>{_hescape(str(v))}</td>" for v in row) + "</tr>"
                    for row in _df_display.itertuples(index=False)
                )
                _html_headers = "".join(f"<th>{_hescape(str(c))}</th>" for c in _df_display.columns)
                _tipo_label_safe = _hescape(str(tipo_label))
                _dt_ini_safe = _hescape(str(dt_ini))
                _dt_fim_safe = _hescape(str(dt_fim))
                _html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>Relatório {_tipo_label_safe} — {_dt_ini_safe} a {_dt_fim_safe}</title>
<style>
  body{{font-family:Arial,sans-serif;font-size:11px;margin:20px}}
  h2{{color:#E84300}} table{{border-collapse:collapse;width:100%}}
  th,td{{border:1px solid #ccc;padding:4px 6px;text-align:left}}
  th{{background:#E84300;color:#fff}} tr:nth-child(even){{background:#f9f9f9}}
  @media print{{.no-print{{display:none}}}}
</style></head>
<body>
<h2>Pepper · Chilli Beans — {_tipo_label_safe}</h2>
<p>Período: {_dt_ini_safe} a {_dt_fim_safe} &nbsp;|&nbsp; Gerado em: {date.today().strftime('%d/%m/%Y')}</p>
<button class="no-print" onclick="window.print()" style="background:#E84300;color:#fff;border:none;padding:6px 14px;cursor:pointer;border-radius:4px;margin-bottom:10px">🖨️ Imprimir / Salvar como PDF</button>
<table><thead><tr>{_html_headers}</tr></thead><tbody>{_html_rows}</tbody></table>
</body></html>"""
                st.download_button(
                    "🖨️ PDF (HTML)",
                    data=_html_doc.encode("utf-8"),
                    file_name=f"nfe_{sub_key}_{dt_ini}_{dt_fim}.html",
                    mime="text/html",
                    key=f"dl_nfe_pdf_{sub_key}",
                    help="Abre no navegador e use Ctrl+P (ou Cmd+P) para salvar como PDF.",
                )

        # ── Busca via SEFAZ ──────────────────────────────────────────────────
        st.divider()
        st.markdown("##### 🏛️ Busca via SEFAZ (Certificado Digital A1)")
        _sefaz_cert_ok = bool(cfg.get("sefaz_cert_b64", ""))
        if not _sefaz_cert_ok:
            st.info(
                "Certificado Digital não configurado. "
                "Vá em **Configurações → 🔑 Credenciais** e faça upload do seu .pfx."
            )
        else:
            st.caption(
                "Consulta NF-e / CT-e diretamente da SEFAZ Nacional por NSU incremental. "
                "Traz todas as notas endereçadas ao seu CNPJ (entrada e saída)."
            )
            _sf_c1, _sf_c2, _sf_c3 = st.columns([1, 1, 2])
            with _sf_c1:
                _nsu_input = st.text_input(
                    "A partir do NSU",
                    value=str(cfg.get("sefaz_ultimo_nsu", "0")).lstrip("0") or "0",
                    key="sefaz_nsu_input",
                    help="0 = busca todos os documentos disponíveis. Após cada consulta, o NSU é atualizado automaticamente.",
                )
            with _sf_c2:
                _max_pag = st.number_input(
                    "Máx. páginas (50 docs/pág)",
                    min_value=1, max_value=50,
                    value=5, step=1, key="sefaz_max_pag",
                )
            with _sf_c3:
                st.write("")  # espaçador
                st.write("")
                _btn_sefaz_buscar = st.button(
                    "📡 Buscar via SEFAZ",
                    type="primary",
                    key="btn_sefaz_buscar",
                    width="stretch",
                )

            if _btn_sefaz_buscar:
                _b64  = cfg.get("sefaz_cert_b64", "")
                _pw   = cfg.get("sefaz_cert_password", "")
                _uf   = cfg.get("sefaz_uf", "35")
                _amb  = cfg.get("sefaz_ambiente", 1)
                _cnpj = cfg.get("cnpj", "")
                if not _cnpj:
                    st.warning("Configure o CNPJ em **Configurações → 🔑 Credenciais** antes de buscar.")
                else:
                    with st.spinner("Consultando SEFAZ... isso pode levar alguns segundos."):
                        try:
                            _pfx_bytes = base64.b64decode(_b64)
                            _sf_cli = SefazClient(
                                _pfx_bytes, _pw, cnpj=_cnpj,
                                uf=str(_uf), ambiente=int(_amb),
                            )
                            _nsu_from = str(_nsu_input).strip() or "0"
                            _docs_parsed, _novo_nsu = _sf_cli.buscar_notas(
                                ultimo_nsu=_nsu_from,
                                max_paginas=int(_max_pag),
                            )
                            # Salva novo NSU
                            cfg.set("sefaz_ultimo_nsu", _novo_nsu)
                            cfg.save()

                            if not _docs_parsed:
                                st.info("✅ Nenhum documento novo encontrado no SEFAZ para este NSU.")
                            else:
                                st.success(
                                    f"✅ **{len(_docs_parsed)}** documento(s) recebido(s)! "
                                    f"Novo NSU: **{_novo_nsu}**"
                                )
                                # Monta DataFrame
                                _df_sefaz = pd.DataFrame(_docs_parsed)
                                # Formata colunas para exibição
                                _col_map_sf = {
                                    "tipo": "Tipo", "chave": "Chave", "numero": "Número",
                                    "serie": "Série", "data_emissao": "Data Emissão",
                                    "emitente": "Emitente", "cnpj_emit": "CNPJ Emitente",
                                    "valor": "Valor (R$)", "situacao": "Situação",
                                }
                                _cols_sf = [c for c in _col_map_sf if c in _df_sefaz.columns]
                                _df_sf_show = _df_sefaz[_cols_sf].copy()
                                if "valor" in _df_sf_show.columns:
                                    _df_sf_show["valor"] = _df_sf_show["valor"].apply(
                                        lambda v: fmt_brl(float(v)) if v else "—"
                                    )
                                if "chave" in _df_sf_show.columns:
                                    _df_sf_show["chave"] = _df_sf_show["chave"].apply(
                                        lambda x: str(x)[:20] + "…" if len(str(x)) > 20 else str(x)
                                    )
                                _df_sf_show = _df_sf_show.rename(columns=_col_map_sf)
                                st.dataframe(_df_sf_show, hide_index=True, width="stretch", height=400)

                                # Export CSV
                                _csv_sf = _df_sefaz.drop(columns=["xml_raw"], errors="ignore").to_csv(
                                    index=False, sep=";", encoding="utf-8-sig"
                                ).encode("utf-8-sig")
                                st.download_button(
                                    "📥 Exportar CSV",
                                    data=_csv_sf,
                                    file_name=f"sefaz_nfe_nsu{_nsu_from}.csv",
                                    mime="text/csv",
                                    key="dl_sefaz_csv",
                                )

                        except SefazError as _se:
                            st.error(f"❌ Erro SEFAZ: {_se}")
                        except Exception as _ge:
                            st.error(f"❌ Erro inesperado: {_ge}")

        st.divider()
        if df_nf is None:
            st.info("Clique em **🔄 Carregar NF-e** acima para buscar as notas fiscais via Microvix.")
        else:
            _nfe_sub1, _nfe_sub2, _nfe_sub3, _nfe_sub4 = st.tabs([
                "📄  NF-e / NFCe Saída", "📥  NF-e Entrada", "🧾  NF-Se", "🚛  CT-e Entrada",
            ])
            with _nfe_sub1:
                _render_nf_subtab(df_nf, "saida", "NF-e / NFCe Saída")
            with _nfe_sub2:
                st.info("NF-e de Entrada: endpoint não disponível para esta conta. Carregue os dados via CSV externo.")
            with _nfe_sub3:
                st.info("NF-Se (Serviços): endpoint não disponível para esta conta.")
            with _nfe_sub4:
                st.info("CT-e Entrada: endpoint não disponível para esta conta.")

    # ── Aba Devolução / Troca ────────────────────────────────────────────────
    with tab_dev:
        st.markdown('<div class="section-title">🔄 Sugestão de Devolução / Troca</div>', unsafe_allow_html=True)
        st.caption(
            "Identifica referências com alto tempo em estoque e baixa velocidade de venda — "
            "candidatas a devolução ou troca com o fornecedor."
        )

        _dev_df_c = st.session_state.df_compras
        _dev_df_v = st.session_state.df_vendas

        if (_dev_df_c is None or (hasattr(_dev_df_c, "empty") and _dev_df_c.empty)):
            st.info("Carregue os dados de **Compras** clicando em 🔄 Carregar.")
        elif (_dev_df_v is None or (hasattr(_dev_df_v, "empty") and _dev_df_v.empty)):
            st.info("Carregue os dados de **Vendas** clicando em 🔄 Carregar.")
        else:
            _min_dias_dev = st.slider(
                "Filtro: mínimo de dias em estoque", min_value=30, max_value=720,
                value=90, step=30, key="dev_min_dias",
                help="Mostra apenas itens comprados há mais de N dias.",
            )

            _today_dev = date.today()

            # Agrega compras: data mais antiga por referência
            _dev_comp = _dev_df_c.copy()
            if "data" in _dev_comp.columns:
                _dev_comp["data"] = pd.to_datetime(_dev_comp["data"], errors="coerce")
            _comp_agg = (
                _dev_comp.groupby(["referencia", "categoria"], as_index=False)
                .agg(
                    data_compra_mais_antiga=("data", "min"),
                    qtd_comprada=("quantidade", "sum"),
                    custo_total=("vlr_total", "sum"),
                )
            )
            _comp_agg["dias_estoque"] = _comp_agg["data_compra_mais_antiga"].apply(
                lambda d: (_today_dev - pd.Timestamp(d).date()).days if pd.notna(d) else 0
            )

            # Agrega vendas por referência
            _dev_vend = _dev_df_v.copy()
            _vend_agg = (
                _dev_vend.groupby("referencia", as_index=False)
                .agg(qtd_vendida=("quantidade", "sum"), receita=("vlr_total", "sum"))
            ) if "referencia" in _dev_vend.columns else pd.DataFrame(columns=["referencia", "qtd_vendida", "receita"])

            # Junta compras + vendas
            _dev_merged = _comp_agg.merge(_vend_agg, on="referencia", how="left")
            _dev_merged["qtd_vendida"]  = _dev_merged["qtd_vendida"].fillna(0)
            _dev_merged["receita"]       = _dev_merged["receita"].fillna(0)
            _dev_merged["saldo_est"]     = (_dev_merged["qtd_comprada"] - _dev_merged["qtd_vendida"]).clip(lower=0)

            # Filtra por mínimo de dias
            _dev_filtered = _dev_merged[_dev_merged["dias_estoque"] >= _min_dias_dev].copy()
            _dev_filtered = _dev_filtered.sort_values("dias_estoque", ascending=False).reset_index(drop=True)

            def _acao_dev(dias):
                if dias > 180:
                    return "🔄 Devolver"
                if dias > 90:
                    return "⚠️ Avaliar"
                return "✅ OK"

            _dev_filtered["Ação Sugerida"] = _dev_filtered["dias_estoque"].apply(_acao_dev)

            # KPIs
            _n_devolver = int((_dev_filtered["Ação Sugerida"] == "🔄 Devolver").sum())
            _n_avaliar  = int((_dev_filtered["Ação Sugerida"] == "⚠️ Avaliar").sum())
            _media_dias = int(_dev_filtered["dias_estoque"].mean()) if not _dev_filtered.empty else 0
            _val_recup  = _dev_filtered[_dev_filtered["Ação Sugerida"] == "🔄 Devolver"]["custo_total"].sum()

            _dk1, _dk2, _dk3, _dk4 = st.columns(4)
            _dk1.metric("Para devolver",     f"{_n_devolver} refs")
            _dk2.metric("Para avaliar",       f"{_n_avaliar} refs")
            _dk3.metric("Média dias em est.", f"{_media_dias} dias")
            _dk4.metric("Valor recuperável",  fmt_brl(_val_recup),
                        help="Custo total das referências marcadas como 'Devolver'.")

            st.divider()

            if _dev_filtered.empty:
                st.info(f"Nenhuma referência com mais de {_min_dias_dev} dias em estoque.")
            else:
                _dev_show = _dev_filtered[[
                    "referencia", "categoria", "data_compra_mais_antiga",
                    "dias_estoque", "qtd_comprada", "qtd_vendida", "saldo_est",
                    "receita", "Ação Sugerida",
                ]].copy()
                _dev_show["data_compra_mais_antiga"] = pd.to_datetime(
                    _dev_show["data_compra_mais_antiga"], errors="coerce"
                ).dt.strftime("%d/%m/%Y").fillna("—")
                _dev_show["receita_fmt"] = _dev_show["receita"].apply(fmt_brl)
                _dev_show = _dev_show.rename(columns={
                    "referencia":             "Referência",
                    "categoria":              "Categoria",
                    "data_compra_mais_antiga": "Data Compra",
                    "dias_estoque":           "Dias em Estoque",
                    "qtd_comprada":           "Qtd Comprada",
                    "qtd_vendida":            "Qtd Vendida",
                    "saldo_est":              "Saldo Est.",
                    "receita_fmt":            "Receita",
                })
                _dev_cols_show = [
                    "Referência", "Categoria", "Data Compra", "Dias em Estoque",
                    "Qtd Comprada", "Qtd Vendida", "Saldo Est.", "Receita", "Ação Sugerida",
                ]
                st.dataframe(
                    _dev_show[[c for c in _dev_cols_show if c in _dev_show.columns]],
                    width="stretch", hide_index=True,
                    height=min(600, 80 + len(_dev_show) * 35),
                    column_config={
                        "Dias em Estoque": st.column_config.NumberColumn("Dias em Est.", format="%d"),
                        "Qtd Comprada":    st.column_config.NumberColumn("Qtd Comprada", format="%d"),
                        "Qtd Vendida":     st.column_config.NumberColumn("Qtd Vendida",  format="%d"),
                        "Saldo Est.":      st.column_config.NumberColumn("Saldo",        format="%d"),
                    },
                )
                _dev_export = _dev_filtered.rename(columns={
                    "referencia": "Referência", "categoria": "Categoria",
                    "data_compra_mais_antiga": "Data Compra", "dias_estoque": "Dias em Estoque",
                    "qtd_comprada": "Qtd Comprada", "qtd_vendida": "Qtd Vendida",
                    "saldo_est": "Saldo Est.", "receita": "Receita",
                })
                st.download_button(
                    "📥 Exportar Excel",
                    data=to_excel({"Devolução": _dev_export}),
                    file_name=f"devolucao_{date.today().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_devolucao",
                )

    # ── Aba Por Cidade (CIDADE-NORM) ──────────────────────────────────────────
    with tab_cidade:
        st.markdown('<div class="section-title">🗺️ Distribuição por Cidade</div>', unsafe_allow_html=True)
        st.caption("Base de cidades normalizada — construída a partir do cadastro de clientes.")
        _cmap_cid = st.session_state.client_map or {}
        if not _cmap_cid:
            st.info("Importe o cadastro de clientes em ⚙️ Configurações → Clientes.")
        else:
            from collections import Counter
            _cidade_uf = Counter()
            for info in _cmap_cid.values():
                _cid = str(info.get("cidade","") or "").strip().title()
                _uf  = str(info.get("uf","") or "").strip().upper()
                if _cid and _cid.lower() not in ("nan","none",""):
                    _cidade_uf[(_cid, _uf)] += 1
            _cid_rows = [
                {"Cidade": c, "UF": u, "Clientes": n}
                for (c,u),n in sorted(_cidade_uf.items(), key=lambda x:-x[1])
            ]
            if not _cid_rows:
                st.info("Nenhuma cidade identificada no cadastro.")
            else:
                _df_cid = pd.DataFrame(_cid_rows)
                _total_cid = _df_cid["Clientes"].sum()
                _df_cid["% Base"] = (_df_cid["Clientes"] / _total_cid * 100).round(1).astype(str) + "%"

                # KPIs
                _cc1, _cc2, _cc3 = st.columns(3)
                _cc1.metric("Cidades cadastradas", len(_cid_rows))
                _cc2.metric("Clientes com cidade", int(_total_cid))
                _cc3.metric("Sem cidade", len(_cmap_cid) - int(_total_cid))

                # Gráfico top 15
                _top15 = _df_cid.head(15)
                _fig_cid = go.Figure(go.Bar(
                    x=_top15["Clientes"], y=_top15["Cidade"] + " (" + _top15["UF"] + ")",
                    orientation="h", marker_color="#E84300",
                    text=_top15["% Base"], textposition="outside",
                ))
                _fig_cid.update_layout(
                    title=dict(text="Top 15 cidades", font=dict(color=_TEXT, size=13)),
                    xaxis=dict(color=_MUTED, gridcolor=_GRID),
                    yaxis=dict(autorange="reversed", color=_TEXT),
                    **_base_layout(400),
                )
                st.plotly_chart(_fig_cid, width="stretch", key="chart_cidades")

                st.dataframe(_df_cid, hide_index=True, width="stretch")
                st.download_button(
                    "📥 Exportar por Cidade",
                    data=to_excel({"Por Cidade": _df_cid}),
                    file_name=f"clientes_por_cidade_{date.today().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_cidade",
                )


# ── PAGE: Configurações ───────────────────────────────────────────────────────

def page_settings():
    st.markdown('<div class="cb-title">⚙️ Configurações</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="cb-sub">Credenciais Microvix, catálogo de produtos, faixas de preço e estoque ideal</div>',
        unsafe_allow_html=True,
    )

    tab_cred, tab_cat, tab_tiers, tab_stock, tab_cli, tab_meta, tab_users = st.tabs([
        "🔑  Credenciais", "📦  Catálogo", "💰  Faixas de Preço",
        "📦  Estoque", "👥  Clientes", "🎯  Meta de Mix", "👤  Usuários",
    ])

    # ── Credenciais ──────────────────────────────────────────────────────────
    with tab_cred:
        col_form, col_help = st.columns([2, 1], gap="large")
        with col_form:
            st.markdown("#### Acesso ao WebService Microvix")
            modo_demo = st.toggle("Modo Demonstração (dados fictícios)", value=cfg.modo_demo)
            st.divider()
            nome_empresa = st.text_input("Nome da Empresa", value=cfg.get("nome_empresa", ""), placeholder="OTICAS CHILLI BEANS")
            cnpj         = st.text_input("CNPJ (somente números)", value=cfg.get("cnpj", ""), placeholder="00000000000000", max_chars=14)
            token        = st.text_input("Token de Integração", value=cfg.get("token", ""), type="password")
            base_url     = st.text_input("URL do WebService", value=cfg.get("base_url", "http://webapi.microvix.com.br/1.0/api/integracao"))
            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Salvar", type="primary", width="stretch"):
                    cfg.set("modo_demo", modo_demo)
                    cfg.set("nome_empresa", nome_empresa.strip())
                    cfg.set("cnpj", "".join(filter(str.isdigit, cnpj)))
                    cfg.set("token", token.strip())
                    cfg.set("base_url", base_url.strip())
                    cfg.save()
                    st.success("Configurações salvas!")
                    st.rerun()
            with c2:
                if st.button("🔌 Testar Conexão", width="stretch"):
                    if not (token and cnpj and nome_empresa):
                        st.warning("Preencha todos os campos antes de testar.")
                    else:
                        with st.spinner("Conectando..."):
                            try:
                                ok = MicrovixAPI(token, cnpj, nome_empresa, base_url).test_connection()
                            except MicrovixAPIError as _e:
                                ok = False
                                _err_msg = str(_e)
                            else:
                                _err_msg = ""
                        if ok:
                            st.success("✅ Conexão bem-sucedida!")
                        elif _err_msg:
                            st.error(f"❌ {_err_msg}")
                        else:
                            st.error("❌ Falha. Verifique credenciais e URL.")
        with col_help:
            st.markdown("#### Como obter as credenciais")
            st.info("1. Acesse o Microvix\n2. Configurações → Integrações\n3. Copie o **Token**\n4. Nome da empresa = exato como no Microvix\n5. CNPJ da empresa")
            st.markdown("#### Detectar DDD da loja")
            st.caption("Busca o DDD padrão direto dos parâmetros do Microvix (LinxLojasParametros).")
            if st.button("📡 Detectar DDD automático", width="stretch", key="btn_detect_ddd"):
                if not (cfg.get("token") and cfg.get("cnpj")):
                    st.warning("Configure e salve as credenciais antes de detectar o DDD.")
                else:
                    with st.spinner("Consultando parâmetros da loja..."):
                        try:
                            _api_ddd = get_api()
                            if _api_ddd:
                                _params = _api_ddd.get_store_params()
                                _ddd_found = str(
                                    _params.get("ddd", "") or
                                    _params.get("ddd_loja", "") or
                                    _params.get("ddd_telefone", "") or ""
                                ).strip()
                                if _ddd_found and _ddd_found.isdigit():
                                    cfg.set("ddd_padrao", _ddd_found)
                                    cfg.save()
                                    st.success(f"✅ DDD detectado: **{_ddd_found}**")
                                else:
                                    st.warning(
                                        "DDD não encontrado nos parâmetros. "
                                        "Configure manualmente em Configurações → Campanhas Ativas."
                                    )
                            else:
                                st.warning("Configure as credenciais reais (modo demo não suporta detecção de DDD).")
                        except MicrovixAPIError as _e:
                            st.error(str(_e))

        # ── Canal E-mail (Brevo) ──────────────────────────────────────────────
        st.divider()
        st.markdown("#### 📧 Canal E-mail — Brevo")
        st.caption(
            "Configure sua API key do Brevo para disparar e-mails de reativação "
            "para clientes dos segmentos **Em Risco** e **Hibernando** no RFM. "
            "Gratuito até 300 e-mails/dia. Obtenha a API key em brevo.com → Configurações → API."
        )
        from modules.email_sender import (
            load_email_config as _load_ecfg, save_email_config as _save_ecfg,
            test_connection as _test_brevo,
        )
        _ecfg = _load_ecfg()
        _ec1, _ec2 = st.columns(2)
        with _ec1:
            _brevo_key = st.text_input(
                "API Key Brevo", type="password",
                value=_ecfg.get("brevo_api_key", ""),
                placeholder="xkeysib-...",
                key="brevo_api_key",
            )
            _brevo_sender = st.text_input(
                "E-mail remetente",
                value=_ecfg.get("sender_email", ""),
                placeholder="seuemail@dominio.com",
                key="brevo_sender",
            )
            _brevo_name = st.text_input(
                "Nome remetente",
                value=_ecfg.get("sender_name", "Ótica P. Ferreira"),
                key="brevo_name",
            )
        with _ec2:
            _assunto_padrao = st.text_input(
                "Assunto padrão dos e-mails",
                value=_ecfg.get("subject_default", "Uma mensagem especial para você 👓"),
                key="brevo_subject",
            )
            st.caption(
                "O corpo do e-mail usa o **mesmo template da campanha selecionada**, "
                "adaptado para e-mail (links WhatsApp removidos automaticamente)."
            )
            _be1, _be2 = st.columns(2)
            with _be1:
                if st.button("💾 Salvar", key="save_brevo"):
                    _save_ecfg({
                        "brevo_api_key":  _brevo_key.strip(),
                        "sender_email":   _brevo_sender.strip(),
                        "sender_name":    _brevo_name.strip(),
                        "subject_default": _assunto_padrao.strip(),
                    })
                    st.success("Configuração de e-mail salva!")
                    st.rerun()
            with _be2:
                if st.button("🔌 Testar Brevo", key="test_brevo"):
                    if not _brevo_key or not _brevo_sender:
                        st.warning("Preencha API key e e-mail remetente antes de testar.")
                    else:
                        ok, msg = _test_brevo(_brevo_key.strip(), _brevo_sender.strip())
                        if ok:
                            st.success(f"✅ {msg}")
                        else:
                            st.error(f"❌ {msg}")
        if _ecfg.get("brevo_api_key"):
            st.success(f"📧 E-mail configurado — remetente: **{_ecfg.get('sender_email','?')}**")

        # ── Seção SEFAZ ──────────────────────────────────────────────────────
        st.divider()
        st.markdown("#### 🏛️ Certificado Digital A1 — SEFAZ")
        st.caption(
            "Configure o Certificado Digital A1 (.pfx) para consultar NF-e e CT-e "
            "diretamente da SEFAZ Nacional (NFeDistribuicaoDFe)."
        )

        # Inicializa chaves de session_state para resultados persistentes
        if "sefaz_test_msg" not in st.session_state:
            st.session_state["sefaz_test_msg"] = None   # ("ok"|"warn"|"err", texto)
        if "sefaz_conn_msg" not in st.session_state:
            st.session_state["sefaz_conn_msg"] = None

        _sefaz_col1, _sefaz_col2 = st.columns([2, 1], gap="large")

        with _sefaz_col1:
            # ── Status do certificado salvo ───────────────────────────────────
            _cert_b64_saved = cfg.get("sefaz_cert_b64", "")
            _cert_name_saved = cfg.get("sefaz_cert_name", "")

            if _cert_b64_saved:
                _cert_kb = len(_cert_b64_saved) * 3 // 4 // 1024
                st.success(
                    f"✅ **Certificado carregado:** {_cert_name_saved or 'certificado.pfx'}  "
                    f"({_cert_kb} KB) — salvo permanentemente."
                )
                with st.expander("🔄 Substituir certificado"):
                    _pfx_file = st.file_uploader(
                        "Novo certificado (.pfx / .p12)",
                        type=["pfx", "p12"],
                        key="sefaz_pfx_upload",
                    )
                    if _pfx_file is not None:
                        _pfx_b64_new = base64.b64encode(_pfx_file.read()).decode("utf-8")
                        cfg.set("sefaz_cert_b64", _pfx_b64_new)
                        cfg.set("sefaz_cert_name", _pfx_file.name)
                        cfg.save()
                        # Limpa cliente em cache para forçar rebuild
                        st.session_state.pop("sefaz_client", None)
                        st.session_state["sefaz_test_msg"] = None
                        st.session_state["sefaz_conn_msg"] = None
                        st.success(f"✅ Certificado **{_pfx_file.name}** substituído.")
                        st.rerun()
            else:
                _pfx_file = st.file_uploader(
                    "Certificado Digital A1 (.pfx / .p12)",
                    type=["pfx", "p12"],
                    key="sefaz_pfx_upload",
                    help="Arquivo .pfx ou .p12 do Certificado Digital A1 da empresa.",
                )
                if _pfx_file is not None:
                    _pfx_b64_new = base64.b64encode(_pfx_file.read()).decode("utf-8")
                    cfg.set("sefaz_cert_b64", _pfx_b64_new)
                    cfg.set("sefaz_cert_name", _pfx_file.name)
                    cfg.save()
                    st.session_state.pop("sefaz_client", None)
                    st.rerun()

            # ── Senha e configurações ─────────────────────────────────────────
            _sefaz_pw = st.text_input(
                "Senha do Certificado",
                value=cfg.get("sefaz_cert_password", ""),
                type="password",
                key="sefaz_pw_input",
            )

            _sefaz_amb_opts = {"Produção (1)": 1, "Homologação (2)": 2}
            _amb_saved = cfg.get("sefaz_ambiente", 1)
            _amb_label = "Produção (1)" if _amb_saved == 1 else "Homologação (2)"
            _sefaz_amb = st.selectbox(
                "Ambiente",
                options=list(_sefaz_amb_opts.keys()),
                index=list(_sefaz_amb_opts.keys()).index(_amb_label),
                key="sefaz_amb_sel",
            )

            _uf_options = {
                "11 - RO": "11", "12 - AC": "12", "13 - AM": "13", "14 - RR": "14",
                "15 - PA": "15", "16 - AP": "16", "17 - TO": "17", "21 - MA": "21",
                "22 - PI": "22", "23 - CE": "23", "24 - RN": "24", "25 - PB": "25",
                "26 - PE": "26", "27 - AL": "27", "28 - SE": "28", "29 - BA": "29",
                "31 - MG": "31", "32 - ES": "32", "33 - RJ": "33", "35 - SP": "35",
                "41 - PR": "41", "42 - SC": "42", "43 - RS": "43", "50 - MS": "50",
                "51 - MT": "51", "52 - GO": "52", "53 - DF": "53",
            }
            _uf_saved = cfg.get("sefaz_uf", "35")
            _uf_label_saved = next(
                (k for k, v in _uf_options.items() if v == str(_uf_saved)),
                "35 - SP",
            )
            _sefaz_uf_sel = st.selectbox(
                "UF do Emitente",
                options=list(_uf_options.keys()),
                index=list(_uf_options.keys()).index(_uf_label_saved),
                key="sefaz_uf_sel",
            )

            # ── Botões ────────────────────────────────────────────────────────
            _sc1, _sc2, _sc3 = st.columns(3)

            with _sc1:
                if st.button("💾 Salvar SEFAZ", type="primary", key="btn_sefaz_save"):
                    cfg.set("sefaz_cert_password", _sefaz_pw.strip())
                    cfg.set("sefaz_ambiente", _sefaz_amb_opts[_sefaz_amb])
                    cfg.set("sefaz_uf", _uf_options[_sefaz_uf_sel])
                    cfg.save()
                    # Invalida cliente em cache (senha pode ter mudado)
                    st.session_state.pop("sefaz_client", None)
                    st.session_state["sefaz_test_msg"] = ("ok", "✅ Configurações SEFAZ salvas!")
                    st.rerun()

            with _sc2:
                if st.button("🔌 Testar Certificado", key="btn_sefaz_test"):
                    _b64 = cfg.get("sefaz_cert_b64", "")
                    _pw  = _sefaz_pw.strip() or cfg.get("sefaz_cert_password", "")
                    if not _b64:
                        st.session_state["sefaz_test_msg"] = ("warn", "⚠️ Faça upload do certificado .pfx primeiro.")
                    else:
                        with st.spinner("Validando certificado..."):
                            try:
                                _pfx_bytes = base64.b64decode(_b64)
                                _cli_test  = SefazClient(
                                    _pfx_bytes, _pw,
                                    cnpj=cfg.get("cnpj", ""),
                                    uf=_uf_options[_sefaz_uf_sel],
                                    ambiente=_sefaz_amb_opts[_sefaz_amb],
                                )
                                _info = _cli_test.cert_info()
                                if "error" in _info:
                                    st.session_state["sefaz_test_msg"] = ("err", f"❌ {_info['error']}")
                                else:
                                    # Guarda cliente em cache para reutilizar
                                    st.session_state["sefaz_client"] = _cli_test
                                    _subj = _info.get("subject", "")
                                    # Extrai apenas o CN do subject (fica mais legível)
                                    import re as _re
                                    _cn = _re.search(r"CN=([^,]+)", _subj)
                                    _titular = _cn.group(1) if _cn else _subj
                                    st.session_state["sefaz_test_msg"] = (
                                        "ok",
                                        f"✅ **Certificado válido!**\n\n"
                                        f"👤 **Titular:** {_titular}\n\n"
                                        f"📅 **Válido até:** {_info.get('not_after', '')}",
                                    )
                            except SefazError as _se:
                                st.session_state["sefaz_test_msg"] = ("err", f"❌ {_se}")
                            except BaseException as _ge:
                                st.session_state["sefaz_test_msg"] = ("err", f"❌ Erro inesperado: {type(_ge).__name__}: {_ge}")
                    st.rerun()

            with _sc3:
                if st.button("📡 Testar SEFAZ", key="btn_sefaz_conn"):
                    _b64 = cfg.get("sefaz_cert_b64", "")
                    _pw  = _sefaz_pw.strip() or cfg.get("sefaz_cert_password", "")
                    _uf  = _uf_options[_sefaz_uf_sel]
                    _amb = _sefaz_amb_opts[_sefaz_amb]
                    if not _b64:
                        st.session_state["sefaz_conn_msg"] = ("warn", "⚠️ Faça upload e salve o certificado .pfx primeiro.")
                    else:
                        with st.spinner("Conectando ao SEFAZ Nacional... (pode levar até 30s)"):
                            try:
                                # Reusa cliente em cache se disponível, senão cria
                                _cli_conn = st.session_state.get("sefaz_client")
                                if _cli_conn is None:
                                    _pfx_bytes = base64.b64decode(_b64)
                                    _cli_conn  = SefazClient(
                                        _pfx_bytes, _pw,
                                        cnpj=cfg.get("cnpj", ""),
                                        uf=_uf, ambiente=_amb,
                                    )
                                    st.session_state["sefaz_client"] = _cli_conn
                                _nsu_test  = cfg.get("sefaz_ultimo_nsu", "0")
                                _resp_test = _cli_conn.dist_dfe(_nsu_test)
                                _cs = _resp_test.get("cStat", "")
                                _xm = _resp_test.get("xMotivo", "")
                                _nd = len(_resp_test.get("docs", []))
                                _max_nsu = _resp_test.get("maxNSU", "?")
                                if _cs == "137":
                                    st.session_state["sefaz_conn_msg"] = (
                                        "ok",
                                        f"✅ **SEFAZ conectado!** — {_xm}\n\n"
                                        f"📄 Documentos disponíveis: **{_nd}** | "
                                        f"MaxNSU: **{_max_nsu}**",
                                    )
                                elif _cs == "138":
                                    st.session_state["sefaz_conn_msg"] = (
                                        "ok",
                                        f"✅ **SEFAZ conectado!** — {_xm}\n\n"
                                        f"Nenhum documento novo a partir do NSU {_nsu_test}. "
                                        f"MaxNSU: **{_max_nsu}**",
                                    )
                                else:
                                    # Retorno com cStat de rejeição — exibe detalhes para diagnóstico
                                    _cstat_map = {
                                        "215": "Falha no esquema XML",
                                        "238": "CNPJ não autorizado",
                                        "248": "CNPJ do interessado ≠ CNPJ do certificado",
                                        "656": "NSU não encontrado para este CNPJ",
                                        "998": "Serviço em manutenção",
                                        "999": "Erro não catalogado",
                                    }
                                    _dica = _cstat_map.get(_cs, "")
                                    _msg_cs = f"cStat={_cs}: {_xm}" + (f" ({_dica})" if _dica else "")
                                    st.session_state["sefaz_conn_msg"] = (
                                        "warn", f"⚠️ SEFAZ respondeu mas com rejeição — {_msg_cs}"
                                    )
                            except SefazError as _se:
                                st.session_state["sefaz_conn_msg"] = ("err", f"❌ {_se}")
                            except BaseException as _ge:
                                st.session_state["sefaz_conn_msg"] = ("err", f"❌ Erro inesperado: {type(_ge).__name__}: {_ge}")
                    st.rerun()

            # ── Exibe resultados persistentes ─────────────────────────────────
            for _msg_key in ("sefaz_test_msg", "sefaz_conn_msg"):
                _msg = st.session_state.get(_msg_key)
                if _msg:
                    _kind, _text = _msg
                    if _kind == "ok":
                        st.success(_text)
                    elif _kind == "warn":
                        st.warning(_text)
                    else:
                        st.error(_text)

        with _sefaz_col2:
            st.markdown("#### Sobre o Certificado Digital A1")
            st.info(
                "**Certificado A1** (.pfx / .p12):\n\n"
                "• Arquivo digital com chave privada\n"
                "• Emitido por AC credenciada ICP-Brasil\n"
                "• Validade geralmente de 1 ano\n\n"
                "**Onde obter:**\n"
                "Certisign, Serasa Experian, Soluti, Valid, etc.\n\n"
                "**Ambiente:**\n"
                "Use **Produção** para dados reais. "
                "**Homologação** para testes (NFs fictícias)."
            )
            _nsu_atual = cfg.get("sefaz_ultimo_nsu", "0")
            st.metric("📬 Último NSU consultado", str(_nsu_atual).lstrip("0") or "0")
            if cfg.get("sefaz_cert_b64", ""):
                if st.button("🗑️ Remover certificado", key="btn_sefaz_del_cert"):
                    cfg.set("sefaz_cert_b64", "")
                    cfg.set("sefaz_cert_name", "")
                    cfg.save()
                    st.session_state.pop("sefaz_client", None)
                    st.session_state["sefaz_test_msg"] = None
                    st.session_state["sefaz_conn_msg"] = None
                    st.rerun()
            if st.button("🔄 Resetar NSU para 0", key="btn_sefaz_reset_nsu"):
                cfg.set("sefaz_ultimo_nsu", "0")
                cfg.save()
                st.success("NSU resetado. Próxima busca trará todos os documentos.")
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # ABA CATÁLOGO — SEÇÃO BLOQUEADA — BASE FUNDAMENTAL DO PROGRAMA
    # Autorizado por: Gestor TI Chilli Beans
    # Alterações nesta seção requerem autorização expressa do gestor antes de
    # qualquer modificação. A política aditiva é aplicada em dois níveis:
    #   1. UI: checkbox exige confirmação manual para substituição total.
    #   2. Módulo: import_from_df() rejeita merge=False sem force_overwrite=True.
    # ══════════════════════════════════════════════════════════════════════════
    with tab_cat:
        from modules.product_map import load_meta as _load_cat_meta

        st.markdown("#### 📦 Catálogo de Produtos")
        st.caption("O catálogo mapeia cod_produto → referência/categoria. Necessário para filtrar LV/OC/ML/AC.")

        # ── Status e metadados ────────────────────────────────────────────
        _pmap = st.session_state.product_map
        _cat_meta = _load_cat_meta()

        # ── Faixinha de Saúde do Catálogo (somente leitura) ──────────────
        # Autorizado por Rafael Burim Ramo em 01/06/2026
        if _pmap:
            _sem_cat    = sum(1 for v in _pmap.values() if not v.get("categoria") or v.get("categoria") == "?")
            _sem_preco  = sum(1 for v in _pmap.values() if not v.get("preco_original"))
            _pct_sem_preco = round(_sem_preco / len(_pmap) * 100, 1)
            _hc1, _hc2, _hc3 = st.columns(3)
            _hc1.metric("📦 Produtos", f"{len(_pmap):,}".replace(",", "."))
            _hc2.metric(
                "⚠️ Sem categoria", _sem_cat,
                delta=f"{_sem_cat / len(_pmap) * 100:.1f}%" if _sem_cat else "0%",
                delta_color="inverse" if _sem_cat > 0 else "off",
            )
            _hc3.metric(
                "💲 Sem preço", f"{_pct_sem_preco}%",
                help="Produtos sem preco_original no catálogo. O preço virá do preco_tabela_epoca nas vendas.",
            )
            if _sem_cat > 0:
                with st.expander(f"🔍 {_sem_cat} produto(s) sem categoria — clique para ver"):
                    _sc_df = pd.DataFrame([
                        {
                            "Cod. Produto": cod,
                            "Referência":   v.get("referencia", ""),
                            "Categoria":    v.get("categoria", "?") or "?",
                        }
                        for cod, v in _pmap.items()
                        if not v.get("categoria") or v.get("categoria") == "?"
                    ])
                    st.dataframe(_sc_df, hide_index=True, width="stretch")
            st.divider()

        if _pmap:
            # Conta todas as categorias, inclusive desconhecidas
            cats = {}
            for v in _pmap.values():
                cat_key = v.get("categoria") or "?"
                cats[cat_key] = cats.get(cat_key, 0) + 1

            # ── Total em destaque ─────────────────────────────────────────
            st.metric("📦 Total de produtos mapeados", f"{len(_pmap):,}".replace(",", "."))

            # ── Categorias em grade de 3 por linha ────────────────────────
            _sorted_cats = sorted(cats.items())
            _chunk_size = 3
            for _row_start in range(0, len(_sorted_cats), _chunk_size):
                _chunk = _sorted_cats[_row_start: _row_start + _chunk_size]
                _row_cols = st.columns(_chunk_size)
                for _col, (cat, cnt) in zip(_row_cols, _chunk):
                    _label = CAT_NAMES.get(cat, f"Outros / Não classificados ({cat})")
                    _col.metric(_label, f"{cnt:,}".replace(",", "."))

            # Verificação: alerta se a soma das categorias divergir do total
            _soma = sum(cats.values())
            if _soma != len(_pmap):
                st.warning(
                    f"⚠️ Atenção: soma das categorias ({_soma:,}) difere do total "
                    f"({len(_pmap):,}). Pode haver entradas sem categoria definida."
                )

            # ── Referências não classificadas ─────────────────────────────
            _sem_cat = {
                cod: v for cod, v in _pmap.items()
                if not v.get("categoria") or v.get("categoria") == "?"
            }
            if _sem_cat:
                with st.expander(f"🔍 Referências não classificadas ({len(_sem_cat):,} produtos) — clique para ver os prefixos"):
                    st.caption(
                        "Estes produtos não se encaixam em nenhum grupo existente. "
                        "Analise os prefixos abaixo para criar novos grupos de categoria."
                    )
                    # Agrupa por prefixo (primeiros 5 caracteres da referência)
                    _prefix_groups: dict = {}
                    for v in _sem_cat.values():
                        ref = str(v.get("referencia", "")).strip().upper()
                        if not ref or ref in ("NAN", "NONE", ""):
                            prefix = "(sem referência)"
                        else:
                            # Mostra até o 2º ponto para capturar padrões como "XX.YY"
                            parts = ref.split(".")
                            prefix = ".".join(parts[:2]) if len(parts) >= 2 else ref[:5]
                        if prefix not in _prefix_groups:
                            _prefix_groups[prefix] = {"quantidade": 0, "exemplo": ref}
                        _prefix_groups[prefix]["quantidade"] += 1

                    _prefix_df = pd.DataFrame([
                        {
                            "Prefixo": pfx,
                            "Exemplo de referência": data["exemplo"],
                            "Quantidade de produtos": data["quantidade"],
                        }
                        for pfx, data in sorted(
                            _prefix_groups.items(),
                            key=lambda x: -x[1]["quantidade"]
                        )
                    ])
                    st.dataframe(_prefix_df, hide_index=True, width="stretch")

            if _cat_meta.get("last_import"):
                st.success(f"✅ Catálogo ativo — última importação: **{_cat_meta['last_import']}**")
            else:
                st.success("✅ Catálogo carregado.")

            # ── Histórico de importações ──────────────────────────────────
            _hist = _cat_meta.get("historico", [])
            if _hist:
                with st.expander("📋 Histórico de importações"):
                    _hist_df = pd.DataFrame(_hist)[["data", "source", "adicionados", "ignorados", "total_catalogo"]]
                    _hist_df.columns = ["Data", "Origem", "Adicionados", "Ignorados", "Total no catálogo"]
                    st.dataframe(_hist_df, hide_index=True, width="stretch")

            # ── Proteção ──────────────────────────────────────────────────
            st.info(
                "🔒 **Catálogo protegido.** Novas importações são ADITIVAS: produtos novos são adicionados, "
                "existentes são preservados. Para substituir o catálogo inteiro, marque a opção abaixo."
            )
            _allow_overwrite = st.checkbox(
                "⚠️ Autorizo substituição completa do catálogo (use apenas se necessário)",
                value=False,
                key="cat_allow_overwrite",
            )
        else:
            st.warning("⚠️ Catálogo não importado. Dados ao vivo não serão filtrados por LV/OC/ML/AC.")
            _allow_overwrite = False

        st.divider()

        # ── Tabela de produtos catalogados ────────────────────────────────
        if _pmap:
            st.markdown("##### 📋 Produtos catalogados")
            _tbl_rows = [
                {
                    "Cod. Produto": cod,
                    "Referência": v.get("referencia", ""),
                    "Categoria": CAT_NAMES.get(v.get("categoria", ""), v.get("categoria", "")),
                    "Descrição": v.get("descricao", ""),
                    "Preço Original (R$)": v.get("preco_original", ""),
                }
                for cod, v in sorted(_pmap.items())
            ]
            _tbl_df = pd.DataFrame(_tbl_rows)
            st.dataframe(_tbl_df, hide_index=True, width="stretch")
            st.divider()

        # ── Importação via API ────────────────────────────────────────────
        st.markdown("##### 🔄 Importar via API")
        st.caption("Busca o catálogo direto do Microvix (LinxProdutos) sem precisar de arquivo CSV.")
        if st.button("📡 Importar catálogo via API", type="primary", key="btn_api_catalog"):
            if not cfg.is_configured or cfg.modo_demo:
                st.warning("Configure as credenciais reais antes de importar via API.")
            else:
                with st.spinner("Buscando catálogo do Microvix (LinxProdutos)..."):
                    try:
                        _api_cat = get_api()
                        _df_prod = _api_cat.get_products()
                        if _df_prod.empty:
                            st.warning(
                                "Nenhum produto retornado pelo endpoint LinxProdutos. "
                                "Use a importação via CSV abaixo para carregar o catálogo."
                            )
                        else:
                            _new_map = import_product_api(_df_prod)
                            st.session_state.product_map = _new_map
                            _cats2 = {}
                            for _v in _new_map.values():
                                _cats2[_v["categoria"]] = _cats2.get(_v["categoria"], 0) + 1
                            _resumo = ", ".join(
                                f"{CAT_NAMES.get(c, c)}: {n}" for c, n in sorted(_cats2.items())
                            )
                            st.success(
                                f"✅ {len(_new_map)} produtos importados via API — {_resumo}"
                            )
                            st.rerun()
                    except MicrovixAPIError as _e:
                        st.error(str(_e))
                    except Exception as _e:
                        st.error(f"Erro inesperado: {_e}")

        st.divider()
        st.markdown("##### 📄 Importar via CSV ← **Recomendado para capturar LV/OC/ML/AC**")
        st.info(
            "**Por que o CSV é necessário para armações e acessórios?**\n\n"
            "Lentes (LE.*) usam a referência como código de barras no Microvix — por isso são capturadas automaticamente. "
            "Armações (LV, OC, ML) e Acessórios (AC) têm código EAN numérico impresso na etiqueta, "
            "então a referência 'LV.IJ.001' só existe no cadastro de produtos do Microvix (não nas movimentações).\n\n"
            "**Como exportar o CSV do Microvix (Linx):**\n"
            "1. Acesse o Microvix\n"
            "2. Menu **Relatórios → Produtos** (ou Cadastros → Produtos)\n"
            "3. Clique em **Exportar** → formato **CSV** ou **Excel**\n"
            "4. Certifique-se que o arquivo contém as colunas: `cod_produto` e `referencia`\n"
            "5. Faça upload abaixo"
        )
        if "cat_upload_key" not in st.session_state:
            st.session_state["cat_upload_key"] = 0
        uploaded = st.file_uploader(
            "Arquivo CSV do Microvix (Produtos)", type=["csv", "txt", "xlsx", "xls"],
            key=f"cat_uploader_{st.session_state['cat_upload_key']}",
        )
        _fname = uploaded.name if uploaded is not None else ""
        _is_excel = _fname.lower().endswith((".xlsx", ".xls"))
        if not _is_excel:
            sep = st.selectbox("Separador", [";  (ponto e vírgula)", ",  (vírgula)", "\\t  (tabulação)"])
            sep_char = {";": ";", ",": ",", "\\t": "\t"}[sep.split()[0]]
        _header_row = st.number_input(
            "Linha do cabeçalho (qual linha tem os nomes das colunas?)",
            min_value=1, max_value=10, value=2, step=1,
            help="Se a planilha tem uma linha de título acima dos cabeçalhos, use 2. Caso contrário, use 1.",
            key="cat_header_row",
        )
        if uploaded is not None:
            try:
                if _is_excel:
                    # Lê xlsx diretamente como ZIP — ignora estilos/formatação
                    import zipfile, xml.etree.ElementTree as _ET
                    from io import BytesIO as _BytesIO

                    def _col_letter_to_idx(letters: str) -> int:
                        import re as _re2
                        letters = _re2.sub(r"[^A-Za-z]", "", letters).upper()
                        idx = 0
                        for ch in letters:
                            idx = idx * 26 + (ord(ch) - ord("A") + 1)
                        return idx - 1

                    _raw = uploaded.read()
                    with zipfile.ZipFile(_BytesIO(_raw)) as _zf:
                        _wb_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                        # ── Shared strings ──────────────────────────────
                        _sst: list = []
                        _sst_candidates = [n for n in _zf.namelist()
                                           if "sharedStrings" in n or "sharedstrings" in n.lower()]
                        if _sst_candidates:
                            _sst_xml = _zf.read(_sst_candidates[0])
                            _sst_root = _ET.fromstring(_sst_xml)
                            # Aceita qualquer namespace na tag <si>
                            for _si in _sst_root.iter():
                                if _si.tag.endswith("}si") or _si.tag == "si":
                                    _t_parts = []
                                    for _t_el in _si.iter():
                                        if _t_el.tag.endswith("}t") or _t_el.tag == "t":
                                            _t_parts.append(_t_el.text or "")
                                    _sst.append("".join(_t_parts))
                        # ── Primeira planilha ────────────────────────────
                        _sheet_candidates = sorted(
                            [n for n in _zf.namelist()
                             if "worksheets/sheet" in n and n.endswith(".xml")],
                        )
                        if not _sheet_candidates:
                            raise ValueError("Planilha não encontrada no arquivo xlsx.")
                        _ws_xml = _zf.read(_sheet_candidates[0])
                        _ws_root = _ET.fromstring(_ws_xml)
                        # ── Lê linhas ────────────────────────────────────
                        _data_rows: list = []
                        for _row_el in _ws_root.iter():
                            if not (_row_el.tag.endswith("}row") or _row_el.tag == "row"):
                                continue
                            _row_dict: dict = {}
                            for _c in _row_el:
                                if not (_c.tag.endswith("}c") or _c.tag == "c"):
                                    continue
                                _ref = _c.get("r", "")
                                _col_idx = _col_letter_to_idx(_ref) if _ref else len(_row_dict)
                                _t_attr = _c.get("t", "n")
                                _val = ""
                                # Valor principal
                                _v_el = next(
                                    (ch for ch in _c if ch.tag.endswith("}v") or ch.tag == "v"),
                                    None,
                                )
                                # Inline string
                                _is_el = next(
                                    (ch for ch in _c if ch.tag.endswith("}is") or ch.tag == "is"),
                                    None,
                                )
                                if _is_el is not None:
                                    _val = "".join(
                                        (ch.text or "") for ch in _is_el.iter()
                                        if ch.tag.endswith("}t") or ch.tag == "t"
                                    )
                                elif _v_el is not None and _v_el.text:
                                    if _t_attr == "s":
                                        try:
                                            _val = _sst[int(_v_el.text)]
                                        except (IndexError, ValueError):
                                            _val = _v_el.text
                                    else:
                                        _val = _v_el.text
                                _row_dict[_col_idx] = _val
                            if _row_dict:
                                _max_c = max(_row_dict.keys()) + 1
                                _data_rows.append([_row_dict.get(i, "") for i in range(_max_c)])

                    if not _data_rows:
                        st.error("Planilha vazia ou sem dados reconhecíveis.")
                        st.stop()
                    _max_cols = max(len(r) for r in _data_rows)
                    _data_rows = [r + [""] * (_max_cols - len(r)) for r in _data_rows]
                    # Usa a linha selecionada como cabeçalho (1-indexed)
                    _hdr_idx = int(_header_row) - 1
                    _raw_headers = _data_rows[_hdr_idx]
                    _headers = [
                        str(h).strip() if str(h).strip() else f"col_{i}"
                        for i, h in enumerate(_raw_headers)
                    ]
                    df_csv = pd.DataFrame(_data_rows[_hdr_idx + 1:], columns=_headers)
                else:
                    df_csv = pd.read_csv(
                        uploaded, sep=sep_char, encoding="latin-1",
                        dtype=str, header=int(_header_row) - 1,
                    )
                st.markdown(f"**{len(df_csv)} linhas.** Pré-visualização:")
                st.dataframe(df_csv.head(5), width="stretch", hide_index=True)
                if st.button("✅ Confirmar importação", type="primary"):
                    with st.spinner("Processando..."):
                        _merge_mode = not _allow_overwrite
                        new_map = import_from_df(
                            df_csv,
                            merge=_merge_mode,
                            source="CSV manual",
                            force_overwrite=_allow_overwrite,  # exige confirmação explícita do gestor
                        )
                    st.session_state.product_map = new_map
                    cats2 = {}
                    for v in new_map.values(): cats2[v["categoria"]] = cats2.get(v["categoria"], 0) + 1
                    resumo = ", ".join(f"{CAT_NAMES.get(c,c)}: {n}" for c, n in sorted(cats2.items()))
                    _modo_txt = "substituído" if not _merge_mode else "atualizado (aditivo)"
                    st.success(f"✅ Catálogo {_modo_txt} — {len(new_map)} produtos — {resumo}")
                    st.session_state["cat_upload_key"] += 1  # limpa o file_uploader
                    st.rerun()
            except Exception as e:
                st.error(f"Erro ao ler o arquivo: {e}")

    # ── Faixas de Preço ───────────────────────────────────────────────────────
    with tab_tiers:
        st.markdown("#### Faixas de Preço")
        st.caption("Máximo da última faixa (Luxo) pode ficar em 99999.")
        tiers  = cfg.get("faixas_preco", [])
        edited = st.data_editor(
            pd.DataFrame(tiers),
            width="stretch", hide_index=True, num_rows="fixed",
            column_config={
                "label": st.column_config.TextColumn("Nome da Faixa", required=True),
                "min":   st.column_config.NumberColumn("Preço Mínimo (R$)", min_value=0, format="%.2f"),
                "max":   st.column_config.NumberColumn("Preço Máximo (R$)", format="%.2f"),
            },
        )
        if st.button("💾 Salvar Faixas", type="primary"):
            cfg.set("faixas_preco", edited.to_dict("records"))
            cfg.save()
            st.success("Faixas atualizadas!")
            st.rerun()

    # ── Estoque Ideal ─────────────────────────────────────────────────────────
    with tab_stock:
        st.markdown("### 📦 Estoque Atual")
        st.caption("Informe o estoque atual por categoria. O sistema ajustará automaticamente com base nas compras e vendas do Microvix a partir da data informada.")

        # ── Upload do Saldo em Estoque ────────────────────────────────────────
        st.markdown("**📂 Upload do Saldo em Estoque**")
        st.caption(
            "Faça upload do relatório **Saldo em Estoque** exportado do Microvix (`.xls`) "
            "ou de um CSV/Excel com colunas `referencia` e `quantidade`."
        )
        _inv_file = st.file_uploader(
            "Saldo em Estoque (XLS do Microvix ou CSV/Excel)",
            type=["csv", "xlsx", "xls"],
            key="inv_upload",
        )
        if _inv_file is not None:
            try:
                from modules.product_map import ref_to_category as _ref_to_cat
                _est_from_inv: dict = {"LV": 0, "OC": 0, "ML": 0}
                _rows_ok = 0
                _detail_rows: list = []  # referencia, categoria, quantidade

                # ── Tenta parsear formato Microvix XLS (HTML disfarçado) ──────
                _parsed_microvix = False
                _raw_bytes = _inv_file.read()
                _inv_file.seek(0)

                if _raw_bytes[:6] in (b'<html ', b'<HTML ', b'<?xml', b'<html\n') or b'<html' in _raw_bytes[:200].lower():
                    try:
                        import io as _io
                        _html_dfs = pd.read_html(_io.BytesIO(_raw_bytes), encoding="utf-8")
                        # Encontra a maior tabela (tabela de dados do Saldo em Estoque)
                        _main_tbl = max(_html_dfs, key=lambda t: len(t))
                        if len(_main_tbl) > 10:
                            # Linhas de dados: coluna 0 é código numérico (int)
                            def _is_cod(v):
                                try: int(float(str(v))); return True
                                except: return False
                            _data_rows = _main_tbl[_main_tbl[0].apply(_is_cod)].copy()
                            _data_rows[3] = pd.to_numeric(_data_rows[3], errors="coerce").fillna(0)
                            for _, _dr in _data_rows.iterrows():
                                _ref_v = str(_dr[2]).strip()
                                _qty_v = int(_dr[3])
                                if not _ref_v or _qty_v <= 0:
                                    continue
                                _cat_v = _ref_to_cat(_ref_v)
                                if _cat_v in _est_from_inv:
                                    _est_from_inv[_cat_v] += _qty_v
                                    _detail_rows.append({"referencia": _ref_v, "categoria": _cat_v, "quantidade": _qty_v})
                                    _rows_ok += 1
                            _parsed_microvix = _rows_ok > 0
                    except Exception:
                        pass  # Fallback abaixo

                # ── Fallback: CSV / Excel estruturado ─────────────────────────
                if not _parsed_microvix:
                    _inv_file.seek(0)
                    if _inv_file.name.lower().endswith(".csv"):
                        _df_inv = pd.read_csv(_inv_file, sep=None, engine="python", encoding="utf-8-sig")
                    else:
                        _df_inv = pd.read_excel(_inv_file)
                    _df_inv.columns = [c.strip().lower() for c in _df_inv.columns]
                    _pmap_inv = st.session_state.product_map or {}
                    _col_ref = next((c for c in _df_inv.columns if "refer" in c or "cod" in c or "ref" in c), None)
                    _col_qty = next((c for c in _df_inv.columns if "qtd" in c or "quant" in c or "saldo" in c or "fisico" in c or "físico" in c or "estoque" in c), None)
                    _col_cat = next((c for c in _df_inv.columns if "cat" in c), None)
                    if _col_qty:
                        for _, _inv_row in _df_inv.iterrows():
                            _qty = 0
                            try: _qty = int(float(str(_inv_row[_col_qty]).replace(",", ".")))
                            except: continue
                            if _qty <= 0: continue
                            if _col_cat:
                                _cat_v = str(_inv_row[_col_cat]).strip().upper()[:2]
                                if _cat_v in _est_from_inv:
                                    _est_from_inv[_cat_v] += _qty; _rows_ok += 1
                            elif _col_ref:
                                _ref_v = str(_inv_row[_col_ref]).strip()
                                _cat_v = _ref_to_cat(_ref_v)
                                if _cat_v in _est_from_inv:
                                    _est_from_inv[_cat_v] += _qty
                                    _detail_rows.append({"referencia": _ref_v, "categoria": _cat_v, "quantidade": _qty})
                                    _rows_ok += 1

                if _rows_ok > 0:
                    cfg.set("estoque_virtual", _est_from_inv)
                    cfg.set("estoque_base_data", date.today().strftime("%d/%m/%Y"))
                    # Salva detalhe por referência para futuro rastreio
                    if _detail_rows:
                        cfg.set("estoque_detalhe", _detail_rows)
                    cfg.save()
                    _fonte = "Saldo em Estoque Microvix" if _parsed_microvix else "planilha"
                    st.success(
                        f"✅ {_fonte} importado com {_rows_ok} SKUs. "
                        f"LV={_est_from_inv['LV']} | OC={_est_from_inv['OC']} | ML={_est_from_inv['ML']} peças. "
                        f"Data base: {date.today().strftime('%d/%m/%Y')}"
                    )
                else:
                    st.warning(
                        "⚠️ Nenhum item reconhecido. Para o **Saldo em Estoque do Microvix**, "
                        "exporte como `.xls` pelo relatório de Estoque. Para planilha própria, "
                        "use colunas `referencia` + `quantidade`."
                    )
            except Exception as _e:
                st.error(f"Erro ao ler arquivo: {_e}")

        # ── Entrada manual por categoria ──────────────────────────────────────
        st.markdown("**✏️ Ajuste Manual por Categoria**")
        _est_base_date_show = cfg.get("estoque_base_data", "")
        if _est_base_date_show:
            # Mostra saldo estimado em tempo real usando LinxMovimento
            _api_cfg = get_api()
            if _api_cfg and not cfg.modo_demo:
                try:
                    from datetime import datetime as _dtc
                    _base_iso_cfg = str(_dtc.strptime(_est_base_date_show, "%d/%m/%Y").date())
                    _ent_cfg = _api_cfg.get_stock_from_movements(
                        _base_iso_cfg, st.session_state.product_map
                    )
                    _virt_cfg = cfg.get("estoque_virtual", {"LV": 0, "OC": 0, "ML": 0})
                    _df_vnd_cfg = st.session_state.df_vendas
                    _saldo_rt = {}
                    for _c in ("LV", "OC", "ML"):
                        _sai = 0
                        if _df_vnd_cfg is not None and "data" in _df_vnd_cfg.columns:
                            _mask = (
                                (_df_vnd_cfg["categoria"] == _c) &
                                (pd.to_datetime(_df_vnd_cfg["data"], errors="coerce").dt.date
                                 >= _dtc.strptime(_est_base_date_show, "%d/%m/%Y").date())
                            )
                            _sai = int(_df_vnd_cfg.loc[_mask, "quantidade"].sum())
                        _saldo_rt[_c] = max(0, int(_virt_cfg.get(_c, 0)) + _ent_cfg.get(_c, 0) - _sai)

                    _ideal_cfg = cfg.get("estoque_ideal", {"LV": 20, "OC": 15, "ML": 10})
                    _rt_parts = []
                    for _c, _lbl in [("LV","LV"),("OC","OC"),("ML","ML")]:
                        _s = _saldo_rt[_c]; _i = _ideal_cfg.get(_c, 0)
                        _icon = "✅" if _s >= _i else "🔴"
                        _rt_parts.append(f"{_icon} {_lbl}: **{_s} pç** (ideal {_i})")
                    st.success(
                        f"📡 **Saldo em tempo real** — base: {_est_base_date_show} "
                        f"(+{sum(_ent_cfg.values())} entradas via LinxMovimento)  \n"
                        + "  ·  ".join(_rt_parts)
                    )
                except Exception:
                    st.info(f"📅 Data base: **{_est_base_date_show}** — o sistema ajusta automaticamente via LinxMovimento.")
            else:
                st.info(f"📅 Data base do estoque: **{_est_base_date_show}** — o sistema calculará ajustes com base nas compras/vendas do Microvix desde esta data.")
        else:
            st.warning(
                "⚠️ **Nenhuma data base configurada.** "
                "Informe o estoque atual abaixo e clique **💾 Salvar** — "
                "a partir daí o sistema calculará o saldo em tempo real via LinxMovimento."
            )
        _est_virtual_cfg = cfg.get("estoque_virtual", {"LV": 0, "OC": 0, "ML": 0})
        _est_cols = st.columns(3)
        _new_est = {}
        for _i2, (_cat2, _label2) in enumerate([("LV","Armações de Grau"),("OC","Óculos Solar"),("ML","Armações Multi")]):
            with _est_cols[_i2]:
                _new_est[_cat2] = st.number_input(
                    _label2, min_value=0,
                    value=int(_est_virtual_cfg.get(_cat2, 0)),
                    key=f"cfg_est_{_cat2}",
                )
        if st.button("💾 Salvar Estoque Manual", key="save_est_manual"):
            cfg.set("estoque_virtual", {k: int(v) for k, v in _new_est.items()})
            cfg.set("estoque_base_data", date.today().strftime("%d/%m/%Y"))
            cfg.save()
            st.success("✅ Estoque salvo. A partir de hoje o sistema acompanha entradas e saídas em tempo real via LinxMovimento.")
            st.rerun()

        st.divider()
        st.markdown("### 🎯 Níveis de Estoque")
        st.caption(
            "🟡 **Estoque Mínimo** — defina manualmente. Abaixo deste valor → compra urgente na semana.  \n"
            "🟢 **Estoque Ideal** — calculado automaticamente: `Mínimo + (Venda/Sem × 2)` com base em 12 meses. Não editável."
        )
        _cat_labels = {
            "LV": "Armações de Grau (LV)",
            "OC": "Óculos Solar (OC)",
            "ML": "Armações Multi (ML)",
        }
        est_ideal = cfg.get("estoque_ideal", {"LV": 20, "OC": 15, "ML": 10})
        est_min   = cfg.get("estoque_minimo", {
            k: max(1, round(est_ideal.get(k, 10) * 0.5)) for k in ["LV", "OC", "ML"]
        })
        _vel_12m_cfg = cfg.get("velocidade_semanal_12m", {})

        # ── Tabela editável: somente Mínimo ──────────────────────────────────
        _min_rows = [
            {"Categoria": _cat_labels[k], "Código": k, "🟡 Mínimo (pç)": est_min.get(k, 1)}
            for k in ["LV", "OC", "ML"]
        ]
        edited_min = st.data_editor(
            pd.DataFrame(_min_rows),
            width="stretch", hide_index=True, num_rows="fixed",
            column_config={
                "Categoria":       st.column_config.TextColumn("Categoria", disabled=True),
                "Código":          st.column_config.TextColumn("Código", disabled=True, width="small"),
                "🟡 Mínimo (pç)": st.column_config.NumberColumn(
                    "🟡 Mínimo", min_value=0, format="%d",
                    help="Abaixo deste valor → compra urgente na semana corrente"
                ),
            },
        )

        # ── Botão: Calcular Ideal via 12 meses de histórico ──────────────────
        _calc_col, _save_col = st.columns([2, 1])
        with _calc_col:
            _btn_calcular = st.button(
                "🔄 Recalcular Ideal (12 meses)",
                help="Busca 12 meses de vendas no Microvix e calcula: Ideal = Mínimo + (Venda/Semana × 2)",
            )
        with _save_col:
            _btn_salvar_min = st.button("💾 Salvar Mínimo", type="primary")

        if _btn_calcular:
            _api_niv = get_api()
            if not _api_niv or cfg.modo_demo:
                st.warning("Disponível somente no modo ao vivo com credenciais configuradas.")
            else:
                with st.spinner("Buscando 12 meses de vendas para calcular o estoque ideal..."):
                    try:
                        from datetime import date as _dc
                        _dt_12m = str(_dc.today().replace(year=_dc.today().year - 1))
                        _dt_hj  = str(_dc.today())
                        _df_12m = _api_niv.get_sales(_dt_12m, _dt_hj, st.session_state.product_map)
                        if _df_12m.empty:
                            st.warning("Sem dados nos últimos 12 meses. Verifique as credenciais.")
                        else:
                            # Velocidade semanal por categoria (52 semanas exatas)
                            _vel = {}
                            for _c in ("LV", "OC", "ML"):
                                _qt = float(_df_12m[_df_12m["categoria"] == _c]["quantidade"].sum())
                                _vel[_c] = round(_qt / 52.0, 2)
                            cfg.set("velocidade_semanal_12m", _vel)
                            # Calcula ideal = mínimo + (vel × 2)
                            _new_min_now = {
                                row["Código"]: int(row["🟡 Mínimo (pç)"])
                                for _, row in edited_min.iterrows()
                            }
                            _new_ideal = {
                                k: _new_min_now.get(k, est_min.get(k, 0)) + math.ceil(_vel.get(k, 0) * 2)
                                for k in ("LV", "OC", "ML")
                            }
                            cfg.set("estoque_minimo", _new_min_now)
                            cfg.set("estoque_ideal",  _new_ideal)
                            cfg.save()
                            st.success(
                                "✅ Estoque ideal calculado e salvo:  \n"
                                + "  ·  ".join(
                                    f"**{k}**: mín {_new_min_now[k]} + {_vel[k]:.1f}/sem × 2 = **{_new_ideal[k]} pç**"
                                    for k in ("LV", "OC", "ML")
                                )
                            )
                            st.rerun()
                    except Exception as _e:
                        st.error(f"Erro ao calcular: {_e}")

        if _btn_salvar_min:
            _new_min_s = {row["Código"]: int(row["🟡 Mínimo (pç)"]) for _, row in edited_min.iterrows()}
            cfg.set("estoque_minimo", _new_min_s)
            # Recalcula ideal com a velocidade já armazenada
            if _vel_12m_cfg:
                _new_ideal_s = {
                    k: _new_min_s.get(k, 0) + math.ceil(_vel_12m_cfg.get(k, 0) * 2)
                    for k in ("LV", "OC", "ML")
                }
                cfg.set("estoque_ideal", _new_ideal_s)
            cfg.save()
            st.success("Mínimo salvo" + (" e Ideal recalculado." if _vel_12m_cfg else
                                          ". Clique em 'Recalcular Ideal' para atualizar o Ideal."))
            st.rerun()

        # ── Exibição do Ideal calculado (somente leitura) ────────────────────
        if est_ideal and _vel_12m_cfg:
            st.markdown("**🟢 Estoque Ideal atual (calculado — não editável):**")
            _ei_cols = st.columns(3)
            for _i3, _k in enumerate(["LV", "OC", "ML"]):
                _ei_cols[_i3].metric(
                    label=_cat_labels[_k],
                    value=f"{est_ideal.get(_k, 0)} pç",
                    delta=f"mín {est_min.get(_k,0)} + {_vel_12m_cfg.get(_k,0):.1f}/sem × 2",
                    delta_color="off",
                )
        elif est_ideal:
            st.info("Clique em **🔄 Recalcular Ideal** para derivar o estoque ideal a partir do mínimo e do histórico de 12 meses.")

        st.divider()
        st.markdown("#### 📦 Quantidade Mínima por Pedido")
        st.caption(
            "Quantidade mínima de peças por categoria em cada pedido de compra."
        )
        _qtd_min_default = {"LV": 1, "OC": 1, "ML": 1}
        _qtd_min_cfg = cfg.get("qtd_minima_compra", _qtd_min_default)
        _qm_rows = [
            {"Categoria": _cat_labels[k], "Código": k, "Qtd. Mínima": _qtd_min_cfg.get(k, 1)}
            for k in ["LV", "OC", "ML"]
        ]
        _qm_edited = st.data_editor(
            pd.DataFrame(_qm_rows),
            width="stretch", hide_index=True, num_rows="fixed",
            column_config={
                "Categoria":   st.column_config.TextColumn("Categoria", disabled=True),
                "Código":      st.column_config.TextColumn("Código", disabled=True, width="small"),
                "Qtd. Mínima": st.column_config.NumberColumn("Qtd. Mínima por pedido", min_value=1, format="%d"),
            },
        )
        if st.button("💾 Salvar Qtd. Mínima", key="save_qtd_min"):
            cfg.set("qtd_minima_compra", {r["Código"]: int(r["Qtd. Mínima"]) for _, r in _qm_edited.iterrows()})
            cfg.save()
            st.success("Quantidade mínima salva!")
            st.rerun()

    # ── Base de Clientes ─────────────────────────────────────────────────────
    with tab_cli:
        col_up, col_inf = st.columns([2, 1], gap="large")
        with col_up:
            st.markdown("#### Importar Base de Clientes do Microvix")
            st.caption(
                "Necessário para a aba **🔁 Clientes para Retorno**. "
                "Use o relatório *Clientes/Fornecedores* exportado do Microvix (CSV)."
            )
            _cmap = st.session_state.client_map or {}
            _cmeta = load_client_meta()
            if _cmap:
                _n_real = _cmeta.get("total", sum(1 for k in _cmap if k != "_meta"))
                st.success(f"✅ {_n_real:,} clientes mapeados.".replace(",", "."))

                # Exibe metadados de importação
                _imported_at = _cmeta.get("imported_at", "")
                _newest_date = _cmeta.get("newest_client_date", "")
                if _imported_at:
                    _meta_cols = st.columns(2)
                    _meta_cols[0].info(f"📅 Importado em: **{_imported_at}**")
                    if _newest_date:
                        _meta_cols[1].info(f"🆕 Último cadastro: **{_newest_date}**")

                    # Aviso de importação antiga (> 30 dias)
                    try:
                        _imp_dt = datetime.strptime(_imported_at, "%d/%m/%Y %H:%M")
                        _days_old = (datetime.now() - _imp_dt).days
                        if _days_old > 30:
                            st.warning(
                                f"⚠️ Base importada há **{_days_old} dias**. "
                                "Recomendamos importar o CSV atualizado do Microvix mensalmente "
                                "para manter os dados de contato em dia."
                            )
                    except Exception:
                        pass

                if st.button("🗑 Limpar base de clientes", key="clear_clients"):
                    st.session_state.client_map = {}
                    _fpath_c = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)), "data", "client_map.json"
                    )
                    if os.path.exists(_fpath_c):
                        os.remove(_fpath_c)
                    st.success("Base de clientes removida.")
                    st.rerun()
            else:
                st.warning("⚠️ Nenhuma base importada. A aba Clientes para Retorno ficará oculta.")
            st.divider()
            # ── Importação via API ────────────────────────────────────────────
            st.markdown("##### 🔄 Importar via API (recomendado)")
            st.caption("Busca todos os clientes direto do Microvix sem precisar de arquivo CSV.")
            if st.button("📡 Importar clientes via API", type="primary", key="btn_api_clients"):
                if not cfg.is_configured or cfg.modo_demo:
                    st.warning("Configure as credenciais reais antes de importar via API.")
                else:
                    with st.spinner("Buscando clientes do Microvix (LinxClientes)..."):
                        try:
                            _api_cli = get_api()
                            _new_cmap = _api_cli.get_clients_api()
                            if not _new_cmap:
                                st.warning("Nenhum cliente retornado. Verifique as credenciais.")
                            else:
                                import_client_api(_new_cmap)
                                st.session_state.client_map = _new_cmap
                                _new_meta = load_client_meta()
                                _n_imp = _new_meta.get("total", len(_new_cmap))
                                st.success(
                                    f"✅ {_n_imp:,} clientes importados via API!".replace(",", ".")
                                )
                                st.rerun()
                        except MicrovixAPIError as _e:
                            st.error(str(_e))
                        except Exception as _e:
                            st.error(f"Erro inesperado: {_e}")

            st.markdown("##### 📄 Ou importar via CSV (manual)")
            uploaded_cli = st.file_uploader(
                "Arquivo CSV — Relatório Clientes/Fornecedores (Microvix)",
                type=["csv"],
                key="upload_clients",
            )
            if uploaded_cli is not None:
                try:
                    preview_bytes = uploaded_cli.read()
                    uploaded_cli.seek(0)
                    import csv as _csv
                    import io as _io
                    preview_text = preview_bytes.decode("utf-8-sig", errors="replace")
                    preview_rows = list(_csv.DictReader(_io.StringIO(preview_text), delimiter=";"))
                    st.markdown(f"**{len(preview_rows)} registros encontrados.** Pré-visualização:")
                    _prev_df = pd.DataFrame(preview_rows[:5])
                    st.dataframe(_prev_df, width="stretch", hide_index=True)
                    if st.button("✅ Confirmar importação", type="primary", key="confirm_clients"):
                        with st.spinner("Importando clientes..."):
                            new_cmap = import_client_csv(preview_bytes)
                        st.session_state.client_map = new_cmap
                        _new_meta = load_client_meta()
                        _n_imp = _new_meta.get("total", len(new_cmap))
                        st.success(f"✅ {_n_imp:,} clientes importados!".replace(",", "."))
                        st.rerun()
                except Exception as e:
                    st.error(f"Erro ao ler o arquivo: {e}")
        with col_inf:
            st.markdown("#### Como exportar do Microvix")
            st.info(
                "1. No Microvix, acesse **Relatórios**\n"
                "2. Clientes / Fornecedores\n"
                "3. Exportar como **CSV**\n"
                "4. Colunas reconhecidas:\n"
                "   • `Cod` • `Nome/Razão Social`\n"
                "   • `Cel.` • `Tel.` • `Email`\n"
                "   • `Cidade` • `UF`\n"
                "   • `Cliente Desde` • `Data de Nascimento`\n\n"
                "💡 Importe mensalmente para manter os contatos atualizados."
            )

    # ── Meta de Mix ───────────────────────────────────────────────────────────
    with tab_meta:
        st.markdown("#### 🎯 Meta de Mix por Faixa de Preço")
        st.caption(
            "Define a distribuição percentual ideal por faixa de preço.  \n"
            "Essa meta é definida pela Chilli Beans e raramente muda — "
            "altere apenas quando receber orientação do seu consultor.  \n"
            "O comparativo aparece na aba **📊 Análise de Contexto**."
        )
        _tiers_meta = cfg.get("faixas_preco", [])
        if not _tiers_meta:
            st.warning("Nenhuma faixa de preço cadastrada. Configure em **💰 Faixas de Preço** primeiro.")
        else:
            _saved_meta = cfg.get("sug_faixas_saved") or {}
            _meta_inputs: dict = {}
            for _tier in _tiers_meta:
                _lbl = _tier["label"]
                _meta_inputs[_lbl] = st.number_input(
                    _price_label(_tier),
                    min_value=0.0, max_value=100.0,
                    value=float(_saved_meta.get(_lbl, 20.0)),
                    step=0.5,
                    format="%.1f",
                    key=f"meta_mix_{_lbl}",
                )
            _total_meta = sum(_meta_inputs.values())
            if abs(_total_meta - 100.0) < 0.1:
                st.success(f"✅ Total: {_total_meta:.1f}%")
            else:
                st.info(f"ℹ️ Total atual: {_total_meta:.1f}% — será normalizado para 100% ao salvar.")
            if st.button("💾 Salvar Meta de Mix", type="primary"):
                _s_meta = sum(_meta_inputs.values())
                if _s_meta > 0 and abs(_s_meta - 100.0) > 0.05:
                    _f_meta = 100.0 / _s_meta
                    _meta_inputs = {k: round(v * _f_meta, 1) for k, v in _meta_inputs.items()}
                    _adj = round(100.0 - sum(_meta_inputs.values()), 1)
                    _last_k = list(_meta_inputs.keys())[-1]
                    _meta_inputs[_last_k] = round(_meta_inputs[_last_k] + _adj, 1)
                cfg.set("sug_faixas_saved", _meta_inputs)
                cfg.save()
                st.success("✅ Meta de mix salva! O comparativo estará disponível na Análise de Contexto.")
                st.rerun()

    # ── Meta Mensal de Vendas (abaixo do mix) ────────────────────────────────
    with tab_meta:
        st.divider()
        st.markdown("#### 📈 Meta Mensal de Vendas (R$)")
        st.caption(
            "Define o valor de vendas líquidas que a loja precisa atingir no mês.  \n"
            "Aparece no **Bom Dia** como farol 🟢🟡🔴 de progresso do mês."
        )
        _meta_mensal_atual = float(cfg.get("meta_mensal_valor") or 0)
        _meta_mensal_input = st.number_input(
            "Meta do mês (R$)",
            min_value=0.0, value=_meta_mensal_atual, step=1000.0,
            format="%.2f", key="cfg_meta_mensal",
            help="Zero = sem meta definida (farol não aparece no Bom Dia)"
        )
        if st.button("💾 Salvar Meta Mensal", type="primary", key="btn_save_meta_mensal"):
            cfg.set("meta_mensal_valor", _meta_mensal_input)
            cfg.save()
            st.success(f"Meta mensal salva: R$ {_meta_mensal_input:,.2f}")
            st.rerun()

    # ── Aba Usuários (só gerente) ─────────────────────────────────────────────
    with tab_users:
        from modules.auth import NIVEL as _NIVEL_MAP
        _au_cfg = st.session_state.get("auth_user", {})

        st.markdown("#### 👤 Usuários do Pepper")

        # Hierarquia visual
        with st.expander("📋 Hierarquia de perfis"):
            st.markdown("""
| Perfil | Acesso |
|---|---|
| 🛠️ **Dev** | Acesso total + painel de sistema — exclusivo do responsável técnico |
| 🏢 **Admin** | Acesso total à(s) sua(s) franquia(s) — franqueado |
| 👔 **Supervisor** | Leitura de N lojas, sem Configurações — gerência regional |
| 🏪 **Gerente** | Operação completa da sua loja — responsável local |
| 🛍️ **Vendedor** | Bom Dia + Campanhas + sua carteira — nível operacional |
| 🎯 **Captador** | Bom Dia + Funil de visitas — captação externa |
""")

        st.info(
            f"🔑 **Senha padrão para novos usuários:** `{senha_padrao()}`  \n"
            "O usuário deve trocar no primeiro login.",
            icon=None,
        )

        # Lista de usuários (dev e admin veem todos; gerente só vê abaixo dele)
        _todos = list_users()
        _nv_eu = nivel(_au_cfg)
        _visiveis = [u for u in _todos if _NIVEL_MAP.get(u.get("perfil",""), 0) <= _nv_eu]
        if _visiveis:
            _u_rows = []
            for u in sorted(_visiveis, key=lambda x: -_NIVEL_MAP.get(x.get("perfil",""), 0)):
                p = u.get("perfil","")
                _u_rows.append({
                    "":          PERFIL_ICON.get(p,""),
                    "Login":     u["login"],
                    "Nome":      u.get("nome",""),
                    "Perfil":    PERFIL_LABEL.get(p, p.capitalize()),
                    "Loja":      u.get("loja","") or "—",
                    "Cód Vend.": u.get("cod_vendedor_microvix","") or "—",
                    "Ativo":     "✅" if u.get("ativo", True) else "❌",
                    "1º Acesso": "⚠️ Pendente" if u.get("primeiro_acesso") else "✓",
                })
            st.dataframe(pd.DataFrame(_u_rows), hide_index=True, width="stretch")

        # Formulário de criação — só mostra perfis que o usuário logado pode criar
        _criáveis = perfis_criáveis_por(_au_cfg)
        if _criáveis:
            st.divider()
            st.markdown("##### ➕ Novo usuário")
            st.caption(
                f"Senha inicial: **{senha_padrao()}** — o usuário troca no primeiro login. "
                "Você pode sobrescrever se precisar de uma senha específica."
            )
            with st.form("form_novo_usuario", clear_on_submit=True):
                _u1, _u2 = st.columns(2)
                _nu_login = _u1.text_input("Login *", placeholder="ex: joao.silva")
                _nu_nome  = _u2.text_input("Nome completo *")
                _u3, _u4  = st.columns(2)
                # Formata opções com ícone
                _opts = [f"{PERFIL_ICON.get(p,'')} {PERFIL_LABEL.get(p,p)}" for p in _criáveis]
                _sel  = _u3.selectbox("Perfil *", _opts)
                _nu_perfil = _criáveis[_opts.index(_sel)]
                _nu_loja  = _u4.text_input("Loja", placeholder="ex: Porto Ferreira")
                _u5, _u6  = st.columns(2)
                _nu_cod   = _u5.text_input(
                    "Cód. Vendedor Microvix",
                    placeholder="Obrigatório para vendedor",
                    help="Valor do campo cod_vendedor no LinxMovimento — filtra dados do vendedor",
                )
                _nu_senha = _u6.text_input(
                    "Senha personalizada (opcional)",
                    type="password",
                    placeholder=f"Padrão: {senha_padrao()}",
                )
                _sub_u = st.form_submit_button("✅ Criar usuário", type="primary", width="stretch")

            if _sub_u:
                if not _nu_login or not _nu_nome:
                    st.error("Login e Nome são obrigatórios.")
                else:
                    _ok, _msg = create_user(
                        login=_nu_login.strip().lower(),
                        nome=_nu_nome.strip(),
                        perfil=_nu_perfil,
                        cod_vendedor_microvix=_nu_cod.strip(),
                        loja=_nu_loja.strip(),
                        senha=_nu_senha.strip() or None,
                    )
                    if _ok:
                        _sp = _nu_senha.strip() or senha_padrao()
                        st.success(
                            f"✅ **{_nu_login}** criado como **{PERFIL_LABEL.get(_nu_perfil,_nu_perfil)}**.  \n"
                            f"Senha inicial: `{_sp}` — deve ser trocada no primeiro login."
                        )
                        st.rerun()
                    else:
                        st.error(f"❌ {_msg}")
        else:
            st.info("Seu perfil não tem permissão para criar novos usuários.")

        # Ativar / desativar / resetar senha
        _gerenciaveis = [
            u for u in _visiveis
            if u["login"] != _au_cfg.get("login")
            and _NIVEL_MAP.get(u.get("perfil",""), 0) < _nv_eu
        ]
        if _gerenciaveis:
            st.divider()
            st.markdown("##### 🔧 Gerenciar usuário")
            _gu_opts  = {u["login"]: u for u in _gerenciaveis}
            _gu_sel   = st.selectbox(
                "Selecione",
                list(_gu_opts.keys()),
                format_func=lambda l: f"{PERFIL_ICON.get(_gu_opts[l].get('perfil',''),'')}"
                                      f" {_gu_opts[l].get('nome', l)} ({l})",
                key="gu_sel",
            )
            if _gu_sel:
                _gu = _gu_opts[_gu_sel]
                _gc1, _gc2, _gc3 = st.columns(3)
                _tg_ativo = _gu.get("ativo", True)
                if _gc1.button("❌ Desativar" if _tg_ativo else "✅ Reativar", key="toggle_u"):
                    toggle_user(_gu_sel, not _tg_ativo)
                    st.success(f"{'Desativado' if _tg_ativo else 'Reativado'}: {_gu_sel}")
                    st.rerun()
                if _gc2.button("🔑 Resetar senha", key="reset_pw",
                               help=f"Redefine para {senha_padrao()} e força troca no próximo login"):
                    change_password(_gu_sel, senha_padrao())
                    # marca como primeiro acesso novamente
                    from modules.auth import _load as _aload, _save as _asave
                    _ausers = _aload()
                    for _au2 in _ausers:
                        if _au2["login"] == _gu_sel:
                            _au2["primeiro_acesso"] = True
                    _asave(_ausers)
                    st.success(f"Senha de **{_gu_sel}** redefinida para `{senha_padrao()}`. Troca obrigatória no próximo login.")
                    st.rerun()


# ── PAGE: Campanhas Ativas ────────────────────────────────────────────────────

def _apply_audience_filters(
    df_cand: pd.DataFrame,
    filtros: dict,
    client_map: dict,
    df_ret: pd.DataFrame,
) -> pd.DataFrame:
    """Aplica filtros de audiência de uma campanha ao DataFrame de candidatos.

    filtros keys (todos opcionais / 0 ou None = sem filtro):
      aniversario_mes     int  1-12
      aniversario_semana  int  1-53
      ultima_compra_ini   str  'YYYY-MM-DD'
      ultima_compra_fim   str  'YYYY-MM-DD'
      nascimento_ini      str  'YYYY-MM-DD'
      nascimento_fim      str  'YYYY-MM-DD'
    """
    if not filtros or df_cand.empty:
        return df_cand

    _today_year = date.today().year

    def _keep(codigo: str) -> bool:
        info = client_map.get(str(codigo), {})

        # Mês de aniversário
        _aniv_mes = filtros.get("aniversario_mes") or 0
        if _aniv_mes:
            if info.get("aniversario") != int(_aniv_mes):
                return False

        # Semana do aniversário (ISO week number)
        _aniv_sem = filtros.get("aniversario_semana") or 0
        if _aniv_sem:
            _nasc = info.get("nascimento", "")
            if not _nasc:
                return False
            try:
                _nasc_dt = datetime.strptime(_nasc, "%d/%m/%Y")
                _bday = _nasc_dt.replace(year=_today_year)
                if _bday.isocalendar()[1] != int(_aniv_sem):
                    return False
            except Exception:
                return False

        # Intervalo de última compra
        _uc_ini = filtros.get("ultima_compra_ini")
        _uc_fim = filtros.get("ultima_compra_fim")
        if _uc_ini or _uc_fim:
            _rows_c = df_ret[df_ret["codigo_cliente"].astype(str) == str(codigo)]
            if _rows_c.empty:
                return False
            _last_dt = pd.to_datetime(_rows_c["ultima_compra"]).max()
            if pd.isna(_last_dt):
                return False
            _last_d = _last_dt.date()
            try:
                if _uc_ini and _last_d < date.fromisoformat(str(_uc_ini)):
                    return False
                if _uc_fim and _last_d > date.fromisoformat(str(_uc_fim)):
                    return False
            except Exception:
                pass

        # Intervalo de data de nascimento
        _nasc_ini = filtros.get("nascimento_ini")
        _nasc_fim = filtros.get("nascimento_fim")
        if _nasc_ini or _nasc_fim:
            _nasc_str = info.get("nascimento", "")
            if not _nasc_str:
                return False
            try:
                _nasc_date = datetime.strptime(_nasc_str, "%d/%m/%Y").date()
                if _nasc_ini and _nasc_date < date.fromisoformat(str(_nasc_ini)):
                    return False
                if _nasc_fim and _nasc_date > date.fromisoformat(str(_nasc_fim)):
                    return False
            except Exception:
                return False

        return True

    _mask = df_cand["codigo_cliente"].astype(str).apply(_keep)
    return df_cand[_mask].copy()


def page_campanhas_ativas():
    st.markdown('<div class="cb-title">🎯 Campanhas Ativas</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="cb-sub">Clientes candidatos a contato conforme a campanha selecionada '
        '— filtros de audiência e histórico de reativação</div>',
        unsafe_allow_html=True,
    )

    _today_iso = str(date.today())

    client_map = st.session_state.client_map or {}

    # ── Campanha e DDD ───────────────────────────────────────────────────────
    # Só exibe campanhas ativas (sem vencimento ou vencimento >= hoje)
    campaigns = st.session_state.campaigns or []
    active_campaigns = [
        c for c in campaigns
        if not c.get("expiry") or c["expiry"] >= _today_iso
    ]
    col_camp, col_ddd = st.columns([3, 1])
    with col_camp:
        if active_campaigns:
            camp_names    = [c["nome"] for c in active_campaigns]
            sel_name      = st.selectbox("📢 Campanha ativa para envio WhatsApp", camp_names, key="ret_camp")
            selected_camp = next((c for c in active_campaigns if c["nome"] == sel_name), None)
        else:
            if campaigns:
                st.warning("⚠️ Todas as campanhas estão vencidas. Atualize as datas de validade em **📣 Marketing**.")
            else:
                st.info("💡 Configure campanhas em **📣 Marketing** para ativar os links WhatsApp.")
            selected_camp = None
    with col_ddd:
        ddd = st.text_input(
            "DDD padrão",
            value=cfg.get("ddd_padrao", ""),
            max_chars=2,
            placeholder="Ex: 19",
            help="Usado quando o telefone não tem DDD. Ex: 19 para Piracicaba/SP.",
            key="ret_ddd",
        )
        if ddd and ddd != cfg.get("ddd_padrao", ""):
            cfg.set("ddd_padrao", ddd)
            cfg.save()

    # Quando campanha muda, atualiza thresholds a partir da campanha
    if selected_camp:
        _prev = st.session_state.get("ret_camp_prev", "")
        if selected_camp["nome"] != _prev:
            _ct = selected_camp.get("thresholds", {})
            st.session_state["ret_lv"]        = int(_ct.get("LV", 12))
            st.session_state["ret_oc"]        = int(_ct.get("OC", 12))
            st.session_state["ret_ml"]        = int(_ct.get("ML", 12))
            st.session_state["ret_le"]        = int(_ct.get("LE", 6))
            st.session_state["ret_lc"]        = int(_ct.get("LC", 3))
            st.session_state["ret_camp_prev"] = selected_camp["nome"]
            st.rerun()  # força re-render para os widgets lerem os novos valores

    # Mostra filtros de audiência da campanha selecionada (somente leitura)
    if selected_camp:
        _filtros_camp = selected_camp.get("filtros") or {}
        _filtros_ativos = {k: v for k, v in _filtros_camp.items() if v}
        if _filtros_ativos:
            _filt_labels = []
            _mes_map = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
            if _filtros_ativos.get("aniversario_mes"):
                _m = int(_filtros_ativos["aniversario_mes"])
                _filt_labels.append(f"Aniversário em {_mes_map[_m-1]}")
            if _filtros_ativos.get("aniversario_semana"):
                _filt_labels.append(f"Semana de aniv. #{_filtros_ativos['aniversario_semana']}")
            if _filtros_ativos.get("ultima_compra_ini") or _filtros_ativos.get("ultima_compra_fim"):
                _filt_labels.append(f"Última compra entre {_filtros_ativos.get('ultima_compra_ini','?')} e {_filtros_ativos.get('ultima_compra_fim','?')}")
            if _filtros_ativos.get("nascimento_ini") or _filtros_ativos.get("nascimento_fim"):
                _filt_labels.append(f"Nascimento entre {_filtros_ativos.get('nascimento_ini','?')} e {_filtros_ativos.get('nascimento_fim','?')}")
            st.caption("🎯 Filtros da campanha: " + " · ".join(_filt_labels))

    # ── Janelas de contato ───────────────────────────────────────────────────
    st.markdown("#### ⏱ Janelas de Contato")
    _jc1, _jc2 = st.columns([3, 1])
    with _jc1:
        st.info(
            "**LV · OC · ML · LE — 5 janelas fixas de saúde visual:**  \n"
            "**J1** 12m → **J2** 18m → **J3** 24m → **J4** 30m → **J5** 36m → ❌ **Perdido** (42m+)  \n"
            "Cada janela usa mensagem específica focada em saúde visual."
        )
    with _jc2:
        lc_m = st.number_input("L. Contato (meses)", min_value=1, max_value=12,
                               value=3, key="ret_lc",
                               help="Lentes de contato têm ciclo próprio (padrão: 3 meses)")

    thresholds = {
        "LV": 12, "OC": 12, "ML": 12, "LE": 12,   # janela 1 como mínimo
        "LC": int(lc_m),
    }

    # ── Carregar dados ───────────────────────────────────────────────────────
    col_btn, col_info = st.columns([2, 3])
    with col_btn:
        load_btn = st.button(
            "🔄 Buscar histórico (48 meses)", type="primary", width="stretch"
        )
    with col_info:
        if st.session_state.df_retorno is not None:
            st.caption(f"Dados carregados em: {st.session_state.retorno_ts}")
        else:
            st.caption("Clique para buscar o histórico de compras dos últimos 48 meses.")

    if load_btn:
        api  = get_api()
        pmap = st.session_state.product_map
        with st.spinner("Consultando 48 meses de vendas no Microvix... (pode levar alguns segundos)"):
            try:
                if api:
                    df_raw = api.get_retorno_raw(months=48, product_map=pmap)
                else:
                    df_raw = mock_retorno(client_map)
                st.session_state.df_retorno = df_raw
                st.session_state.retorno_ts = datetime.now().strftime("%d/%m/%Y %H:%M")
                st.rerun()
            except MicrovixAPIError as e:
                st.error(str(e))
                return

    df_ret = st.session_state.df_retorno
    if df_ret is None or df_ret.empty:
        st.info("Clique em **🔄 Buscar histórico** para carregar os dados.")
        return

    tab_contato, tab_rfm, tab_recall = st.tabs([
        "🎯  Candidatos a Contato",
        "📊  RFM — Segmentação",
        "🔮  Próxima Troca Prevista",
    ])

    with tab_contato:
        _filtros_sel = (selected_camp.get("filtros") or {}) if selected_camp else {}
        _page_retorno_contato(df_ret, thresholds, client_map, selected_camp, ddd, _filtros_sel)

    with tab_rfm:
        _page_rfm(df_ret, client_map, selected_camp, ddd)

    with tab_recall:
        _page_recall(df_ret, client_map, selected_camp, ddd)


def _page_retorno_contato(df_ret, thresholds, client_map, selected_camp, ddd, filtros=None):
    """Aba 'Candidatos a Contato' — 5 janelas de saúde visual + Perdidos."""
    today   = pd.Timestamp(date.today())
    df_work = df_ret.copy()
    df_work["dias"] = (today - pd.to_datetime(df_work["ultima_compra"])).dt.days

    # Atribui janela e template a cada linha
    df_work["_janela_num"] = df_work.apply(
        lambda r: _get_janela(int(r["dias"]), str(r["categoria"]))[0], axis=1
    )
    df_work["_janela_lbl"] = df_work.apply(
        lambda r: _get_janela(int(r["dias"]), str(r["categoria"]))[1], axis=1
    )

    # Um cliente pode ter múltiplas categorias — fica a mais urgente (maior janela)
    df_work_uniq = (
        df_work.sort_values("_janela_num", ascending=False)
        .drop_duplicates("codigo_cliente")
    )

    # Aplica filtros de campanha
    if filtros:
        df_work_uniq = _apply_audience_filters(df_work_uniq, filtros, client_map, df_ret)
        if {k: v for k, v in filtros.items() if v}:
            st.caption(f"🎯 Filtros de audiência aplicados — {len(df_work_uniq)} candidato(s).")

    # KPIs gerais
    _mapeados = len(set(df_work["codigo_cliente"]) & set(client_map.keys()))
    _em_janela = df_work_uniq[df_work_uniq["_janela_num"].between(1, 5)]
    _perdidos  = df_work_uniq[df_work_uniq["_janela_num"] == 6]
    _kc = st.columns(4)
    _kc[0].metric("Em janela ativa (J1-J5)", len(_em_janela))
    _kc[1].metric("❌ Perdidos (>42m)",       len(_perdidos))
    _kc[2].metric("Clientes analisados",       _mapeados)
    for _ji, _jm in enumerate(JANELAS_MESES):
        pass  # detalhes visíveis nas abas abaixo

    st.divider()

    # ── Sub-tabs: J1 a J5 + Perdidos + LC ────────────────────────────────────
    _tab_labels = [f"J{i+1} — {m}m" for i, m in enumerate(JANELAS_MESES)]
    _tab_labels += ["❌ Perdidos", "💧 L. Contato"]
    _tabs = st.tabs(_tab_labels)

    def _render_janela_tab(df_janela, janela_num, tab_obj):
        """Renderiza uma janela ou a aba de Perdidos."""
        with tab_obj:
            if df_janela.empty:
                if janela_num == 6:
                    st.success("Nenhum cliente classificado como Perdido. 🎉")
                else:
                    st.success(f"Nenhum cliente na Janela {janela_num} no momento.")
                return

            # Template sugerido para esta janela
            if janela_num in TEMPLATES_JANELA:
                with st.expander("💬 Mensagem sugerida para esta janela — clique para ver/copiar"):
                    st.code(TEMPLATES_JANELA[janela_num], language=None)

            # Monta linhas
            rows_out, codigos, nomes_raw = [], [], []
            for _, row in df_janela.iterrows():
                codigo    = str(row["codigo_cliente"])
                info      = client_map.get(codigo, {})
                nome      = (info.get("nome") or "").strip() or f"Cliente #{codigo}"
                fone      = info.get("fone", "") or ""
                ultima    = pd.to_datetime(row["ultima_compra"]).strftime("%d/%m/%Y")
                dias      = int(row["dias"])
                cat_code  = row["categoria"]
                cat_label = CAT_NAMES.get(cat_code, cat_code)

                # Template da janela > template da campanha (foco em saúde visual)
                wa_link = ""
                if fone:
                    _tmpl = TEMPLATES_JANELA.get(janela_num, "")
                    if selected_camp and not _tmpl:
                        _tmpl = selected_camp.get("template", "")
                    if _tmpl:
                        _msg = _tmpl.replace("{nome}", nome.split()[0])
                        wa_link = make_whatsapp_link(fone, _msg, ddd)

                was_contacted  = db.was_contacted_this_month(codigo)
                days_since_cnt = db.days_since_last_contact(codigo)
                nome_display   = nome
                if 0 <= days_since_cnt <= 6:
                    _b = "hoje" if days_since_cnt == 0 else f"há {days_since_cnt}d"
                    nome_display = f"{nome}  ⚠️ Contatado {_b}"

                codigos.append(codigo); nomes_raw.append(nome)
                rows_out.append({
                    "Nome":          nome_display,
                    "📱 WhatsApp":   wa_link,
                    "Categoria":     cat_label,
                    "Última Compra": ultima,
                    "Dias":          dias,
                    "Fone":          fone or "—",
                    "✅ Contatado":  was_contacted,
                })

            df_show = pd.DataFrame(rows_out)
            contacted_set = {codigos[i] for i, r in enumerate(rows_out) if r["✅ Contatado"]}

            st.markdown(
                f'<div class="section-title">👥 {len(df_show)} clientes</div>',
                unsafe_allow_html=True,
            )
            if janela_num == 6:
                st.warning(
                    "⚠️ **Estes clientes passaram por todas as 5 janelas de contato sem recompra.**  \n"
                    "São considerados **ex-clientes (Perdidos)**. Um último contato personalizado "
                    "pode ser tentado antes de arquivá-los."
                )

            key_sfx = f"_j{janela_num}"
            edited = st.data_editor(
                df_show, width="stretch", hide_index=True,
                height=min(500, 80 + len(df_show) * 35),
                key=f"editor{key_sfx}",
                column_config={
                    "📱 WhatsApp": st.column_config.LinkColumn("📱 WhatsApp", display_text="📱 Enviar"),
                    "Dias":        st.column_config.NumberColumn("Dias s/ comprar", format="%d"),
                    "✅ Contatado": st.column_config.CheckboxColumn("✅ Contatado"),
                },
                disabled=["Nome", "📱 WhatsApp", "Categoria", "Última Compra", "Dias", "Fone"],
            )

            # LOG-1: indica quantos checkboxes estão marcados mas ainda não salvos
            _pendentes_salvar = sum(
                1 for i, (_, row) in enumerate(edited.iterrows())
                if row.get("✅ Contatado") and codigos[i] not in contacted_set
            )
            if _pendentes_salvar > 0:
                st.caption(
                    f"💾 **{_pendentes_salvar} contato(s) marcado(s) — clique Salvar para registrar no histórico.**"
                )

            _cs, _ce, _ = st.columns([1.5, 1.5, 3])
            with _cs:
                if st.button("💾 Salvar Contatos", type="primary",
                             key=f"save{key_sfx}", width="stretch"):
                    camp_nome = selected_camp["nome"] if selected_camp else f"Janela {janela_num}"
                    n_novos = 0
                    for i, (_, row) in enumerate(edited.iterrows()):
                        if row["✅ Contatado"] and codigos[i] not in contacted_set:
                            db.log_contact(codigos[i], nomes_raw[i], camp_nome)
                            n_novos += 1
                    if n_novos:
                        st.success(f"✅ {n_novos} contato(s) registrado(s) no histórico!")
                        st.rerun()
                    else:
                        st.info("Nenhum novo contato para registrar.")
            with _ce:
                _exp = df_show.drop(columns=["📱 WhatsApp"]).copy()
                _exp["Nome"] = nomes_raw
                st.download_button(
                    "📥 Exportar",
                    data=to_excel({f"Janela {janela_num}": _exp}),
                    file_name=f"retorno_j{janela_num}_{date.today().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl{key_sfx}",
                )

    # Renderiza J1 a J5
    for _ji in range(5):
        _df_j = df_work_uniq[df_work_uniq["_janela_num"] == _ji + 1]
        _render_janela_tab(_df_j, _ji + 1, _tabs[_ji])

    # Perdidos
    _render_janela_tab(_perdidos, 6, _tabs[5])

    # LC — mantém lógica original de threshold
    with _tabs[6]:
        st.markdown("#### 💧 Lentes de Contato")
        st.caption(f"Threshold configurado: {thresholds.get('LC', 3)} meses")
        _df_lc = df_work_uniq[
            (df_work_uniq["categoria"] == "LC") &
            (df_work_uniq["dias"] >= thresholds.get("LC", 3) * 30)
        ]
        if _df_lc.empty:
            st.success("Nenhum cliente de L. de Contato fora da janela.")
        else:
            _render_janela_tab(_df_lc, 0, st)


# ── RFM: aba Segmentação ─────────────────────────────────────────────────────

def _page_rfm(df_ret, client_map, selected_camp, ddd):
    """Conteúdo da aba RFM — scoring e segmentação de clientes."""
    st.markdown(
        '<div class="section-title">📊 RFM — Segmentação de Clientes</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "**Recency** (quando comprou por último) · **Frequency** (quantas vezes) · "
        "**Monetary** (quanto gastou). Scores 1–5, total máximo 15."
    )

    with st.spinner("Calculando scores RFM..."):
        df_rfm = score_rfm(df_ret, client_map)

    if df_rfm.empty:
        st.info("Sem dados suficientes para calcular RFM. Busque o histórico primeiro.")
        return

    # ── Resumo por segmento ───────────────────────────────────────────────────
    df_seg = segment_summary(df_rfm)
    st.markdown("#### Distribuição por Segmento")

    _seg_cols = st.columns(min(len(df_seg), 4))
    for _si, (_sidx, _srow) in enumerate(df_seg.iterrows()):
        _col = _seg_cols[_si % len(_seg_cols)]
        _cor = SEGMENT_COLORS.get(_srow["Segmento"], "#AAA")
        # Separador de milhar no padrão brasileiro (1.234, não 1,234)
        _ticket_med = f'{_srow["M_Médio"]:,.0f}'.replace(",", ".")
        _col.markdown(
            f'<div style="background:{_cor}22;border-left:4px solid {_cor};'
            f'padding:10px 14px;border-radius:6px;margin-bottom:8px;">'
            f'<div style="font-size:.82rem;color:{_cor};font-weight:700;">{_srow["Segmento"]}</div>'
            f'<div style="font-size:1.4rem;font-weight:800;color:#1C1816;">'
            f'{int(_srow["Clientes"])}</div>'
            f'<div style="font-size:.75rem;color:#7A6A5A;">score médio: {_srow["Score_Médio"]:.1f} · '
            f'ticket médio: R$ {_ticket_med}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Filtro de segmento ────────────────────────────────────────────────────
    _all_segs = ["Todos"] + sorted(df_rfm["segmento"].unique().tolist())
    _priority_segs = ["Todos", "🏆 Campeões", "⚠️ Em Risco", "💎 Fiéis", "🌱 Potenciais Fiéis",
                      "🌙 Hibernando", "❄️ Perdidos", "👤 Regular"]
    _seg_filter = st.selectbox(
        "Filtrar segmento",
        [s for s in _priority_segs if s in _all_segs],
        key="rfm_seg_filter",
    )

    df_show_rfm = df_rfm if _seg_filter == "Todos" else df_rfm[df_rfm["segmento"] == _seg_filter]

    st.markdown(
        f'<div class="section-title">👥 {len(df_show_rfm)} clientes — {_seg_filter}</div>',
        unsafe_allow_html=True,
    )

    # Verifica se e-mail está configurado
    from modules.email_sender import load_email_config as _load_ecfg_rfm, BrevoClient as _BrevoClient
    from modules.lgpd import is_optout as _is_optout
    _ecfg_rfm  = _load_ecfg_rfm()
    _email_ok  = bool(_ecfg_rfm.get("brevo_api_key") and _ecfg_rfm.get("sender_email"))
    _segs_email = {"⚠️ Em Risco", "🌙 Hibernando"}   # segmentos que recebem e-mail D+1

    # Monta linhas com WhatsApp + E-mail
    _rfm_rows = []
    _email_elegíveis = []   # para disparo em lote
    for _, _rrow in df_show_rfm.iterrows():
        _wa  = ""
        _fone = _rrow.get("fone", "") or ""
        _info = client_map.get(str(_rrow["codigo_cliente"]), {})
        _email_cli = _info.get("email", "") or ""
        _client_rows = df_ret[df_ret["codigo_cliente"] == _rrow["codigo_cliente"]]
        if not _client_rows.empty:
            _latest_row = _client_rows.loc[_client_rows["ultima_compra"].idxmax()]
            _cat_code   = str(_latest_row["categoria"])
            _ultima_dt  = _latest_row["ultima_compra"]
        else:
            _cat_code  = "LV"
            _ultima_dt = pd.NaT
        _cat_label  = CAT_NAMES.get(_cat_code, "armação")
        _ultima_str = pd.to_datetime(_ultima_dt).strftime("%d/%m/%Y") if pd.notna(_ultima_dt) else "—"
        _dias_r     = int(_rrow["R_dias"])
        _msg_texto  = ""
        if selected_camp:
            _msg_texto = format_message(selected_camp["template"], _rrow["nome"], _cat_label, _ultima_str, _dias_r)
        if _fone and _msg_texto:
            _wa = make_whatsapp_link(_fone, _msg_texto, ddd)
        # E-mail elegível: segmento Em Risco ou Hibernando + tem e-mail + brevo
        # configurado + NÃO está em opt-out LGPD (trava de consentimento)
        if (_rrow["segmento"] in _segs_email and _email_cli and _email_ok
                and _msg_texto and not _is_optout(str(_rrow["codigo_cliente"]))):
            _email_elegíveis.append({
                "email":    _email_cli,
                "nome":     _rrow["nome"],
                "mensagem": _msg_texto,
            })

        _rfm_rows.append({
            "Segmento":        _rrow["segmento"],
            "Nome":            _rrow["nome"],
            "Score":           int(_rrow["rfm_score"]),
            "R":               int(_rrow["R_score"]),
            "F":               int(_rrow["F_score"]),
            "M":               int(_rrow["M_score"]),
            "Dias s/ comprar": int(_rrow["R_dias"]),
            "Compras":         int(_rrow["F_compras"]),
            "Gasto Total":     round(float(_rrow["M_total"]), 2),
            "📱 WhatsApp":     _wa,
            "📧 E-mail":       "✉️" if _email_cli else "—",
        })

    _df_rfm_show = pd.DataFrame(_rfm_rows)
    st.dataframe(
        _df_rfm_show,
        width="stretch",
        hide_index=True,
        height=min(600, 80 + len(_df_rfm_show) * 35),
        column_config={
            "Score":           st.column_config.NumberColumn("Score RFM", format="%d / 15"),
            "R":               st.column_config.NumberColumn("R", format="%d", help="Recency (1–5): quão recente"),
            "F":               st.column_config.NumberColumn("F", format="%d", help="Frequency (1–5): quantas compras"),
            "M":               st.column_config.NumberColumn("M", format="%d", help="Monetary (1–5): quanto gastou"),
            "Dias s/ comprar": st.column_config.NumberColumn("Dias", format="%d"),
            "Compras":         st.column_config.NumberColumn("Compras", format="%d"),
            "Gasto Total":     st.column_config.NumberColumn("Gasto Total", format="R$ %.2f"),
            "📱 WhatsApp":     st.column_config.LinkColumn("📱 WhatsApp", display_text="📱 Abrir"),
            "📧 E-mail":       st.column_config.TextColumn("📧", width="small",
                                    help="✉️ = tem e-mail cadastrado"),
        },
    )

    # ── Disparo em lote por e-mail (Em Risco + Hibernando) ──────────────────
    if _email_elegíveis:
        from modules.email_queue import push_to_queue as _push_q, queue_size as _qsize
        st.divider()
        st.markdown(f"##### 📧 Disparo por e-mail — {len(_email_elegíveis)} elegíveis (⚠️ Em Risco + 🌙 Hibernando)")
        _assunto_disp = st.text_input(
            "Assunto", value=_ecfg_rfm.get("subject_default", "Uma mensagem especial para você 👓"),
            key="rfm_email_subject",
        )
        _col_disp1, _col_disp2, _col_disp3 = st.columns([2, 2, 3])
        with _col_disp1:
            if st.button(f"📧 Enviar {len(_email_elegíveis)} agora", type="primary", key="rfm_send_emails"):
                if not _email_ok:
                    st.error("Configure o Brevo em ⚙️ Configurações → Credenciais → Canal E-mail.")
                elif not selected_camp:
                    st.warning("Selecione uma campanha acima para usar o template de mensagem.")
                else:
                    _client_rfm = _BrevoClient.from_config()
                    if _client_rfm:
                        with st.spinner(f"Enviando {len(_email_elegíveis)} e-mails via Brevo..."):
                            _result = _client_rfm.send_bulk(_email_elegíveis, _assunto_disp)
                        if _result["falhas"] == 0:
                            st.success(f"✅ {_result['enviados']} e-mails enviados!")
                        else:
                            st.warning(
                                f"✅ {_result['enviados']} enviados · ❌ {_result['falhas']} falhas:  \n"
                                + "  \n".join(_result["erros"][:5])
                            )
        with _col_disp2:
            if st.button(f"🕑 Agendar D+1 ({len(_email_elegíveis)})", key="rfm_queue_emails",
                         help="Coloca na fila para envio automático às 02h de amanhã"):
                if not _email_ok:
                    st.error("Configure o Brevo primeiro.")
                elif not selected_camp:
                    st.warning("Selecione uma campanha acima.")
                else:
                    _items_fila = [
                        {**e, "assunto": _assunto_disp,
                         "segmento": next(
                             (r["segmento"] for r in _rfm_rows if r.get("Nome","").startswith(e["nome"][:10])),
                             ""
                         )}
                        for e in _email_elegíveis
                    ]
                    _adicionados = _push_q(_items_fila)
                    st.success(f"✅ {_adicionados} e-mail(s) agendados para as 02h. Fila total: {_qsize()}")
        with _col_disp3:
            _fila_n = _qsize()
            if _fila_n > 0:
                st.info(f"📬 Fila: **{_fila_n}** e-mail(s) aguardando disparo às 02h.")
            elif not selected_camp:
                st.caption("Selecione uma campanha para ativar o disparo.")
            else:
                st.caption(
                    f"**{selected_camp['nome']}** · Template adaptado para e-mail automaticamente."
                )
    elif _email_ok and _seg_filter in ("Todos", "⚠️ Em Risco", "🌙 Hibernando"):
        st.caption("📧 Nenhum cliente elegível tem e-mail cadastrado. Importe o cadastro de clientes com o campo e-mail.")

    # Legendas
    with st.expander("ℹ️ Como interpretar os segmentos"):
        st.markdown("""
| Segmento | Perfil | Ação recomendada |
|---|---|---|
| 🏆 **Campeões** | Compra frequente, muito recente, alto valor | Programa VIP, oferta exclusiva, convite para eventos |
| 💎 **Fiéis** | Alta frequência, recentes | Manter engajamento, preview de lançamentos |
| 🌱 **Potenciais Fiéis** | Recentes mas ainda poucos compras | Incentivar segunda/terceira compra |
| ⚠️ **Em Risco** | Já compraram bastante, mas sumiram | **E-mail D+1** · Mensagem personalizada urgente |
| 🌙 **Hibernando** | Não compram há muito, baixo valor | **E-mail D+1** · Campanha de reativação com desconto |
| ❄️ **Perdidos** | Muito tempo sem comprar | Última tentativa ou descontinuar |
| 👤 **Regular** | Perfil médio | Campanha padrão de reativação |
        """)

    # Export
    _df_export = _df_rfm_show.drop(columns=["📱 WhatsApp", "📧 E-mail"], errors="ignore")
    _rcol1, _rcol2 = st.columns([2, 3])
    with _rcol1:
        st.download_button(
            "📥 Exportar RFM Excel",
            data=to_excel({"RFM Segmentação": _df_export}),
            file_name=f"rfm_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_rfm",
        )
    with _rcol2:
        # Régua de Pós-Venda — ativa varredura nos dados carregados
        if st.button("📨 Ativar Régua Pós-Venda (D+1/7/30/90)", key="btn_pos_venda",
                     help="Varre as compras recentes e agenda e-mails automáticos de acompanhamento"):
            from modules.pos_venda import scan_from_retorno
            _pv_res = scan_from_retorno(df_ret, client_map)
            if _pv_res["novos"] > 0:
                st.success(
                    f"✅ {_pv_res['novos']} cliente(s) incluídos na régua D+1/7/30/90.  \n"
                    f"{_pv_res['ja_registrados']} já estavam registrados. "
                    "E-mails serão enviados automaticamente às 02h nas datas certas."
                )
            else:
                st.info(f"Nenhum cliente novo na régua. ({_pv_res['ja_registrados']} já registrados)")


def _page_recall(df_ret, client_map, selected_camp, ddd):
    """Aba Próxima Troca Prevista — visão proativa: quem vai precisar trocar em breve."""
    from modules.prescricao import (
        get_ultima_receita, save_prescricao, dias_para_vencer,
        data_vencimento, format_grau,
    )
    st.markdown(
        '<div class="section-title">🔮 Próxima Troca Prevista</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Quem contatar **antes** de sumir. "
        "Usa a **data de vencimento da receita** quando cadastrada; "
        "caso contrário usa o ciclo médio da categoria."
    )

    if df_ret is None or df_ret.empty:
        st.info("Busque o histórico em **Candidatos a Contato** para ver as previsões.")
        return

    # Ciclos de recompra por categoria (dias) — usados como fallback quando não há receita
    _CICLOS_DEFAULT = {
        "LV": 730, "OC": 548, "ML": 730,
        "LE": 365, "LC": 30,  "AC": 180,
    }

    # Controle da janela de alerta
    _janela_dias = st.slider(
        "Mostrar clientes que vão trocar nos próximos X dias",
        min_value=7, max_value=120, value=30, step=7,
        key="recall_janela",
    )

    today = pd.Timestamp(date.today())
    rows_recall = []

    for _, row in df_ret.iterrows():
        cat    = str(row.get("categoria", ""))
        ult_dt = pd.to_datetime(row.get("ultima_compra"), errors="coerce")
        if pd.isna(ult_dt):
            continue
        codigo = str(row.get("codigo_cliente", ""))

        # R2: usa vencimento real da receita se disponível (só para LE/LV)
        _venc_receita = data_vencimento(codigo) if cat in ("LE", "LV") else None
        if _venc_receita:
            proxima        = pd.Timestamp(_venc_receita)
            _fonte_ciclo   = "📋 receita"
        else:
            ciclo          = _CICLOS_DEFAULT.get(cat, 365)
            proxima        = ult_dt + pd.Timedelta(days=ciclo)
            _fonte_ciclo   = "📅 ciclo médio"

        dias_restantes = (proxima - today).days

        if dias_restantes < 0 or dias_restantes > _janela_dias:
            continue   # já passou (coberto pelo Candidatos a Contato) ou longe demais

        codigo = str(row.get("codigo_cliente", ""))
        info   = client_map.get(codigo, {})
        nome   = info.get("nome", f"Cliente #{codigo}")
        fone   = info.get("fone", "") or ""

        urgencia = "🔴 Esta semana" if dias_restantes <= 7 else (
                   "🟡 Este mês"   if dias_restantes <= 30 else "🟢 Próximo mês")

        wa = ""
        if selected_camp and fone:
            _cat_lbl  = CAT_NAMES.get(cat, cat)
            _ult_str  = ult_dt.strftime("%d/%m/%Y")
            _msg      = format_message(selected_camp["template"], nome, _cat_lbl, _ult_str, 0)
            wa = make_whatsapp_link(fone, _msg, ddd)

        # Resumo da receita se disponível
        _rec = get_ultima_receita(codigo)
        _rec_txt = "—"
        if _rec:
            _rec_txt = (f"OD {format_grau(_rec['od'])} | OE {format_grau(_rec['oe'])}"
                        f" | vence {_rec['data_receita']}")

        rows_recall.append({
            "Urgência":       urgencia,
            "Nome":           nome,
            "Categoria":      CAT_NAMES.get(cat, cat),
            "Fonte":          _fonte_ciclo,
            "Última Compra":  ult_dt.strftime("%d/%m/%Y"),
            "Próxima Troca":  proxima.strftime("%d/%m/%Y"),
            "Dias Restantes": dias_restantes,
            "Receita Cadastrada": _rec_txt,
            "📱 WhatsApp":    wa,
            "_ordem":         dias_restantes,
            "_codigo":        codigo,
        })

    if not rows_recall:
        st.success(f"Nenhum cliente previsto para trocar nos próximos {_janela_dias} dias.")
        return

    rows_recall.sort(key=lambda r: r["_ordem"])
    _codigos_recall = [r.pop("_codigo") for r in rows_recall]
    df_recall = pd.DataFrame(rows_recall).drop(columns=["_ordem"])

    # KPIs
    _kr1, _kr2, _kr3, _kr4 = st.columns(4)
    _kr1.metric("📋 Na janela",     len(df_recall))
    _kr2.metric("🔴 Esta semana",   sum(1 for r in rows_recall if "Esta semana" in r["Urgência"]))
    _kr3.metric("🟡 Este mês",      sum(1 for r in rows_recall if "Este mês"    in r["Urgência"]))
    _kr4.metric("📋 Com receita",   sum(1 for r in rows_recall if r["Fonte"] == "📋 receita"))

    st.dataframe(
        df_recall, hide_index=True, width="stretch",
        height=min(600, 80 + len(df_recall) * 35),
        column_config={
            "Urgência":            st.column_config.TextColumn("", width="medium"),
            "Fonte":               st.column_config.TextColumn("Fonte", width="small",
                                       help="📋 receita = usa vencimento real | 📅 ciclo médio = estimativa"),
            "Dias Restantes":      st.column_config.NumberColumn("Dias", format="%d"),
            "Receita Cadastrada":  st.column_config.TextColumn("Receita"),
            "📱 WhatsApp":         st.column_config.LinkColumn("📱", display_text="📱 Contatar"),
        },
    )

    # R2 — Cadastrar receita de um cliente da lista
    st.divider()
    with st.expander("📋 Cadastrar receita de um cliente da lista"):
        st.caption("A receita substitui o ciclo médio na data de Próxima Troca.")
        _rec_nomes = {str(_codigos_recall[i]): r["Nome"] for i, r in enumerate(rows_recall)}
        _rec_sel   = st.selectbox("Cliente", options=list(_rec_nomes.keys()),
                                   format_func=lambda c: _rec_nomes.get(c, c),
                                   key="recall_rec_sel")
        if _rec_sel:
            _rec_atual = get_ultima_receita(_rec_sel)
            if _rec_atual:
                st.caption(f"Receita atual: OD {format_grau(_rec_atual['od'])} | "
                           f"OE {format_grau(_rec_atual['oe'])} | "
                           f"validade: {_rec_atual['data_receita']}")
        with st.form("form_receita_recall", clear_on_submit=True):
            _rc1, _rc2 = st.columns(2)
            _rc1.markdown("**Olho Direito (OD)**")
            _rc2.markdown("**Olho Esquerdo (OE)**")
            _ra1, _ra2, _ra3 = _rc1.columns(3)
            _rb1, _rb2, _rb3 = _rc2.columns(3)
            _od_esf = _ra1.number_input("Esf.", value=0.0, step=0.25, format="%.2f", key="od_esf")
            _od_cil = _ra2.number_input("Cil.", value=0.0, step=0.25, format="%.2f", key="od_cil")
            _od_eix = _ra3.number_input("Eixo", value=0, step=5, min_value=0, max_value=180, key="od_eix")
            _oe_esf = _rb1.number_input("Esf.", value=0.0, step=0.25, format="%.2f", key="oe_esf")
            _oe_cil = _rb2.number_input("Cil.", value=0.0, step=0.25, format="%.2f", key="oe_cil")
            _oe_eix = _rb3.number_input("Eixo", value=0, step=5, min_value=0, max_value=180, key="oe_eix")
            _rc3, _rc4 = st.columns(2)
            _adicao    = _rc3.number_input("Adição", value=0.0, step=0.25, format="%.2f", key="adicao")
            _dt_rec    = _rc4.text_input("Data da receita (DD/MM/AAAA)", value=date.today().strftime("%d/%m/%Y"), key="dt_rec")
            _optom     = st.text_input("Optometrista / CRO", key="optom_rec")
            _sub_rec   = st.form_submit_button("💾 Salvar receita", type="primary")

        if _sub_rec and _rec_sel:
            save_prescricao(
                _rec_sel, _od_esf, _od_cil, _od_eix,
                _oe_esf, _oe_cil, _oe_eix, _adicao,
                _dt_rec, 12, _optom,
            )
            st.success(f"✅ Receita salva para {_rec_nomes.get(_rec_sel,'?')}. "
                       "A data de Próxima Troca será calculada pelo vencimento real da receita.")
            st.rerun()

    st.download_button(
        "📥 Exportar Previsões",
        data=to_excel({"Proxima Troca": df_recall.drop(columns=["📱 WhatsApp"], errors="ignore")}),
        file_name=f"recall_{date.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_recall",
    )

    with st.expander("ℹ️ Como é calculada a data de Próxima Troca"):
        st.markdown("""
| Situação | Fonte da data |
|---|---|
| Receita cadastrada (LV/LE) | Data da receita + validade (12 meses por padrão) |
| Sem receita cadastrada | Última compra + ciclo médio da categoria |

**Ciclos médios usados como fallback:**
LV 24m · OC 18m · ML 24m · LE 12m · LC 30 dias · AC 6m
        """)


# ── PAGE: Marketing ───────────────────────────────────────────────────────────

def page_marketing():
    st.markdown('<div class="cb-title">📣 Marketing</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="cb-sub">Campanhas de reativação de clientes via WhatsApp e histórico de contatos</div>',
        unsafe_allow_html=True,
    )

    tab_camp, tab_aniv, tab_hist, tab_lgpd = st.tabs([
        "📢  Campanhas", "🎂  Aniversariantes",
        "📅  Histórico de Contatos", "🔒  LGPD — Opt-out",
    ])

    # ── Aba Aniversariantes ───────────────────────────────────────────────────
    with tab_aniv:
        st.markdown('<div class="section-title">🎂 Aniversariantes</div>', unsafe_allow_html=True)

        client_map_aniv = st.session_state.client_map or {}

        _hoje = date.today()
        _mes_atual = _hoje.month
        _MESES = ["", "Janeiro","Fevereiro","Março","Abril","Maio","Junho",
                  "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]

        # ── Análise visual: distribuição anual ───────────────────────────────
        if client_map_aniv:
            _dist = [0] * 13
            for info in client_map_aniv.values():
                _m = info.get("aniversario")
                if not _m:
                    try: _m = int(info.get("nascimento","").split("/")[1])
                    except Exception: pass
                if _m and 1 <= _m <= 12:
                    _dist[_m] += 1
            _fig_aniv = go.Figure(go.Bar(
                x=_MESES[1:], y=_dist[1:],
                marker_color=["#E84300" if i+1 == _mes_atual else "#F5A07A" for i in range(12)],
                text=[str(v) if v > 0 else "" for v in _dist[1:]],
                textposition="outside",
            ))
            _fig_aniv.update_layout(
                title=dict(text="Aniversariantes por mês", font=dict(color=_TEXT, size=13)),
                xaxis=dict(color=_MUTED), yaxis=dict(color=_MUTED, gridcolor=_GRID),
                **_base_layout(200),
            )
            st.plotly_chart(_fig_aniv, width="stretch", key="chart_aniversariantes")

        # Filtro de período
        _ac1, _ac2, _ac3 = st.columns([1.5, 1.5, 3])
        with _ac1:
            _mes_sel = st.selectbox("Mês", options=list(range(1, 13)),
                format_func=lambda m: _MESES[m], index=_mes_atual - 1, key="aniv_mes")
        with _ac2:
            _ddd_aniv = st.text_input("DDD padrão", value="19", max_chars=3, key="aniv_ddd")
        with _ac3:
            _tmpl_aniv = st.text_area(
                "Template de mensagem",
                value="Oi {nome}, hoje é seu dia especial! 🎉 Passe na Chilli Beans e ganhe um mimo de aniversário.",
                height=68, key="aniv_tmpl",
            )
            st.caption("Variável disponível: `{nome}`")

        # Monta lista de aniversariantes do mês
        _aniv_rows = []
        for cod, info in client_map_aniv.items():
            mes_nasc = info.get("aniversario")          # int 1-12 ou None
            nasc_str = info.get("nascimento", "")       # "DD/MM/AAAA" ou ""
            if mes_nasc is None and nasc_str:
                try:
                    mes_nasc = int(nasc_str.split("/")[1])
                except Exception:
                    pass
            if mes_nasc != _mes_sel:
                continue
            nome  = info.get("nome", f"Cliente #{cod}")
            fone  = info.get("fone", "")
            # Dia do aniversário
            dia = None
            if nasc_str:
                try: dia = int(nasc_str.split("/")[0])
                except Exception: pass
            # Verifica se é hoje
            eh_hoje = (dia == _hoje.day) if dia and _mes_sel == _mes_atual else False
            # Gera link WhatsApp
            _wa = ""
            if fone:
                _nome_fmt = nome.split()[0] if nome else "cliente"
                _msg_aniv = _tmpl_aniv.replace("{nome}", _nome_fmt)
                _wa = make_whatsapp_link(fone, _msg_aniv, _ddd_aniv)
            _aniv_rows.append({
                "_eh_hoje": eh_hoje,
                "_dia": dia or 0,
                "🎂": "🌟 HOJE" if eh_hoje else "",
                "Nome":    nome,
                "Dia":     f"{dia:02d}/{_MESES[_mes_sel]}" if dia else _MESES[_mes_sel],
                "Telefone": fone or "—",
                "📱 WhatsApp": _wa,
            })

        # Ordena: hoje primeiro, depois por dia
        _aniv_rows.sort(key=lambda r: (0 if r["_eh_hoje"] else 1, r["_dia"]))

        # KPIs
        _n_total = len(_aniv_rows)
        _n_hoje  = sum(1 for r in _aniv_rows if r["_eh_hoje"])
        _n_fone  = sum(1 for r in _aniv_rows if r["Telefone"] != "—")
        _k1, _k2, _k3 = st.columns(3)
        _k1.metric(f"Aniversariantes em {_MESES[_mes_sel]}", f"{_n_total}")
        _k2.metric("Aniversariantes hoje 🌟", f"{_n_hoje}")
        _k3.metric("Com telefone (WhatsApp)", f"{_n_fone}")

        if not _aniv_rows:
            st.info(f"Nenhum cliente com aniversário em {_MESES[_mes_sel]}. "
                    "Importe o cadastro de clientes em ⚙️ Configurações.")
        else:
            # Remove colunas auxiliares para exibição
            _df_aniv = pd.DataFrame(_aniv_rows).drop(columns=["_eh_hoje", "_dia"])
            st.dataframe(
                _df_aniv, hide_index=True, width="stretch",
                height=min(600, 80 + len(_df_aniv) * 35),
                column_config={
                    "🎂":         st.column_config.TextColumn("", width="small"),
                    "Nome":       st.column_config.TextColumn("Nome"),
                    "Dia":        st.column_config.TextColumn("Dia"),
                    "Telefone":   st.column_config.TextColumn("Telefone"),
                    "📱 WhatsApp": st.column_config.LinkColumn("📱 WhatsApp", display_text="📱 Enviar"),
                },
            )
            # Exportar
            _df_exp_aniv = _df_aniv.drop(columns=["📱 WhatsApp"])
            st.download_button(
                f"📥 Exportar Aniversariantes — {_MESES[_mes_sel]}",
                data=to_excel({f"Aniversariantes {_MESES[_mes_sel]}": _df_exp_aniv}),
                file_name=f"aniversariantes_{_mes_sel:02d}_{date.today().year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_aniv",
            )

    # ── Aba Campanhas ─────────────────────────────────────────────────────────
    with tab_camp:
        campaigns = st.session_state.campaigns or []

        # ── Formulário: Nova campanha ────────────────────────────────────────
        st.markdown("#### ➕ Nova Campanha")
        with st.form("form_nova_campanha", clear_on_submit=True):
            nome_camp = st.text_input(
                "Nome da Campanha *",
                placeholder="Ex: Reativação Inverno 2026",
            )
            objetivo = st.text_input(
                "Objetivo",
                placeholder="Ex: Reativar clientes sem compra há +12 meses",
            )
            template = st.text_area(
                "Mensagem Template *",
                value=DEFAULT_TEMPLATE,
                height=130,
                help="Escreva a mensagem que será enviada. Use as variáveis abaixo.",
            )
            st.caption(
                "💡 **Variáveis disponíveis:** "
                "`{nome}` (primeiro nome) · `{categoria}` (ex: óculos solar) · "
                "`{data}` (data da última compra) · `{dias}` (dias sem comprar)"
            )

            # Thresholds da campanha
            st.markdown("**Janela de inatividade (meses por categoria)**")
            _tc1, _tc2, _tc3, _tc4, _tc5 = st.columns(5)
            with _tc1:
                _new_lv = st.number_input("LV — Armação Grau",    min_value=1, max_value=60, value=12, key="new_camp_lv")
            with _tc2:
                _new_oc = st.number_input("OC — Óculos Solar",    min_value=1, max_value=60, value=12, key="new_camp_oc")
            with _tc3:
                _new_ml = st.number_input("ML — Armação Multi",   min_value=1, max_value=60, value=12, key="new_camp_ml")
            with _tc4:
                _new_le = st.number_input("LE — Lentes",          min_value=1, max_value=36, value=6,  key="new_camp_le")
            with _tc5:
                _new_lc = st.number_input("LC — L. de Contato",   min_value=1, max_value=12, value=3,  key="new_camp_lc")

            # Validade (opcional)
            _new_expiry_toggle = st.checkbox("Definir data de validade para esta campanha", value=False)
            _new_expiry = None
            if _new_expiry_toggle:
                _new_expiry = st.date_input("Válida até", value=date.today() + timedelta(days=90), key="new_camp_expiry")

            # Filtros de audiência
            st.markdown("**🎯 Filtros de Audiência** *(opcional — deixe zerado/vazio para incluir todos os clientes)*")
            _fa_col1, _fa_col2 = st.columns(2)
            _MES_OPTS = {0: "Todos", 1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
                         5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
                         9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
            with _fa_col1:
                _new_aniv_mes = st.selectbox(
                    "Mês de aniversário",
                    options=list(_MES_OPTS.keys()),
                    format_func=lambda m: _MES_OPTS[m],
                    key="new_camp_aniv_mes",
                )
                _new_aniv_sem = st.number_input(
                    "Semana do aniversário (1–53, 0 = todos)",
                    min_value=0, max_value=53, value=0, key="new_camp_aniv_sem",
                )
            with _fa_col2:
                _new_uc_ini = st.date_input("Última compra — de",     value=None, key="new_camp_uc_ini")
                _new_uc_fim = st.date_input("Última compra — até",    value=None, key="new_camp_uc_fim")
                _new_nasc_ini = st.date_input("Data de nascimento — de",  value=None, key="new_camp_nasc_ini")
                _new_nasc_fim = st.date_input("Data de nascimento — até", value=None, key="new_camp_nasc_fim")

            # Preview em tempo real (usa valores fixos de exemplo)
            if template:
                prev = format_message(template, "Maria Silva", "Óculos Solar", "10/10/2024", 220)
                st.info(f"**Preview de exemplo:**\n\n{prev}")

            submitted = st.form_submit_button("💾 Salvar Campanha", type="primary")

        if submitted:
            if not nome_camp.strip():
                st.error("O nome da campanha é obrigatório.")
            elif not template.strip():
                st.error("O template da mensagem é obrigatório.")
            elif any(c["nome"] == nome_camp.strip() for c in campaigns):
                st.error(f"Já existe uma campanha com o nome '{nome_camp.strip()}'.")
            else:
                _expiry_str = str(_new_expiry) if _new_expiry_toggle and _new_expiry else None
                campaigns.append({
                    "nome":       nome_camp.strip(),
                    "objetivo":   objetivo.strip(),
                    "template":   template.strip(),
                    "thresholds": {
                        "LV": int(_new_lv), "OC": int(_new_oc), "ML": int(_new_ml),
                        "LE": int(_new_le), "LC": int(_new_lc),
                    },
                    "expiry":  _expiry_str,
                    "filtros": {
                        "aniversario_mes":    int(_new_aniv_mes) if _new_aniv_mes else 0,
                        "aniversario_semana": int(_new_aniv_sem) if _new_aniv_sem else 0,
                        "ultima_compra_ini":  str(_new_uc_ini)  if _new_uc_ini  else None,
                        "ultima_compra_fim":  str(_new_uc_fim)  if _new_uc_fim  else None,
                        "nascimento_ini":     str(_new_nasc_ini) if _new_nasc_ini else None,
                        "nascimento_fim":     str(_new_nasc_fim) if _new_nasc_fim else None,
                    },
                })
                save_campaigns(campaigns)
                st.session_state.campaigns = campaigns
                st.success(f"✅ Campanha '{nome_camp.strip()}' criada!")
                st.rerun()

        # ── Campanhas existentes ─────────────────────────────────────────────
        if campaigns:
            st.divider()
            st.markdown("#### 📢 Campanhas cadastradas")
            _today_mkt = str(date.today())
            for i, camp in enumerate(campaigns):
                _thresh = camp.get("thresholds", {"LV": 12, "OC": 12, "ML": 12})
                _is_expired = bool(camp.get("expiry") and camp["expiry"] < _today_mkt)
                _expiry_label   = f"  •  válida até {camp['expiry']}" if camp.get("expiry") else ""
                _inactive_label = "  🔴 inativa" if _is_expired else ""
                with st.expander(f"📢  {camp['nome']}{_expiry_label}{_inactive_label}", expanded=False):
                    _edit_key = f"editing_camp_{i}"
                    if not st.session_state.get(_edit_key, False):
                        # ── Modo visualização ────────────────────────────────
                        if _is_expired:
                            st.warning("⚠️ Esta campanha está **inativa** (vencida). Edite a validade para reativá-la.")
                        if camp.get("objetivo"):
                            st.write(f"**Objetivo:** {camp['objetivo']}")
                        _tc = camp.get("thresholds", {})
                        st.caption(
                            f"Janela: LV {_tc.get('LV', 12)}m · "
                            f"OC {_tc.get('OC', 12)}m · "
                            f"ML {_tc.get('ML', 12)}m · "
                            f"LE {_tc.get('LE', 6)}m · "
                            f"LC {_tc.get('LC', 3)}m"
                        )
                        # Mostra filtros ativos
                        _fc = camp.get("filtros") or {}
                        _fc_active = {k: v for k, v in _fc.items() if v}
                        if _fc_active:
                            _MES_SHORT = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",
                                          7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
                            _fc_parts = []
                            if _fc_active.get("aniversario_mes"):
                                _fc_parts.append(f"Aniv. {_MES_SHORT.get(int(_fc_active['aniversario_mes']), '?')}")
                            if _fc_active.get("aniversario_semana"):
                                _fc_parts.append(f"Semana aniv. #{_fc_active['aniversario_semana']}")
                            if _fc_active.get("ultima_compra_ini") or _fc_active.get("ultima_compra_fim"):
                                _fc_parts.append(f"Ult. compra {_fc_active.get('ultima_compra_ini','?')}→{_fc_active.get('ultima_compra_fim','?')}")
                            if _fc_active.get("nascimento_ini") or _fc_active.get("nascimento_fim"):
                                _fc_parts.append(f"Nasc. {_fc_active.get('nascimento_ini','?')}→{_fc_active.get('nascimento_fim','?')}")
                            st.caption("🎯 Filtros: " + " · ".join(_fc_parts))
                        else:
                            st.caption("🎯 Filtros: todos os clientes")
                        st.write("**Template:**")
                        st.text_area(
                            "template_view", value=camp["template"],
                            height=100, disabled=True,
                            label_visibility="collapsed",
                            key=f"view_camp_{i}",
                        )
                        prev_ex = format_message(
                            camp["template"], "João Pedro",
                            "Armações de Grau", "15/08/2024", 285,
                        )
                        st.info(f"**Preview de exemplo:**\n\n{prev_ex}")

                        _bce1, _bce2 = st.columns(2)
                        with _bce1:
                            if st.button("✏️ Editar", key=f"edit_camp_btn_{i}"):
                                st.session_state[_edit_key] = True
                                st.rerun()
                        with _bce2:
                            if st.button("🗑 Excluir", key=f"del_camp_{i}"):
                                campaigns.pop(i)
                                save_campaigns(campaigns)
                                st.session_state.campaigns = campaigns
                                st.warning("Campanha removida.")
                                st.rerun()
                    else:
                        # ── Modo edição ──────────────────────────────────────
                        st.markdown("**Editando campanha**")
                        with st.form(f"form_edit_camp_{i}"):
                            _e_nome = st.text_input("Nome *", value=camp["nome"])
                            _e_obj  = st.text_input("Objetivo", value=camp.get("objetivo", ""))
                            _e_tmpl = st.text_area("Template *", value=camp["template"], height=130)
                            st.caption(
                                "💡 Variáveis: `{nome}` · `{categoria}` · `{data}` · `{dias}`"
                            )
                            if _e_tmpl:
                                st.info(f"**Preview:** {format_message(_e_tmpl, 'Ana', 'Óculos Solar', '10/10/2024', 200)}")
                            st.markdown("**Janela de inatividade (meses)**")
                            _ec1, _ec2, _ec3, _ec4, _ec5 = st.columns(5)
                            with _ec1:
                                _e_lv = st.number_input("LV", min_value=1, max_value=60,
                                                         value=int(_thresh.get("LV", 12)))
                            with _ec2:
                                _e_oc = st.number_input("OC", min_value=1, max_value=60,
                                                         value=int(_thresh.get("OC", 12)))
                            with _ec3:
                                _e_ml = st.number_input("ML", min_value=1, max_value=60,
                                                         value=int(_thresh.get("ML", 12)))
                            with _ec4:
                                _e_le = st.number_input("LE", min_value=1, max_value=36,
                                                         value=int(_thresh.get("LE", 6)))
                            with _ec5:
                                _e_lc = st.number_input("LC", min_value=1, max_value=12,
                                                         value=int(_thresh.get("LC", 3)))
                            _e_exp_toggle = st.checkbox(
                                "Definir validade",
                                value=bool(camp.get("expiry")),
                            )
                            _e_expiry_val = None
                            if _e_exp_toggle:
                                _e_exp_default = date.today() + timedelta(days=90)
                                if camp.get("expiry"):
                                    try:
                                        _e_exp_default = date.fromisoformat(camp["expiry"])
                                    except Exception:
                                        pass
                                _e_expiry_val = st.date_input("Válida até", value=_e_exp_default)

                            # Filtros de audiência (edição)
                            st.markdown("**🎯 Filtros de Audiência**")
                            _fc_cur = camp.get("filtros") or {}
                            _eMES_OPTS = {0: "Todos", 1: "Janeiro", 2: "Fevereiro", 3: "Março",
                                          4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho",
                                          8: "Agosto", 9: "Setembro", 10: "Outubro",
                                          11: "Novembro", 12: "Dezembro"}
                            _efc1, _efc2 = st.columns(2)
                            with _efc1:
                                _e_aniv_mes = st.selectbox(
                                    "Mês de aniversário",
                                    options=list(_eMES_OPTS.keys()),
                                    format_func=lambda m: _eMES_OPTS[m],
                                    index=int(_fc_cur.get("aniversario_mes") or 0),
                                )
                                _e_aniv_sem = st.number_input(
                                    "Semana do aniversário (0 = todos)",
                                    min_value=0, max_value=53,
                                    value=int(_fc_cur.get("aniversario_semana") or 0),
                                )
                            with _efc2:
                                _e_uc_ini_def = None
                                _e_uc_fim_def = None
                                _e_nasc_ini_def = None
                                _e_nasc_fim_def = None
                                try:
                                    if _fc_cur.get("ultima_compra_ini"):
                                        _e_uc_ini_def = date.fromisoformat(_fc_cur["ultima_compra_ini"])
                                    if _fc_cur.get("ultima_compra_fim"):
                                        _e_uc_fim_def = date.fromisoformat(_fc_cur["ultima_compra_fim"])
                                    if _fc_cur.get("nascimento_ini"):
                                        _e_nasc_ini_def = date.fromisoformat(_fc_cur["nascimento_ini"])
                                    if _fc_cur.get("nascimento_fim"):
                                        _e_nasc_fim_def = date.fromisoformat(_fc_cur["nascimento_fim"])
                                except Exception:
                                    pass
                                _e_uc_ini  = st.date_input("Última compra — de",     value=_e_uc_ini_def)
                                _e_uc_fim  = st.date_input("Última compra — até",    value=_e_uc_fim_def)
                                _e_nasc_ini = st.date_input("Nascimento — de",       value=_e_nasc_ini_def)
                                _e_nasc_fim = st.date_input("Nascimento — até",      value=_e_nasc_fim_def)

                            _esave, _ecancel = st.columns(2)
                            with _esave:
                                _saved_edit = st.form_submit_button("💾 Salvar alterações", type="primary")
                            with _ecancel:
                                _cancel_edit = st.form_submit_button("✖ Cancelar")

                        if _saved_edit:
                            if _e_nome.strip() and _e_tmpl.strip():
                                campaigns[i] = {
                                    "nome":       _e_nome.strip(),
                                    "objetivo":   _e_obj.strip(),
                                    "template":   _e_tmpl.strip(),
                                    "thresholds": {
                                        "LV": int(_e_lv), "OC": int(_e_oc), "ML": int(_e_ml),
                                        "LE": int(_e_le), "LC": int(_e_lc),
                                    },
                                    "expiry":  str(_e_expiry_val) if _e_exp_toggle and _e_expiry_val else None,
                                    "filtros": {
                                        "aniversario_mes":    int(_e_aniv_mes) if _e_aniv_mes else 0,
                                        "aniversario_semana": int(_e_aniv_sem) if _e_aniv_sem else 0,
                                        "ultima_compra_ini":  str(_e_uc_ini)  if _e_uc_ini  else None,
                                        "ultima_compra_fim":  str(_e_uc_fim)  if _e_uc_fim  else None,
                                        "nascimento_ini":     str(_e_nasc_ini) if _e_nasc_ini else None,
                                        "nascimento_fim":     str(_e_nasc_fim) if _e_nasc_fim else None,
                                    },
                                }
                                save_campaigns(campaigns)
                                st.session_state.campaigns = campaigns
                                st.session_state[_edit_key] = False
                                st.success("✅ Campanha atualizada!")
                                st.rerun()
                            else:
                                st.error("Nome e template são obrigatórios.")
                        if _cancel_edit:
                            st.session_state[_edit_key] = False
                            st.rerun()
        else:
            st.info(
                "Nenhuma campanha cadastrada ainda.  \n"
                "Crie sua primeira campanha no formulário acima — "
                "ela ficará disponível para seleção na aba **🎯 Campanhas Ativas**."
            )

    # ── Aba Histórico de Contatos ─────────────────────────────────────────────
    with tab_hist:
        st.markdown("#### 📅 Histórico de Contatos")
        hist = db.list_contacts(limit=500)
        if not hist:
            st.info(
                "Nenhum contato registrado ainda.  \n"
                "Os contatos aparecem aqui quando você marca **✅ Contatado** "
                "na aba Campanhas Ativas e clica **Salvar**."
            )
        else:
            df_hist = pd.DataFrame(hist)
            _n_total = len(df_hist)
            _n_mes   = sum(
                1 for _, r in df_hist.iterrows()
                if r["Data/Hora"][3:10] == datetime.now().strftime("%m/%Y")
            )
            h1, h2 = st.columns(2)
            h1.metric("Total de contatos registrados", _n_total)
            h2.metric("Contatos este mês",             _n_mes)
            st.divider()
            st.dataframe(
                df_hist,
                width="stretch",
                hide_index=True,
                height=min(500, 80 + _n_total * 35),
            )
            st.download_button(
                "📥 Exportar Excel",
                data=to_excel({"Histórico de Contatos": df_hist}),
                file_name=f"historico_contatos_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    # ── Aba LGPD Opt-out ──────────────────────────────────────────────────────
    with tab_lgpd:
        from modules.lgpd import load_optout, set_optout, remove_optout, optout_count
        st.markdown("#### 🔒 LGPD — Opt-out de Marketing")
        st.caption(
            "Clientes que solicitaram sair das comunicações de marketing. "
            "**Prazo legal: 24h** para remover de todas as listas após solicitação. "
            "Clientes em opt-out **não** recebem e-mails da régua de pós-venda nem campanhas."
        )

        _optouts = load_optout()
        _lgpd_c1, _lgpd_c2 = st.columns([2, 3])
        with _lgpd_c1:
            st.metric("Clientes em opt-out", optout_count())
        with _lgpd_c2:
            if _optouts:
                st.warning(
                    f"⚠️ {optout_count()} cliente(s) em opt-out. "
                    "Remova das campanhas antes do próximo disparo."
                )

        # Registrar novo opt-out
        with st.expander("➕ Registrar opt-out de cliente"):
            _oo_cod  = st.text_input("Código do cliente", key="lgpd_cod")
            _oo_mot  = st.text_input("Motivo (opcional)", key="lgpd_motivo")
            _cmap_oo = st.session_state.client_map or {}
            _oo_nome = _cmap_oo.get(_oo_cod, {}).get("nome", "") if _oo_cod else ""
            if _oo_nome:
                st.caption(f"Cliente encontrado: **{_oo_nome}**")
            if st.button("🔒 Registrar opt-out", key="lgpd_add", type="primary"):
                if _oo_cod:
                    set_optout(_oo_cod, _oo_nome, _oo_mot)
                    st.success(f"✅ {_oo_nome or _oo_cod} registrado em opt-out. Remova das listas em até 24h.")
                    st.rerun()
                else:
                    st.warning("Informe o código do cliente.")

        # Lista atual de opt-outs
        if _optouts:
            _oo_rows = [
                {"Código": k, "Nome": v.get("nome",""), "Data": v.get("data",""),
                 "Motivo": v.get("motivo","")}
                for k, v in _optouts.items()
            ]
            _df_oo = pd.DataFrame(_oo_rows)
            _edited_oo = st.data_editor(
                _df_oo, hide_index=True, width="stretch",
                num_rows="fixed",
                column_config={
                    "Código": st.column_config.TextColumn("Código", disabled=True),
                    "Nome":   st.column_config.TextColumn("Nome",   disabled=True),
                    "Data":   st.column_config.TextColumn("Data",   disabled=True),
                    "Motivo": st.column_config.TextColumn("Motivo", disabled=True),
                },
            )
            if st.button("🔓 Remover opt-out selecionado (re-consentiu)", key="lgpd_remove"):
                st.info("Selecione o cliente abaixo e confirme.")
            _oo_rm = st.text_input("Código para remover opt-out", key="lgpd_rm_cod")
            if st.button("Confirmar remoção", key="lgpd_rm_confirm"):
                if _oo_rm in _optouts:
                    remove_optout(_oo_rm)
                    st.success(f"✅ Opt-out de {_oo_rm} removido.")
                    st.rerun()
        else:
            st.success("Nenhum cliente em opt-out no momento.")


def page_bom_dia():
    """Tela de Bom Dia — fila diária priorizada para o vendedor."""
    import locale
    _hoje   = date.today()
    _MESES  = ["","Janeiro","Fevereiro","Março","Abril","Maio","Junho",
               "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]
    _DIAS_S = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
    _dia_semana = _DIAS_S[_hoje.weekday()]

    # Resolve o nome de saudação: nome_social > primeiro nome > "Pepper"
    from modules.user_profile import get_profile as _get_profile_bd
    _auth_bd      = st.session_state.get("auth_user", {})
    _prof_bd      = _get_profile_bd(_auth_bd.get("login","")) if _auth_bd.get("login") else {}
    _nome_social  = (_prof_bd.get("nome_social") or "").strip()
    _nome_completo_bd = (_prof_bd.get("nome_completo") or _auth_bd.get("nome","")).strip()
    _primeiro_nome = _nome_completo_bd.split()[0] if _nome_completo_bd else ""
    _saudacao = _nome_social or _primeiro_nome or "Pepper"

    st.markdown(
        f'<div class="cb-title">🌄 Bom Dia, {_saudacao}!</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="cb-sub">{_dia_semana}, {_hoje.day} de {_MESES[_hoje.month]} de {_hoje.year}</div>',
        unsafe_allow_html=True,
    )

    _cmap    = st.session_state.client_map or {}
    _vend_nome_bd = _auth_bd.get("nome", "")
    _vend_login_bd = _auth_bd.get("login", "")
    _dret  = st.session_state.df_retorno
    _df_v  = st.session_state.df_vendas
    _est_v = cfg.get("estoque_virtual", {})
    _est_m = cfg.get("estoque_minimo",  {})
    _est_i = cfg.get("estoque_ideal",   {})
    _ddd   = cfg.get("ddd_padrao", "19") or "19"

    # ── Constrói fila de ações ────────────────────────────────────────────────
    # Cada ação: {prioridade (0=urgente, 1=hoje, 2=semana), tipo, nome, subtitulo,
    #             wa (link), id (chave para checkbox)}
    _acoes = []
    _feitos = st.session_state.get("_bom_dia_feitos", set())

    # 1. Estoque abaixo do mínimo (sempre urgente)
    for _c in ("LV", "OC", "ML"):
        _at = int(_est_v.get(_c, 0))
        _mn = int(_est_m.get(_c, 0))
        _id_i = cfg.get("estoque_ideal", {}).get(_c, 0)
        if _mn > 0 and _at < _mn:
            _acoes.append({
                "prioridade": 0, "grupo": "🔴 URGENTE",
                "tipo": "📦", "nome": CAT_NAMES.get(_c, _c),
                "subtitulo": f"Estoque crítico: {_at} pç (mínimo: {_mn}) — faça o pedido hoje",
                "wa": "", "id": f"estoque_{_c}",
            })

    # 2. Aniversariantes de hoje
    for _cod, _info in _cmap.items():
        _m = _info.get("aniversario")
        _nasc = _info.get("nascimento", "")
        _dia_n = None
        if _nasc:
            try: _dia_n = int(_nasc.split("/")[0])
            except Exception: pass
        if _m == _hoje.month and (_dia_n is None or _dia_n == _hoje.day):
            _fone = _info.get("fone","") or ""
            _nome = (_info.get("nome") or "").strip() or f"Cliente #{_cod}"
            _msg  = f"Oi {_nome.split()[0]}, hoje é seu dia especial! 🎉 Passe na Chilli Beans e ganhe um mimo de aniversário."
            _wa   = make_whatsapp_link(_fone, _msg, _ddd) if _fone else ""
            _is_hoje = _dia_n == _hoje.day if _dia_n else False
            _acoes.append({
                "prioridade": 0 if _is_hoje else 1,
                "grupo": "🔴 URGENTE" if _is_hoje else "🟡 HOJE",
                "tipo": "🎂", "nome": _nome,
                "subtitulo": f"Aniversário {'hoje' if _is_hoje else 'este mês'} — mensagem de parabéns",
                "wa": _wa, "id": f"aniv_{_cod}",
            })

    # 3. Recalls urgentes (≤7 dias para próxima troca prevista)
    if _dret is not None and not _dret.empty:
        _CICLOS = {"LV":730,"OC":548,"ML":730,"LE":365,"LC":30,"AC":180}
        _hoje_ts = pd.Timestamp(_hoje)
        for _, _rrow in _dret.iterrows():
            _cat    = str(_rrow.get("categoria",""))
            _ciclo  = _CICLOS.get(_cat, 365)
            _ult    = pd.to_datetime(_rrow.get("ultima_compra"), errors="coerce")
            if pd.isna(_ult): continue
            _proxima = _ult + pd.Timedelta(days=_ciclo)
            _dr = (_proxima - _hoje_ts).days
            if _dr < 0 or _dr > 30: continue
            _cod  = str(_rrow.get("codigo_cliente",""))
            _info = _cmap.get(_cod, {})
            _nome = (_info.get("nome") or "").strip() or f"Cliente #{_cod}"
            _fone = _info.get("fone","") or ""
            _cat_lbl = CAT_NAMES.get(_cat, _cat)
            _msg  = (f"Oi {_nome.split()[0]}! Sua {_cat_lbl.lower()} está chegando no prazo de troca. "
                     f"Que tal agendar uma visita?")
            _wa   = make_whatsapp_link(_fone, _msg, _ddd) if _fone else ""
            _pri  = 0 if _dr <= 7 else (1 if _dr <= 14 else 2)
            _grp  = "🔴 URGENTE" if _dr <= 7 else ("🟡 HOJE" if _dr <= 14 else "🟢 ESTA SEMANA")
            _acoes.append({
                "prioridade": _pri, "grupo": _grp,
                "tipo": "🔮", "nome": _nome,
                "subtitulo": f"Troca prevista em {_dr} dia(s) — {_cat_lbl}",
                "wa": _wa, "id": f"recall_{_cod}_{_cat}",
            })

    # 4. Janela J1 (12 meses) — clientes que entraram recentemente
    if _dret is not None and not _dret.empty:
        _hoje_ts = pd.Timestamp(_hoje)
        for _, _rrow in _dret.iterrows():
            _cat = str(_rrow.get("categoria",""))
            if _cat not in ("LV","OC","ML","LE"): continue
            _ult  = pd.to_datetime(_rrow.get("ultima_compra"), errors="coerce")
            if pd.isna(_ult): continue
            _dias = (_hoje_ts - _ult).days
            if not (360 <= _dias <= 420): continue  # janela J1 (12±1 mês)
            _cod  = str(_rrow.get("codigo_cliente",""))
            if f"j1_{_cod}" in [a["id"] for a in _acoes]: continue
            _info = _cmap.get(_cod, {})
            _nome = (_info.get("nome") or "").strip() or f"Cliente #{_cod}"
            _fone = _info.get("fone","") or ""
            _msg  = (f"Oi {_nome.split()[0]}! Já faz um ano desde sua última visita à Chilli Beans. "
                     f"Como está sua saúde visual?")
            _wa   = make_whatsapp_link(_fone, _msg, _ddd) if _fone else ""
            _acoes.append({
                "prioridade": 1, "grupo": "🟡 HOJE",
                "tipo": "⏱️", "nome": _nome,
                "subtitulo": f"Janela J1 — {_dias} dias sem comprar. Contato de saúde visual.",
                "wa": _wa, "id": f"j1_{_cod}",
            })

    # 5. Fila de e-mail pendente
    try:
        from modules.email_queue import queue_size as _qs
        _n_fila = _qs()
        if _n_fila > 0:
            _acoes.append({
                "prioridade": 1, "grupo": "🟡 HOJE",
                "tipo": "📧", "nome": f"{_n_fila} e-mail(s) na fila",
                "subtitulo": "Serão enviados automaticamente às 02h — nenhuma ação necessária",
                "wa": "", "id": "email_fila",
            })
    except Exception:
        pass

    # ── KPIs de resumo ────────────────────────────────────────────────────────
    _n_urgente = sum(1 for a in _acoes if a["prioridade"] == 0 and a["id"] not in _feitos)
    _n_hoje    = sum(1 for a in _acoes if a["prioridade"] == 1 and a["id"] not in _feitos)
    _n_semana  = sum(1 for a in _acoes if a["prioridade"] == 2 and a["id"] not in _feitos)
    _n_feitos_hoje = len(_feitos)

    _k1, _k2, _k3, _k4 = st.columns(4)
    _k1.metric("🔴 Urgente", _n_urgente)
    _k2.metric("🟡 Hoje",    _n_hoje)
    _k3.metric("🟢 Semana",  _n_semana)
    _k4.metric("✅ Feitos",  _n_feitos_hoje)

    # ── Card de Meta do Mês ───────────────────────────────────────────────────
    try:
        from modules.metas import pace as _pace_fn
        _meta_val = float(cfg.get("meta_mensal_valor") or 0)
        if _meta_val > 0 and _df_v is not None and not _df_v.empty:
            _ini_mes  = _hoje.replace(day=1)
            _df_mes   = _df_v[
                (pd.to_datetime(_df_v["data"], errors="coerce") >= pd.Timestamp(_ini_mes)) &
                (pd.to_datetime(_df_v["data"], errors="coerce") <= pd.Timestamp(_hoje))
            ] if "data" in _df_v.columns else _df_v
            _realizado = float(_df_mes["valor_liquido"].sum()) if "valor_liquido" in _df_mes.columns else 0.0
            _p = _pace_fn(_meta_val, _realizado, today=_hoje)
            _farol = _p["farol"]
            _pct   = f"{_p['pct']:.0%}"
            _falta = _p["falta"]
            _rnec  = _p.get("ritmo_necessario") or 0
            _proj  = _p.get("projecao")
            _label = _p.get("status_label","")
            st.markdown(
                f'<div style="background:#FDF8F5;border-radius:12px;padding:12px 16px;'
                f'margin:12px 0;display:flex;align-items:center;gap:16px;'
                f'border-left:4px solid #E84300;">'
                f'<div style="font-size:1.8rem;">{_farol}</div>'
                f'<div style="flex:1;">'
                f'<div style="font-size:.72rem;color:#9E8E7E;font-weight:600;text-transform:uppercase;'
                f'letter-spacing:.05em;">Meta do Mês</div>'
                f'<div style="font-size:1rem;font-weight:700;color:#1C1816;">'
                f'R$ {_realizado:,.0f} / R$ {_meta_val:,.0f} &nbsp;·&nbsp; {_pct} &nbsp;·&nbsp; {_label}'
                f'</div>'
                + (f'<div style="font-size:.75rem;color:#7A6A5A;">Falta R$ {_falta:,.0f} · '
                   f'Ritmo necessário: R$ {_rnec:,.0f}/dia'
                   + (f' · Projeção: R$ {_proj:,.0f}' if _proj else '')
                   + '</div>' if _falta > 0 else
                   '<div style="font-size:.75rem;color:#059669;">🎉 Meta do mês batida!</div>')
                + '</div></div>',
                unsafe_allow_html=True,
            )
    except Exception:
        pass

    if not _acoes:
        st.success(
            "✅ **Nada urgente hoje!** Sem aniversários, recalls ou estoque crítico.  \n"
            "Carregue o histórico de clientes em **🎯 Campanhas Ativas** para ver janelas de contato."
        )
        return

    if _dret is None:
        st.info(
            "💡 Para ver recalls e janelas de contato, carregue o histórico em "
            "**🎯 Campanhas Ativas → Buscar histórico (48 meses)**."
        )

    st.divider()

    # ── Renderiza fila por grupo ──────────────────────────────────────────────
    _acoes_ord  = sorted(_acoes, key=lambda a: (a["prioridade"], a["nome"]))
    _grupo_atual = None
    for _a in _acoes_ord:
        if _a["id"] in _feitos:
            continue   # oculta os feitos

        if _a["grupo"] != _grupo_atual:
            _grupo_atual = _a["grupo"]
            st.markdown(f"### {_grupo_atual}")

        _col_txt, _col_wa, _col_ok = st.columns([5, 1, 1])
        with _col_txt:
            st.markdown(
                f"**{_a['tipo']} {_a['nome']}**  \n"
                f"<span style='font-size:.82rem;color:#7A6A5A;'>{_a['subtitulo']}</span>",
                unsafe_allow_html=True,
            )
        with _col_wa:
            if _a["wa"]:
                st.link_button("📱", _a["wa"], help="Abrir WhatsApp")
            else:
                st.write("")
        with _col_ok:
            if st.button("✅", key=f"done_{_a['id']}", help="Marcar como feito"):
                _feitos.add(_a["id"])
                st.session_state["_bom_dia_feitos"] = _feitos
                st.rerun()

    # Botão para ver os feitos
    if _feitos:
        with st.expander(f"Ver {len(_feitos)} item(s) marcado(s) como feito"):
            for _a in _acoes_ord:
                if _a["id"] in _feitos:
                    st.markdown(
                        f"~~{_a['tipo']} {_a['nome']} — {_a['subtitulo']}~~",
                        unsafe_allow_html=True,
                    )
            if st.button("↩️ Limpar feitos", key="bom_dia_limpar"):
                st.session_state["_bom_dia_feitos"] = set()
                st.rerun()

    # ── R4 — Registrar visita + painel do funil ───────────────────────────────
    st.divider()
    from modules.funil import (
        add_visita, get_visitas_hoje, resumo_funil,
        RESULTADOS, RESULTADO_ICONS,
    )
    _visitas_hoje = get_visitas_hoje(_vend_login_bd)
    _resumo_hoje  = resumo_funil(
        dt_ini=date.today().strftime("%d/%m/%Y"),
        dt_fim=date.today().strftime("%d/%m/%Y"),
        vendedor_login=_vend_login_bd,
    )

    _bd_f1, _bd_f2 = st.columns([3, 2], gap="large")

    with _bd_f1:
        st.markdown("#### 🚪 Registrar visita")
        st.caption("Registre toda entrada na loja — comprou ou não. É isso que mede a conversão real.")
        with st.form("form_visita_rapida", clear_on_submit=True):
            _v_nome = st.text_input("Nome do visitante", placeholder="Opcional — deixe vazio se não quis se identificar")
            _vc1, _vc2 = st.columns(2)
            _v_cat = _vc1.selectbox(
                "Interesse", ["", "LV — Armação de Grau","OC — Óculos Solar",
                              "ML — Armação Multi","LE — Lentes","LC — L. Contato","AC — Acessórios"],
                index=0,
            )
            _v_res = _vc2.selectbox("Resultado", RESULTADOS)
            _v_nota = st.text_input("Observação rápida", placeholder="ex: gostou do modelo XY, retorna sáb")
            _v_sub  = st.form_submit_button("✅ Registrar visita", type="primary", width="stretch")

        if _v_sub:
            add_visita(
                visitante_nome  = _v_nome,
                categoria       = _v_cat.split(" — ")[0] if _v_cat else "",
                resultado       = _v_res,
                notas           = _v_nota,
                vendedor_login  = _vend_login_bd,
                vendedor_nome   = _vend_nome_bd,
            )
            st.success(f"✅ Visita registrada: **{_v_res}**")
            st.rerun()

    with _bd_f2:
        st.markdown("#### 📊 Funil de hoje")
        _fv1, _fv2, _fv3 = st.columns(3)
        _fv1.metric("Visitas",     _resumo_hoje["total"])
        _fv2.metric("Conversões",  _resumo_hoje["conversoes"])
        _fv3.metric("Taxa",        f"{_resumo_hoje['taxa_conversao']:.0f}%")

        if _visitas_hoje:
            for _vt in _visitas_hoje[:8]:
                _icon = RESULTADO_ICONS.get(_vt["resultado"], "•")
                _nome_v = _vt.get("visitante_nome") or "Anônimo"
                st.caption(f"{_icon} **{_nome_v}** — {_vt['resultado']} ({_vt['hora']})")
        else:
            st.caption("Nenhuma visita registrada hoje ainda.")


def page_cobertura():
    """Painel de Cobertura Territorial — gerente e acima."""
    from modules.manager_coverage import (
        manager_coverage_report, mortos_list,
    )
    from modules.client_map import load_clients

    st.markdown('<div class="cb-title">🗺️ Cobertura Territorial</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="cb-sub">Alcance por canal e praça — onde a base é atingível e onde há lacunas</div>',
        unsafe_allow_html=True,
    )

    _cmap = st.session_state.client_map or {}
    if not _cmap:
        st.info("Importe a base de clientes em ⚙️ Configurações → Clientes.")
        return

    _ddd = cfg.get("ddd_padrao", "") or ""
    _rep  = manager_coverage_report(_cmap, default_ddd=_ddd)

    # ── KPIs gerais ──────────────────────────────────────────────────────────
    _k1, _k2, _k3, _k4, _k5 = st.columns(5)
    _k1.metric("👥 Base total",         len(_cmap))
    _k2.metric("📱 Alcance WhatsApp",   f"{_rep['wa_alcance']} ({_rep['wa_alcance']/len(_cmap)*100:.0f}%)")
    _k3.metric("📧 Alcance E-mail",     f"{_rep['email_alcance']} ({_rep['email_alcance']/len(_cmap)*100:.0f}%)")
    _k4.metric("☠️ Sem canal",          _rep['mortos'])
    _k5.metric("📞 ROI enriq. fone",    f"{_rep['roi_total']} clie.")

    # ── Alerta SP concentração ────────────────────────────────────────────────
    if _rep.get("wa_top_uf"):
        _top_uf, _top_share = _rep["wa_top_uf"], _rep.get("wa_top_share", 0)
        if _top_share > 90:
            st.warning(
                f"⚠️ **{_top_share:.0f}% do alcance de WhatsApp está concentrado em {_top_uf}.** "
                "Captadores e vendedores de outras praças têm fila de WhatsApp essencialmente vazia. "
                "Ativar o **Canal E-mail** e/ou enriquecer telefones são as saídas."
            )

    st.divider()

    # ── Tabela por UF ─────────────────────────────────────────────────────────
    st.markdown("#### 📊 Alcance por UF")
    _STATUS_COR = {
        "WHATSAPP OK":          "🟢",
        "WHATSAPP CRÍTICO":     "🟡",
        "PURO-LOTE / SÓ E-MAIL": "🔵",
        "SEM CANAL":            "🔴",
    }
    _uf_rows = []
    for _uf_data in _rep.get("uf_ordenado", []):
        _st = _uf_data.get("status", "")
        _uf_rows.append({
            "":         _STATUS_COR.get(_st, ""),
            "UF":       _uf_data.get("uf", ""),
            "Total":    _uf_data.get("total", 0),
            "WA%":      f"{_uf_data.get('pct_wa', 0):.0f}%",
            "E-mail%":  f"{_uf_data.get('pct_email', 0):.0f}%",
            "Mortos":   _uf_data.get("mortos", 0),
            "Puro-lote":  "✓" if _uf_data.get("puro_lote") else "",
            "ROI fone": _uf_data.get("batch_sem_fone", 0),
            "Status":   _st,
        })
    if _uf_rows:
        st.dataframe(
            pd.DataFrame(_uf_rows), hide_index=True, width="stretch",
            column_config={
                "":        st.column_config.TextColumn("", width="small"),
                "WA%":     st.column_config.TextColumn("📱 WA%"),
                "E-mail%": st.column_config.TextColumn("📧 Email%"),
                "ROI fone":st.column_config.NumberColumn("ROI fone", help="Clientes sem telefone — cada um destrava 1 novo WA"),
            },
        )

    # ── Ranking de ROI de enriquecimento ─────────────────────────────────────
    if _rep.get("roi_ranking"):
        st.divider()
        st.markdown("#### 📈 Ranking de ROI — enriquecimento de telefone")
        st.caption("Praças ordenadas por número de clientes que ganhariam acesso ao WhatsApp após enriquecimento de telefone.")
        _roi_rows = [{"UF": r["uf"], "Clientes sem fone": r["batch_sem_fone"],
                      "% da praça": f"{r['pct_sem_fone']:.0f}%"} for r in _rep["roi_ranking"][:15]]
        st.dataframe(pd.DataFrame(_roi_rows), hide_index=True, width="stretch")

    # ── Lista de "mortos" (sem canal) para captador sanear ───────────────────
    _mortos = mortos_list(_cmap, default_ddd=_ddd)
    if _mortos:
        st.divider()
        with st.expander(f"☠️ {len(_mortos)} clientes sem nenhum canal de contato — exportar para captador sanear"):
            st.caption("Estes clientes não têm telefone válido nem e-mail — não recebem nenhuma campanha. "
                       "O captador deve buscar contato presencial ou atualizar o cadastro no Microvix.")
            _m_df = pd.DataFrame([
                {"Nome": m.get("nome",""), "Cidade": m.get("cidade","—"),
                 "UF": m.get("uf","—"), "Cód.": m.get("codigo","")}
                for m in _mortos
            ])
            st.dataframe(_m_df, hide_index=True, width="stretch")
            st.download_button(
                "📥 Exportar lista de mortos",
                data=to_excel({"Sem Canal": _m_df}),
                file_name=f"sem_canal_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_mortos",
            )

    # ── Legenda ───────────────────────────────────────────────────────────────
    with st.expander("ℹ️ Legenda dos status"):
        st.markdown("""
| Status | Significado |
|---|---|
| 🟢 WHATSAPP OK | ≥50% da praça tem WhatsApp normalizável |
| 🟡 WHATSAPP CRÍTICO | < 50% mas > 0% têm WhatsApp |
| 🔵 PURO-LOTE / SÓ E-MAIL | 100% dos clientes vieram do import de 15/05/2026 — WhatsApp ~0%; e-mail ~94% |
| 🔴 SEM CANAL | Praça sem WhatsApp nem e-mail válido |
""")


def page_change_password():
    """Tela de troca de senha — acessível via dropdown da top bar."""
    from modules.auth import change_password, senha_padrao
    _au_cp = st.session_state.get("auth_user", {})
    _sp    = senha_padrao()

    st.markdown("### 🔑 Trocar senha")
    st.caption("Escolha uma senha pessoal com pelo menos 6 caracteres.")

    _cp1 = st.text_input("Nova senha", type="password", key="cp_nova")
    _cp2 = st.text_input("Confirmar nova senha", type="password", key="cp_conf")

    _bc1, _bc2 = st.columns([1, 3])
    with _bc1:
        if st.button("💾 Salvar", type="primary", width="stretch", key="btn_cp_save"):
            if len(_cp1) < 6:
                st.error("A senha deve ter pelo menos 6 caracteres.")
            elif _cp1 != _cp2:
                st.error("As senhas não coincidem.")
            elif _cp1 == _sp:
                st.error(f"A nova senha não pode ser igual à senha padrão `{_sp}`.")
            else:
                change_password(_au_cp["login"], _cp1)
                st.success("✅ Senha alterada com sucesso!")
                for k in ("cp_nova", "cp_conf"):
                    st.session_state.pop(k, None)
    with _bc2:
        if st.button("← Voltar", key="btn_cp_back", width="stretch"):
            st.session_state.pop("_show_senha", None)
            st.rerun()


def page_profile():
    """Página de perfil do usuário — dados pessoais + avatar."""
    from modules.user_profile import (
        get_profile, save_profile, is_profile_complete,
        GALERIA_AVATARES, compress_avatar, get_avatar_html,
    )
    _au_p = st.session_state.get("auth_user", {})
    _login = _au_p.get("login", "")
    p = get_profile(_login)

    # ── Card de perfil centralizado ──────────────────────────────────────────
    _completo, _faltando = is_profile_complete(_login)
    _nome_exib  = p.get("nome_completo") or _au_p.get("nome", "?")
    _perfil_exib = PERFIL_LABEL.get(_au_p.get("perfil",""), "")
    _avatar_html = get_avatar_html(_login, size=96)
    _badge_html  = (
        '<span style="background:#D1FAE5;color:#065F46;font-size:.75rem;'
        'font-weight:600;padding:4px 12px;border-radius:20px;">✅ Perfil completo</span>'
        if _completo else
        '<span style="background:#FEF3C7;color:#92400E;font-size:.75rem;'
        f'font-weight:600;padding:4px 12px;border-radius:20px;">⚠️ Faltam: {", ".join(_faltando)}</span>'
    )
    st.markdown(f"""
<div style="text-align:center;padding:32px 16px 24px;background:white;
            border-radius:16px;box-shadow:0 2px 12px rgba(0,0,0,.06);
            margin-bottom:24px;">
  <div style="display:flex;justify-content:center;margin-bottom:12px;">
    {_avatar_html}
  </div>
  <div style="font-size:1.35rem;font-weight:800;color:#1C1816;margin-bottom:4px;">
    {_nome_exib}
  </div>
  <div style="font-size:.82rem;color:#7A6A5A;margin-bottom:14px;">
    {_perfil_exib} &nbsp;·&nbsp; @{_login}
  </div>
  {_badge_html}
</div>
""", unsafe_allow_html=True)

    # ── Helpers de formatação automática ─────────────────────────────────────
    def _fmt_cpf(raw: str) -> str:
        d = "".join(c for c in raw if c.isdigit())[:11]
        if len(d) == 11:
            return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
        return raw

    def _fmt_fone(raw: str) -> str:
        d = "".join(c for c in raw if c.isdigit())
        if len(d) == 11:
            return f"({d[:2]}) {d[2:7]}-{d[7:]}"
        if len(d) == 10:
            return f"({d[:2]}) {d[2:6]}-{d[6:]}"
        return raw

    def _fmt_nome(raw: str) -> str:
        _excl = {"de","da","do","das","dos","e","a","o","em"}
        return " ".join(
            w.capitalize() if w.lower() not in _excl or i == 0 else w.lower()
            for i, w in enumerate(raw.strip().split())
        )

    def _fmt_data(raw: str) -> str:
        d = "".join(c for c in raw if c.isdigit())[:8]
        if len(d) == 8:
            return f"{d[:2]}/{d[2:4]}/{d[4:]}"
        return raw

    # Callbacks — formatam ao sair do campo (on_change)
    def _cb_nome():
        v = st.session_state.get("pf_nome", "")
        if v: st.session_state["pf_nome"] = _fmt_nome(v)
    def _cb_cpf():
        v = st.session_state.get("pf_cpf", "")
        if v: st.session_state["pf_cpf"] = _fmt_cpf(v)
    def _cb_fone():
        v = st.session_state.get("pf_fone", "")
        if v: st.session_state["pf_fone"] = _fmt_fone(v)
    def _cb_nasc():
        v = st.session_state.get("pf_nasc", "")
        if v: st.session_state["pf_nasc"] = _fmt_data(v)
    def _cb_uf():
        v = st.session_state.get("pf_uf", "")
        if v: st.session_state["pf_uf"] = v.upper()
    def _cb_cidade():
        v = st.session_state.get("pf_cidade", "")
        if v: st.session_state["pf_cidade"] = _fmt_nome(v)
    def _cb_bairro():
        v = st.session_state.get("pf_bairro", "")
        if v: st.session_state["pf_bairro"] = _fmt_nome(v)

    # ── Formulário SEM st.form (evita tooltip "Press Enter to submit") ────────
    st.markdown("#### ✏️ Dados pessoais")
    _end = p.get("endereco", {})

    # Inicializa session_state com valores salvos (só na primeira renderização)
    for _k, _v in [
        ("pf_nome",         p.get("nome_completo","")),
        ("pf_nome_social",  p.get("nome_social","")),
        ("pf_cpf",          p.get("cpf","")),
        ("pf_nasc",         p.get("nascimento","")),
        ("pf_fone",         p.get("telefone","")),
        ("pf_email",        p.get("email","")),
        ("pf_rua",          _end.get("rua","")),
        ("pf_num",          _end.get("numero","")),
        ("pf_bairro",       _end.get("bairro","")),
        ("pf_cidade",       _end.get("cidade","")),
        ("pf_uf",           _end.get("uf","")),
    ]:
        if f"_pf_init_{_k}" not in st.session_state:
            st.session_state[_k]             = _v
            st.session_state[f"_pf_init_{_k}"] = True

    _f1, _f2 = st.columns(2)
    _f1.text_input("Nome completo *", key="pf_nome",  on_change=_cb_nome)
    _f2.text_input("CPF *",           key="pf_cpf",   on_change=_cb_cpf,  placeholder="000.000.000-00")

    st.text_input(
        "Como quer ser chamado(a)?",
        key="pf_nome_social",
        placeholder="Ex.: Rafa, Carol, João…",
        help="Aparece no lugar de 'Pepper' na saudação de Bom Dia. "
             "Deixe em branco para usar o primeiro nome do cadastro.",
    )
    _f3, _f4 = st.columns(2)
    _f3.text_input("Data de nascimento *", key="pf_nasc",  on_change=_cb_nasc, placeholder="DD/MM/AAAA")
    _f4.text_input("Telefone *",           key="pf_fone",  on_change=_cb_fone, placeholder="(19) 99999-9999")
    st.text_input("E-mail *", key="pf_email")

    st.markdown("#### 📍 Endereço")
    _e1, _e2 = st.columns([3, 1])
    _e1.text_input("Rua / Avenida", key="pf_rua")
    _e2.text_input("Número",        key="pf_num")
    _e3, _e4, _e5 = st.columns([2, 2, 1])
    _e3.text_input("Bairro",  key="pf_bairro", on_change=_cb_bairro)
    _e4.text_input("Cidade",  key="pf_cidade", on_change=_cb_cidade)
    _e5.text_input("UF",      key="pf_uf",     on_change=_cb_uf, max_chars=2)

    if st.button("💾 Salvar dados", type="primary", width="stretch", key="btn_save_profile"):
        _nome        = st.session_state.get("pf_nome","").strip()
        _nome_social = st.session_state.get("pf_nome_social","").strip()
        _cpf         = _fmt_cpf(st.session_state.get("pf_cpf",""))
        _nasc        = _fmt_data(st.session_state.get("pf_nasc",""))
        _fone        = _fmt_fone(st.session_state.get("pf_fone",""))
        _email       = st.session_state.get("pf_email","").strip().lower()
        _rua         = st.session_state.get("pf_rua","").strip()
        _num         = st.session_state.get("pf_num","").strip()
        _bairro      = _fmt_nome(st.session_state.get("pf_bairro",""))
        _cidade      = _fmt_nome(st.session_state.get("pf_cidade",""))
        _uf          = st.session_state.get("pf_uf","").strip().upper()

        if not _nome:
            st.error("Nome completo é obrigatório.")
        else:
            save_profile(
                _login,
                nome_completo = _fmt_nome(_nome),
                nome_social   = _nome_social,
                cpf           = _cpf,
                nascimento    = _nasc,
                telefone      = _fone,
                email         = _email,
                endereco      = {"rua": _rua, "numero": _num, "bairro": _bairro, "cidade": _cidade, "uf": _uf},
            )
            # Atualiza nome no auth
            _nome_fmt = _fmt_nome(_nome)
            if _nome_fmt != _au_p.get("nome",""):
                from modules.auth import update_user
                update_user(_login, nome=_nome_fmt)
                _au_p["nome"] = _nome_fmt
                st.session_state["auth_user"] = _au_p
            # Limpa flags de inicialização para recarregar os valores salvos
            for _k in ["pf_nome","pf_nome_social","pf_cpf","pf_nasc","pf_fone",
                       "pf_email","pf_rua","pf_num","pf_bairro","pf_cidade","pf_uf"]:
                st.session_state.pop(f"_pf_init_{_k}", None)
            st.success("✅ Dados salvos!")
            st.rerun()

    # ── Avatar (expander compacto) ────────────────────────────────────────────
    with st.expander("📷 Alterar foto / avatar"):
        _av_tab1, _av_tab2 = st.tabs(["📷 Upload de foto", "🎨 Galeria de avatares"])

        with _av_tab1:
            st.caption("Envie uma selfie ou foto de perfil (JPG/PNG, máx 2MB)")
            _foto = st.file_uploader("", type=["jpg","jpeg","png"], label_visibility="collapsed")
            if _foto:
                _fc1, _fc2 = st.columns([2,3])
                with _fc1:
                    st.image(_foto, width=120, caption="Pré-visualização")
                with _fc2:
                    st.write("")
                    if st.button("✅ Usar esta foto", type="primary", width="stretch"):
                        try:
                            _foto.seek(0)
                            _b64 = compress_avatar(_foto.read())
                            save_profile(_login, avatar_tipo="upload", avatar_data=_b64)
                            st.success("Foto salva!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao processar imagem: {e}")

        with _av_tab2:
            st.caption("Escolha um avatar para representar você no sistema")
            # Grid 6 colunas
            _cols_av = st.columns(6)
            for _i, _av in enumerate(GALERIA_AVATARES):
                with _cols_av[_i % 6]:
                    _ativo = p.get("avatar_data") == _av["slug"]
                    _borda = "3px solid #E84300" if _ativo else "2px solid #E8E0D8"
                    _bg_sel = "rgba(232,67,0,.08)" if _ativo else "transparent"
                    st.markdown(
                        f'<div style="text-align:center;padding:6px 2px;border-radius:10px;'
                        f'background:{_bg_sel};margin-bottom:4px;">'
                        f'<div style="width:44px;height:44px;border-radius:50%;background:{_av["bg"]};'
                        f'display:flex;align-items:center;justify-content:center;font-size:1.5rem;'
                        f'margin:0 auto 4px;border:{_borda};">{_av["emoji"]}</div>'
                        f'<div style="font-size:.58rem;color:#7A6A5A;line-height:1.2;">{_av["label"]}</div>'
                        f'</div>', unsafe_allow_html=True,
                    )
                    if st.button(
                        "✓ Ativo" if _ativo else "Usar",
                        key=f"av_{_av['slug']}",
                        width="stretch",
                        type="primary" if _ativo else "secondary",
                    ):
                        save_profile(_login, avatar_tipo="galeria", avatar_data=_av["slug"])
                        st.rerun()


# ── Onboarding: bloqueia Admin sem loja configurada ───────────────────────────
def check_onboarding():
    """Verifica se o Admin precisa passar pelo wizard. Retorna True se bloqueou."""
    _au_ob = st.session_state.get("auth_user", {})
    if _au_ob.get("perfil") not in ("admin",):
        return False   # Só bloqueia Admin; Dev já tem a loja de teste
    from modules.store import get_lojas_do_usuario, get_rede_do_admin
    lojas = get_lojas_do_usuario(_au_ob.get("login",""))
    loja_config = next((l for l in lojas if l.get("configurada")), None)
    if loja_config or not lojas:
        # Se não tem nenhuma loja, deixa passar (Dev precisa criar a loja primeiro)
        return False
    # Tem loja não configurada → wizard
    from modules.onboarding import STEPS, TOTAL_STEPS, get_current_step, progress_html
    _loja = lojas[0]
    _step = get_current_step(_loja["id"])
    if _step > TOTAL_STEPS:
        return False
    # Renderiza wizard
    st.markdown('<div class="cb-title">🎉 Bem-vindo ao Pepper!</div>', unsafe_allow_html=True)
    st.markdown(f'Antes de continuar, vamos configurar a loja **{_loja["nome"]}** em {TOTAL_STEPS} passos.')
    st.markdown(progress_html(_step), unsafe_allow_html=True)
    _s = STEPS[_step - 1]
    st.markdown(f"### {_s['icone']} Passo {_step}/{TOTAL_STEPS} — {_s['titulo']}")
    st.caption(_s["desc"])
    st.info("Complete este passo para desbloquear o restante do sistema.")
    # Aqui cada passo renderiza seu formulário específico
    # (implementação futura; por ora mostra botão de avançar para teste)
    if st.button(f"✅ Concluir passo {_step} e avançar", type="primary"):
        if _step == TOTAL_STEPS:
            from modules.store import marcar_configurada
            marcar_configurada(_loja["id"])
            st.success("🎉 Loja configurada! Bem-vindo ao Pepper!")
        st.rerun()
    return True


# ── Router Mobile (intercede antes do desktop) ────────────────────────────────
_mobile_tab = st.query_params.get("tab", None)
if _mobile_tab:
    from modules.mobile_ui import render_mobile_chrome
    from modules.user_profile import get_avatar_html as _get_av
    _au_mob = st.session_state.get("auth_user", {})
    _av_mob = _get_av(_au_mob.get("login", ""), size=36)
    render_mobile_chrome(_mobile_tab, _au_mob.get("nome", ""), avatar_html=_av_mob)

    if _mobile_tab == "hoje":
        page_bom_dia()
    elif _mobile_tab == "contatos":
        page_campanhas_ativas()
    elif _mobile_tab == "lembrar":
        page_marketing()
    elif _mobile_tab == "analise":
        page_analysis()
    elif _mobile_tab == "mais":
        _mais_nav = ["📋  Relatórios", "⚙️  Configurações", "📣  Marketing"]
        st.markdown("### ⋯ Mais")
        for _mn in _mais_nav:
            if st.button(_mn, width="stretch", key=f"mais_{_mn}"):
                st.query_params.clear()
                st.rerun()
    elif _mobile_tab == "perfil":
        # Botão de avatar na top bar mobile → abre Meu Perfil
        page_profile()
    st.stop()   # não renderiza o layout desktop

# ── Onboarding check (Admin sem loja configurada) ─────────────────────────────
if check_onboarding():
    st.stop()

# ── Router Desktop ────────────────────────────────────────────────────────────
# Perfil e troca de senha: acessíveis apenas via dropdown da top bar
if st.session_state.pop("_show_perfil", False):
    page_profile()
elif st.session_state.pop("_show_senha", False):
    page_change_password()
elif page == "🌄  Bom Dia":
    page_bom_dia()
elif page == "📊  Análise de Contexto":
    page_analysis()
elif page == "📋  Relatórios":
    page_reports()
elif page == "🎯  Campanhas Ativas":
    page_campanhas_ativas()
elif page == "📣  Marketing":
    page_marketing()
elif page == "🗺️  Cobertura":
    page_cobertura()
elif page == "⚙️  Configurações":
    page_settings()
