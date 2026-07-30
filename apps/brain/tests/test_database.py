import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


APP_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from models.database import connection_parameters, migration_files


class DatabaseConfigurationTests(unittest.TestCase):
    def test_connection_parameters_use_environment(self):
        environment = {
            "BRAIN_DB_HOST": "database-test",
            "BRAIN_DB_PORT": "5544",
            "POSTGRES_DB": "brain_test",
            "POSTGRES_USER": "brain_user",
            "POSTGRES_PASSWORD": "secret",
            "BRAIN_DB_CONNECT_TIMEOUT_SECONDS": "7",
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            parameters = connection_parameters()

        self.assertEqual(
            parameters,
            {
                "host": "database-test",
                "port": 5544,
                "dbname": "brain_test",
                "user": "brain_user",
                "password": "secret",
                "connect_timeout": 7,
            },
        )

    def test_migration_files_are_ordered_and_sql_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "010_later.sql").write_text("SELECT 10;", encoding="utf-8")
            (root / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
            (root / "README.md").write_text("ignore", encoding="utf-8")

            paths = migration_files(root)

        self.assertEqual([path.name for path in paths], ["001_first.sql", "010_later.sql"])


if __name__ == "__main__":
    unittest.main()
