import unittest
from phones import normalize_phone, normalize_phones, format_phone


class TestNormalizePhone(unittest.TestCase):
    def test_plus375_with_spaces_and_dashes(self):
        self.assertEqual(normalize_phone('+375 29 123-45-67'), '+375291234567')

    def test_plain375(self):
        self.assertEqual(normalize_phone('375291234567'), '+375291234567')

    def test_national8_with_parens(self):
        self.assertEqual(normalize_phone('8 (029) 123-45-67'), '+375291234567')

    def test_national8029(self):
        self.assertEqual(normalize_phone('80291234567'), '+375291234567')

    def test_375_with_spaces(self):
        self.assertEqual(normalize_phone('375 44 000 11 22'), '+375440001122')

    def test_national8_017(self):
        self.assertEqual(normalize_phone('8 017 200 30 40'), '+375172003040')

    def test_surrounding_whitespace(self):
        self.assertEqual(normalize_phone('  +375251112233  '), '+375251112233')

    def test_too_short(self):
        self.assertIsNone(normalize_phone('123-45-67'))

    def test_russian_number(self):
        self.assertIsNone(normalize_phone('+7 999 123 45 67'))

    def test_375_too_short(self):
        self.assertIsNone(normalize_phone('375 29 123'))

    def test_empty(self):
        self.assertIsNone(normalize_phone(''))


class TestNormalizePhones(unittest.TestCase):
    def test_multiple_with_noise(self):
        self.assertEqual(
            normalize_phones('+375 29 111 22 33, 8(017)200-30-40; мусор'),
            ['+375291112233', '+375172003040'],
        )

    def test_dedup(self):
        self.assertEqual(
            normalize_phones('один номер +375291112233 и он же 375 29 111 22 33'),
            ['+375291112233'],
        )


class TestFormatPhone(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_phone('+375291234567'), '+375 (29) 123-45-67')


if __name__ == '__main__':
    unittest.main()
