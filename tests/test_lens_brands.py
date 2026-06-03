"""
test_lens_brands.py — Testes da detecção de marca de lentes (modules/lens_brands.py).

detect_brand classifica a descrição de produto do Microvix em marca de lente.
Isso alimenta relatórios de mix de lentes (margem alta) — se a detecção quebrar,
o vendedor/gerente perde visibilidade do que está vendendo. Travamos as regras.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import lens_brands  # noqa: E402


class TestDetectBrand(unittest.TestCase):

    def test_chillivision(self):
        self.assertEqual(lens_brands.detect_brand("LENTE CHILLIVISION 1.67"), "ChilliVision / ChilliTek")

    def test_chillitek(self):
        self.assertEqual(lens_brands.detect_brand("ARMACAO CHILLITEK"), "ChilliVision / ChilliTek")

    def test_chilli_vision_com_espaco(self):
        self.assertEqual(lens_brands.detect_brand("Chilli Vision Blue"), "ChilliVision / ChilliTek")

    def test_hoya(self):
        self.assertEqual(lens_brands.detect_brand("LENTE HOYA HILUX"), "Hoya")

    def test_zeiss(self):
        self.assertEqual(lens_brands.detect_brand("Carl Zeiss DuraVision"), "Zeiss")

    def test_essilor(self):
        self.assertEqual(lens_brands.detect_brand("ESSILOR EYEZEN"), "Essilor / Varilux")

    def test_varilux(self):
        self.assertEqual(lens_brands.detect_brand("Lente Varilux X Series"), "Essilor / Varilux")

    def test_crizal_mapeia_para_essilor(self):
        self.assertEqual(lens_brands.detect_brand("Tratamento CRIZAL Sapphire"), "Essilor / Varilux")

    def test_transitions_mapeia_para_essilor(self):
        self.assertEqual(lens_brands.detect_brand("TRANSITIONS Gen 8"), "Essilor / Varilux")

    def test_desconhecida_retorna_outros(self):
        self.assertEqual(lens_brands.detect_brand("LENTE GENERICA NACIONAL"), "Outros")

    def test_case_insensitive(self):
        self.assertEqual(lens_brands.detect_brand("hoya"), "Hoya")
        self.assertEqual(lens_brands.detect_brand("HoYa"), "Hoya")

    def test_string_vazia(self):
        self.assertEqual(lens_brands.detect_brand(""), "Outros")

    def test_none_nao_quebra(self):
        self.assertEqual(lens_brands.detect_brand(None), "Outros")

    def test_numero_nao_quebra(self):
        self.assertEqual(lens_brands.detect_brand(12345), "Outros")

    def test_chilli_tem_prioridade_sobre_outras(self):
        # primeira regra na lista deve ganhar mesmo se outra keyword aparecer depois
        self.assertEqual(
            lens_brands.detect_brand("CHILLIVISION com tratamento estilo CRIZAL"),
            "ChilliVision / ChilliTek",
        )


class TestMetadados(unittest.TestCase):

    def test_all_brands_inclui_outros(self):
        self.assertIn("Outros", lens_brands.ALL_BRANDS)

    def test_toda_marca_tem_cor(self):
        for brand in lens_brands.ALL_BRANDS:
            self.assertIn(brand, lens_brands.BRAND_COLORS, f"{brand} sem cor definida")

    def test_cores_sao_hex(self):
        for brand, cor in lens_brands.BRAND_COLORS.items():
            self.assertRegex(cor, r"^#[0-9A-Fa-f]{6}$", f"{brand} cor inválida: {cor}")

    def test_detect_brand_so_retorna_marcas_conhecidas(self):
        for desc in ["HOYA", "ZEISS", "ESSILOR", "CHILLITEK", "xyz"]:
            self.assertIn(lens_brands.detect_brand(desc), lens_brands.ALL_BRANDS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
