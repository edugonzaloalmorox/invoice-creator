import unittest

from backend.app.main import project_name


class BackendScaffoldTest(unittest.TestCase):
    def test_backend_scaffold_is_importable(self) -> None:
        self.assertEqual(project_name(), "invoice-filler")
