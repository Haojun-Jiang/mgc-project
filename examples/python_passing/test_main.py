import unittest

from main import add, divide


class TestMathHelpers(unittest.TestCase):
    def test_adds_two_numbers(self):
        self.assertEqual(add(2, 3), 5)

    def test_divides_two_numbers(self):
        self.assertEqual(divide(8, 2), 4)

    def test_rejects_division_by_zero(self):
        with self.assertRaises(ValueError):
            divide(1, 0)


if __name__ == "__main__":
    unittest.main()
