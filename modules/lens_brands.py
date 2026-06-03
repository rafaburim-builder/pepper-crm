"""
lens_brands.py — Detecção de marca de lentes a partir da descrição do produto.

Marcas reconhecidas:
  ChilliVision / ChilliTek — produtos próprios da Chilli Beans
  Hoya                     — Hoya
  Zeiss                    — Carl Zeiss / Zeiss
  Essilor / Varilux        — Essilor, Varilux, Kodak, Crizal, Transitions
  Outros                   — não reconhecido (requer revisão manual)
"""

# (marca_display, [keywords_em_maiúsculas]) — primeira correspondência ganha
_BRAND_RULES = [
    ("ChilliVision / ChilliTek", ["CHILLIVISION", "CHILLITEK", "CHILLI VISION", "CHILLI TEK"]),
    ("Hoya",                     ["HOYA"]),
    ("Zeiss",                    ["ZEISS"]),
    ("Essilor / Varilux",        ["ESSILOR", "VARILUX", "KODAK", "CRIZAL", "TRANSITIONS"]),
]

BRAND_COLORS: dict = {
    "ChilliVision / ChilliTek": "#D4002A",
    "Hoya":                     "#2563EB",
    "Zeiss":                    "#059669",
    "Essilor / Varilux":        "#7C3AED",
    "Outros":                   "#9CA3AF",
}

ALL_BRANDS: list = [b for b, _ in _BRAND_RULES] + ["Outros"]


def detect_brand(descricao: str) -> str:
    """Retorna o nome da marca detectada ou 'Outros'."""
    desc_upper = str(descricao or "").upper()
    for brand, keywords in _BRAND_RULES:
        for kw in keywords:
            if kw in desc_upper:
                return brand
    return "Outros"
