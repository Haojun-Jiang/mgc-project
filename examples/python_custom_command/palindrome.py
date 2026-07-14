def is_palindrome(text):
    normalized = "".join(char.lower() for char in text if char.isalnum())
    return normalized == normalized[::-1]
