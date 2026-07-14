import unittest

from palindrome import is_palindrome


class PalindromeChecks(unittest.TestCase):
    def test_sentence_palindrome(self):
        self.assertTrue(is_palindrome("Never odd or even"))

    def test_regular_word(self):
        self.assertFalse(is_palindrome("agent"))


if __name__ == "__main__":
    unittest.main()
