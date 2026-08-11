import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TABLES = (
    "risk_source_documents",
    "derivative_risk_cases",
    "risk_case_documents",
    "risk_case_evidence",
    "risk_media_reports",
    "risk_media_report_sources",
)
PRIVATE_TABLES = ("risk_media_leads", "risk_media_backfill_windows")


class RiskReadonlyMigrationTest(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "db" / "009_risk_public_readonly.sql"
        self.assertTrue(self.path.exists(), "risk readonly migration is missing")
        self.sql = self.path.read_text(encoding="utf-8").lower()

    def test_public_tables_revoke_all_then_grant_select(self):
        for table in PUBLIC_TABLES:
            with self.subTest(table=table):
                self.assertIn(
                    f"revoke all on table public.{table} from anon, authenticated",
                    self.sql,
                )
                self.assertIn(
                    f"grant select on table public.{table} to anon, authenticated",
                    self.sql,
                )

    def test_private_tables_have_no_browser_privileges(self):
        for table in PRIVATE_TABLES:
            with self.subTest(table=table):
                self.assertIn(
                    f"revoke all on table public.{table} from anon, authenticated",
                    self.sql,
                )
                self.assertNotIn(
                    f"grant select on table public.{table} to anon, authenticated",
                    self.sql,
                )

    def test_migration_is_idempotent_and_keeps_rls_enabled(self):
        for table in PUBLIC_TABLES + PRIVATE_TABLES:
            with self.subTest(table=table):
                self.assertIn(
                    f"alter table public.{table} enable row level security",
                    self.sql,
                )

    def test_verification_covers_all_risk_table_grants(self):
        verify = (ROOT / "db" / "verify.sql").read_text(encoding="utf-8").lower()
        self.assertIn("role_table_grants", verify)
        for table in PUBLIC_TABLES + PRIVATE_TABLES:
            with self.subTest(table=table):
                self.assertIn(table, verify)


if __name__ == "__main__":
    unittest.main()
