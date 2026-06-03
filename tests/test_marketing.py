"""
Testes de normalização de telefone, geração de link de WhatsApp e
preenchimento de template de mensagem (modules/marketing.py).

A normalização de telefone é crítica: um número malformado vira link de
WhatsApp quebrado e contato perdido — exatamente o "ouro" que o vendedor citou.
"""
import os
import sys
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import marketing  # noqa: E402


class TestNormalizePhone(unittest.TestCase):
    def test_vazio_ou_lixo(self):
        self.assertEqual(marketing.normalize_phone(""), "")
        self.assertEqual(marketing.normalize_phone(None), "")
        self.assertEqual(marketing.normalize_phone("abc"), "")
        self.assertEqual(marketing.normalize_phone("123"), "")  # tamanho inválido

    def test_celular_11_digitos(self):
        self.assertEqual(marketing.normalize_phone("11987654321"), "11987654321")

    def test_fixo_10_digitos(self):
        self.assertEqual(marketing.normalize_phone("1133334444"), "1133334444")

    def test_formatacao_com_simbolos(self):
        self.assertEqual(marketing.normalize_phone("(11) 98765-4321"), "11987654321")

    def test_prefixo_pais_55(self):
        self.assertEqual(marketing.normalize_phone("5511987654321"), "11987654321")
        self.assertEqual(marketing.normalize_phone("+55 (11) 98765-4321"), "11987654321")

    def test_9_digitos_sem_ddd_precisa_default(self):
        self.assertEqual(marketing.normalize_phone("987654321"), "")  # sem DDD -> inválido
        self.assertEqual(marketing.normalize_phone("987654321", default_ddd="11"),
                         "11987654321")

    def test_8_digitos_com_default_ddd(self):
        self.assertEqual(marketing.normalize_phone("33334444", default_ddd="11"),
                         "1133334444")

    def test_default_ddd_invalido(self):
        # DDD com menos de 2 dígitos não completa
        self.assertEqual(marketing.normalize_phone("987654321", default_ddd="1"), "")


class TestWhatsappLink(unittest.TestCase):
    def test_link_valido(self):
        link = marketing.make_whatsapp_link("11987654321", "Olá!")
        self.assertTrue(link.startswith("https://wa.me/5511987654321?text="))

    def test_telefone_invalido_retorna_vazio(self):
        self.assertEqual(marketing.make_whatsapp_link("123", "Olá!"), "")

    def test_mensagem_e_url_encoded(self):
        msg = "Oi Ana! Tudo bem? 😎 Passa lá & confere"
        link = marketing.make_whatsapp_link("11987654321", msg)
        text_part = link.split("?text=", 1)[1]
        # A mensagem deve voltar idêntica ao decodificar
        self.assertEqual(urllib.parse.unquote(text_part), msg)
        # Caracteres reservados não podem aparecer crus
        self.assertNotIn(" ", text_part)
        self.assertNotIn("&", text_part)


class TestFormatMessage(unittest.TestCase):
    def test_substitui_placeholders(self):
        out = marketing.format_message(
            marketing.DEFAULT_TEMPLATE, "Ana Maria Silva", "LV", "10/01/2026", 120)
        self.assertIn("Ana", out)              # só primeiro nome
        self.assertNotIn("Maria", out)
        self.assertIn("120", out)              # dias
        self.assertIn("10/01/2026", out)       # data
        self.assertIn("armação de grau", out)  # rótulo de categoria mapeado
        self.assertNotIn("{nome}", out)        # nenhum placeholder remanescente
        self.assertNotIn("{categoria}", out)

    def test_categoria_desconhecida_usa_lowercase(self):
        out = marketing.format_message("Sua {categoria}", "Joao", "XYZ", "01/01/2026", 1)
        self.assertIn("xyz", out)

    def test_nome_vazio_nao_quebra(self):
        out = marketing.format_message("Oi {nome}", "", "LV", "01/01/2026", 1)
        self.assertIsInstance(out, str)


if __name__ == "__main__":
    unittest.main()
