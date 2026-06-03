"""
mobile_ui.py — Layout e componentes para smartphone.

Detecta mobile via CSS (@media max-width:768px) e renderiza:
  - Header fixo no topo (52px)
  - Bottom navigation bar (64px)
  - Conteúdo rola entre os dois (sem scrollbar visível)

Navegação por st.query_params:  ?tab=hoje | contatos | lembrar | analise | mais
"""
import streamlit as st

# ── Constantes ────────────────────────────────────────────────────────────────
TABS = [
    ("hoje",      "🌄", "Hoje"),
    ("contatos",  "📱", "Contatos"),
    ("lembrar",   "🎂", "Lembrar"),
    ("analise",   "📊", "Análise"),
    ("mais",      "⋯",  "Mais"),
]

MOBILE_BREAKPOINT = 768   # px


# ── CSS global (mobile + PWA) ────────────────────────────────────────────────

def inject_mobile_css():
    """Injeta CSS para layout mobile-first. Seguro chamar no desktop — é no-op."""
    st.markdown("""
<style>
/* ═══════════════════════════════════════════════════════════════
   PEPPER MOBILE LAYOUT  —  @media ≤768px
   ═══════════════════════════════════════════════════════════════ */
@media screen and (max-width: 768px) {

  /* Esconde a sidebar desktop */
  [data-testid="stSidebar"],
  [data-testid="collapsedControl"] { display: none !important; }

  /* Esconde header padrão do Streamlit */
  [data-testid="stHeader"] { display: none !important; }

  /* Área principal: espaço para header (52px) e bottom nav (64px) */
  .main .block-container {
    padding-top:    56px !important;
    padding-bottom: 76px !important;
    padding-left:   12px !important;
    padding-right:  12px !important;
    max-width:      100% !important;
    overflow-x:     hidden !important;
  }

  /* Scrollbar invisível (conteúdo rola, barra não aparece) */
  ::-webkit-scrollbar           { width: 0px; background: transparent; }
  html, body, .main             { overflow-x: hidden !important; }

  /* Botões: área de toque mínima 48px */
  .stButton > button {
    min-height: 48px !important;
    font-size:  1rem  !important;
    width:      100%  !important;
    border-radius: 10px !important;
  }

  /* Tabs do Streamlit: full width */
  .stTabs [data-baseweb="tab-list"] { gap: 0 !important; }
  .stTabs [data-baseweb="tab"]      { flex: 1 !important; justify-content: center !important; }

  /* Métricas compactas */
  [data-testid="metric-container"] { padding: 8px 6px !important; }
  [data-testid="stMetricValue"]    { font-size: 1.1rem !important; }
  [data-testid="stMetricLabel"]    { font-size: 0.72rem !important; }

  /* DataFrames: scroll horizontal interno */
  .stDataFrame { overflow-x: auto !important; }
  .stDataFrame > div { max-width: 100% !important; }

  /* Campos de input: full width */
  .stTextInput > div, .stSelectbox > div,
  .stDateInput > div, .stNumberInput > div {
    width: 100% !important;
  }

  /* Expanders sem padding lateral excessivo */
  .streamlit-expanderContent { padding: 0.5rem 0 !important; }

  /* Colunas de 2: empilha verticalmente em telas muito pequenas */
  @media (max-width: 480px) {
    [data-testid="column"] { min-width: 100% !important; }
  }
}

/* ═══════════════════════════════════════════════════════════════
   PEPPER MOBILE HEADER  (fixo no topo)
   ═══════════════════════════════════════════════════════════════ */
.pepper-mobile-header {
  display:         none;          /* desktop: oculto */
  position:        fixed;
  top:             0;
  left:            0;
  right:           0;
  height:          52px;
  background:      #1C1816;
  color:           white;
  align-items:     center;
  justify-content: space-between;
  padding:         0 16px;
  z-index:         10000;
  font-family:     'Poppins', sans-serif;
  box-shadow:      0 2px 8px rgba(0,0,0,0.4);
}
.pepper-mobile-header .pm-logo  { font-size: 1.25rem; font-weight: 900; color: #E84300; letter-spacing: -0.5px; }
.pepper-mobile-header .pm-user  { font-size: 0.78rem; opacity: 0.75; }

/* ═══════════════════════════════════════════════════════════════
   PEPPER BOTTOM NAV  (fixo no rodapé)
   ═══════════════════════════════════════════════════════════════ */
.pepper-bottom-nav {
  display:         none;          /* desktop: oculto */
  position:        fixed;
  bottom:          0;
  left:            0;
  right:           0;
  height:          64px;
  background:      #1C1816;
  z-index:         10000;
  border-top:      1px solid #2E2822;
  box-shadow:      0 -2px 10px rgba(0,0,0,0.3);
}
.pbn-inner {
  display:         flex;
  height:          100%;
  align-items:     stretch;
}
.pbn-item {
  flex:            1;
  display:         flex;
  flex-direction:  column;
  align-items:     center;
  justify-content: center;
  color:           #7A6A5A;
  text-decoration: none;
  font-size:       0.62rem;
  font-family:     'Poppins', sans-serif;
  gap:             2px;
  cursor:          pointer;
  -webkit-tap-highlight-color: rgba(232,67,0,0.15);
  transition:      color 0.15s, background 0.15s;
  border:          none;
  background:      transparent;
  padding:         0;
}
.pbn-item:active  { background: rgba(232,67,0,0.08); }
.pbn-item.active  { color: #E84300; }
.pbn-item .pbn-icon  { font-size: 1.45rem; line-height: 1; }
.pbn-item .pbn-label { font-size: 0.62rem; font-weight: 500; }

/* Ativa header e bottom-nav somente em mobile */
@media screen and (max-width: 768px) {
  .pepper-mobile-header { display: flex !important; }
  .pepper-bottom-nav    { display: block !important; }
}

/* ═══════════════════════════════════════════════════════════════
   PEPPER CARD  (componente reutilizável mobile)
   ═══════════════════════════════════════════════════════════════ */
.pepper-card {
  background:    white;
  border-radius: 12px;
  padding:       14px 16px;
  margin-bottom: 10px;
  box-shadow:    0 1px 4px rgba(0,0,0,0.08);
  border-left:   4px solid transparent;
}
.pepper-card.urgente { border-left-color: #E84300; }
.pepper-card.hoje    { border-left-color: #F59E0B; }
.pepper-card.semana  { border-left-color: #059669; }
.pepper-card .pc-title  { font-weight: 700; font-size: 0.95rem; color: #1C1816; margin-bottom: 2px; }
.pepper-card .pc-sub    { font-size: 0.78rem; color: #7A6A5A; margin-bottom: 10px; }
.pepper-card .pc-action { display: flex; gap: 8px; }
.pepper-card .pc-btn {
  flex:          1;
  padding:       10px 0;
  border-radius: 8px;
  border:        none;
  font-size:     0.82rem;
  font-weight:   600;
  cursor:        pointer;
  text-align:    center;
  text-decoration: none;
  display:       inline-block;
}
.pepper-card .pc-btn.wa  { background: #25D366; color: white; }
.pepper-card .pc-btn.ok  { background: #F0EBE3; color: #1C1816; }
</style>
""", unsafe_allow_html=True)


# ── Header e Bottom Nav ──────────────────────────────────────────────────────

def render_mobile_chrome(current_tab: str, user_nome: str = "", avatar_html: str = ""):
    """Renderiza o header fixo e a barra de navegação inferior."""
    nome_curto = user_nome.split()[0] if user_nome else "?"
    tabs_html  = ""
    for key, icon, label in TABS:
        active = "active" if key == current_tab else ""
        tabs_html += (
            f'<button class="pbn-item {active}" onclick="pepperNav(\'{key}\')">'
            f'<span class="pbn-icon">{icon}</span>'
            f'<span class="pbn-label">{label}</span>'
            f'</button>'
        )

    # Botão do usuário no canto direito — avatar ou fallback com inicial
    _user_btn = (
        f'<button class="pm-user-btn" onclick="pepperNav(\'perfil\')" '
        f'title="Meu Perfil">'
        f'{avatar_html if avatar_html else f"<span>{nome_curto[0].upper() if nome_curto else "?"}</span>"}'
        f'</button>'
    )

    st.markdown(f"""
<style>
.pm-user-btn {{
  background:    none;
  border:        2px solid rgba(255,255,255,0.25);
  border-radius: 50%;
  width:         36px;
  height:        36px;
  padding:       0;
  cursor:        pointer;
  display:       flex;
  align-items:   center;
  justify-content: center;
  overflow:      hidden;
  -webkit-tap-highlight-color: rgba(232,67,0,0.2);
}}
.pm-user-btn img {{
  width:         36px;
  height:        36px;
  border-radius: 50%;
  object-fit:    cover;
}}
.pm-user-btn > div {{
  width:         36px !important;
  height:        36px !important;
  border-radius: 50% !important;
}}
</style>
<!-- ── PEPPER MOBILE CHROME ───────────────────────────────── -->
<div class="pepper-mobile-header">
  <span class="pm-logo">🌶️ Pepper</span>
  {_user_btn}
</div>
<div class="pepper-bottom-nav">
  <div class="pbn-inner">{tabs_html}</div>
</div>
<script>
function pepperNav(tab) {{
    const url = new URL(window.location.href);
    url.searchParams.set('tab', tab);
    window.location.replace(url.toString());
}}
</script>
""", unsafe_allow_html=True)


# ── Utilitário: card de ação ─────────────────────────────────────────────────

def action_card(tipo: str, titulo: str, subtitulo: str, wa_link: str = "", key: str = ""):
    """Renderiza um card de ação mobile com botão WhatsApp."""
    btn_wa  = (f'<a class="pc-btn wa" href="{wa_link}" target="_blank">📱 Contatar</a>' if wa_link else "")
    btn_ok  = f'<button class="pc-btn ok" onclick="pepperDone(\'{key}\')">✅ Feito</button>'
    st.markdown(f"""
<div class="pepper-card {tipo}">
  <div class="pc-title">{titulo}</div>
  <div class="pc-sub">{subtitulo}</div>
  <div class="pc-action">{btn_wa}{btn_ok}</div>
</div>
""", unsafe_allow_html=True)
