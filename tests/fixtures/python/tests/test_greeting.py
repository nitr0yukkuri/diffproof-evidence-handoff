import unittest


def greeting(name: str) -> str:
    return f"Hello, {name}"


class GreetingTests(unittest.TestCase):
    def test_greeting(self):
        self.assertEqual(greeting("agent"), "Hello, agent")
