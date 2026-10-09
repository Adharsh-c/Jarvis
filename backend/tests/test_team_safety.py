import unittest

from app.services.developer import _command_kind


class CommandKindTests(unittest.TestCase):
    def test_python_pytest_is_test(self):
        self.assertEqual(_command_kind("python -m pytest -q", "verify"), "test")

    def test_npm_test_is_test(self):
        self.assertEqual(_command_kind("npm run test", "verify"), "test")

    def test_package_install_is_install(self):
        self.assertEqual(_command_kind("pip install requests", "verify"), "install")

    def test_arbitrary_command_cannot_claim_test_kind(self):
        self.assertEqual(_command_kind("python app.py", "test"), "verify")

    def test_build_command(self):
        self.assertEqual(_command_kind("npm run build", "verify"), "build")


if __name__ == "__main__":
    unittest.main()
