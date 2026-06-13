import unittest
from cities import normalize_city


class TestNormalizeCity(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(normalize_city('г. Минск'), 'Минск')

    def test_single_letter(self):
        self.assertEqual(normalize_city('г. Г. Минск'), 'Минск')

    def test_single_letter_with_dot_space(self):
        self.assertEqual(normalize_city('г. Г .Минск'), 'Минск')

    def test_extra_spaces(self):
        self.assertEqual(normalize_city('  г.  Слуцк '), 'Слуцк')

    def test_city_molodechno(self):
        self.assertEqual(normalize_city('г. Молодечно'), 'Молодечно')

    def test_city_dzerzhinsk(self):
        self.assertEqual(normalize_city('г. Дзержинск'), 'Дзержинск')

    def test_city_d_kirshi(self):
        self.assertEqual(normalize_city('г. Д. Кирши'), 'Кирши')

    def test_city_ag_koldidishi(self):
        self.assertEqual(normalize_city('г. Аг. Колодищи'), 'Колодищи')

    def test_city_agrogorodok(self):
        self.assertEqual(normalize_city('г. Агрогородок Колодищи'), 'Колодищи')

    def test_city_koldidishi(self):
        self.assertEqual(normalize_city('г. Колодищи'), 'Колодищи')

    def test_trailing_soviet(self):
        self.assertEqual(normalize_city('г. Новодворский с/с'), 'Новодворский')

    def test_posyolok(self):
        self.assertEqual(normalize_city('п. Боровляны'), 'Боровляны')

    def test_keeping_district(self):
        self.assertEqual(normalize_city('Минский р-н'), 'Минский р-н')

    def test_keeping_district_dzerzhinsky(self):
        self.assertEqual(normalize_city('Дзержинский р-н'), 'Дзержинский р-н')

    def test_keeping_oblast(self):
        self.assertEqual(normalize_city('г. Могилевская обл.'), 'Могилевская обл.')

    def test_typo_left_untouched(self):
        self.assertEqual(normalize_city('г. Минсчк'), 'Минсчк')

    def test_empty(self):
        self.assertEqual(normalize_city(''), '')

    def test_none(self):
        self.assertEqual(normalize_city(None), '')


if __name__ == '__main__':
    unittest.main()
