"""
onboarding.py — Wizard de configuração de loja para Admin no primeiro login.

Passos:
  1. Rede (nome + logo)
  2. Loja (nome, CNPJ, endereço)
  3. Microvix API (token + teste)
  4. Catálogo (CSV ou API)
  5. Clientes (CSV ou API)
  6. Estoque inicial
  → Conclusão: loja marcada como configurada

O wizard só libera o próximo passo quando o atual está 100% sem erros.
"""

STEPS = [
    {"n": 1, "titulo": "Sua Rede",        "icone": "🏢", "desc": "Nome e identidade visual da sua rede de franquias"},
    {"n": 2, "titulo": "Dados da Loja",   "icone": "🏪", "desc": "Informações cadastrais da loja"},
    {"n": 3, "titulo": "Microvix API",    "icone": "🔌", "desc": "Credenciais de integração com o sistema ERP"},
    {"n": 4, "titulo": "Catálogo",        "icone": "📦", "desc": "Importar produtos para o sistema"},
    {"n": 5, "titulo": "Clientes",        "icone": "👥", "desc": "Importar base de clientes"},
    {"n": 6, "titulo": "Estoque Inicial", "icone": "📊", "desc": "Definir o estoque atual da loja"},
]

TOTAL_STEPS = len(STEPS)


def get_current_step(loja_id: str) -> int:
    """Retorna o passo atual do wizard (1-6). 7 = concluído."""
    try:
        from modules.store import get_store
        loja = get_store(loja_id)
        if not loja:
            return 1
        if loja.get("configurada"):
            return TOTAL_STEPS + 1
        mx = loja.get("microvix", {})
        if not mx.get("token"):
            return 3 if loja.get("nome") else 2
        # Verifica catálogo
        from modules.product_map import load_map
        if len(load_map()) < 100:
            return 4
        # Verifica clientes
        from modules.client_map import load_clients
        if len(load_clients()) < 5:
            return 5
        # Verifica estoque
        from config import Config
        cfg = Config()
        est = cfg.get("estoque_virtual", {})
        if not any(v > 0 for v in est.values()):
            return 6
        return TOTAL_STEPS + 1
    except Exception:
        return 1


def progress_html(current_step: int) -> str:
    """Gera HTML da barra de progresso do wizard."""
    steps_html = ""
    for s in STEPS:
        n     = s["n"]
        done  = n < current_step
        active = n == current_step
        color  = "#059669" if done else ("#E84300" if active else "#D1C4BE")
        border = "2px solid #E84300" if active else "2px solid transparent"
        check  = "✓" if done else str(n)
        steps_html += f"""
        <div style="display:flex;flex-direction:column;align-items:center;flex:1;">
          <div style="width:32px;height:32px;border-radius:50%;background:{color};
               color:white;display:flex;align-items:center;justify-content:center;
               font-weight:700;font-size:.85rem;border:{border};">{check}</div>
          <div style="font-size:.62rem;color:{'#1C1816' if active else '#9E8E7E'};
               font-weight:{'700' if active else '400'};margin-top:4px;text-align:center;
               max-width:60px;">{s['icone']}</div>
        </div>
        """
    return f"""
    <div style="display:flex;align-items:flex-start;padding:16px 8px 0;
         background:#F8F4F0;border-radius:12px;margin-bottom:20px;">
      {steps_html}
    </div>
    """
