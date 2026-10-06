import importlib
import subprocess
import unittest
from unittest.mock import patch


def pipeline():
    try:
        return importlib.import_module('scripts.run_periodic_h1')
    except ModuleNotFoundError as exc:
        raise AssertionError('half-year pipeline is not implemented') from exc


class H1PipelineTest(unittest.TestCase):
    def run_stage(self, **kwargs):
        commands = []
        module = pipeline()
        with patch.object(module.subprocess, 'run', side_effect=lambda cmd, **kw: commands.append(cmd)):
            module.run_pipeline(**kwargs)
        return [[str(x) for x in cmd[1:]] for cmd in commands]

    def test_daily_metadata_never_invokes_locator_or_llm(self):
        commands = self.run_stage(stage='metadata')
        self.assertEqual([cmd[0] for cmd in commands], [
            'scripts/periodic_progress.py', 'scripts/fetch_periodic_reports.py',
            'scripts/periodic_progress.py'])
        self.assertIn('--strategy', commands[1])
        self.assertEqual(commands[1][-3:], ['--strategy', 'full', '--write'])
        for cmd in commands:
            self.assertEqual(cmd[1:7], ['--sample', 'config/annual_formal_2025.csv',
                                     '--fiscal-year', '2026', '--report-type', 'semiannual'])

    def test_queue_only_locates_48_and_extracts_36_with_no_force_or_retry(self):
        commands = self.run_stage(stage='queue', confirm_llm=True)
        self.assertEqual([cmd[0] for cmd in commands], [
            'scripts/periodic_progress.py', 'scripts/locate_periodic_pages.py',
            'scripts/extract_periodic_reports.py', 'scripts/periodic_progress.py'])
        self.assertEqual(commands[1][-3:], ['--limit', '48', '--write'])
        self.assertEqual(commands[2][-3:], ['--limit', '36', '--confirm-llm'])
        for cmd in commands:
            self.assertEqual(cmd[1:7], ['--sample', 'config/annual_formal_2025.csv',
                                     '--fiscal-year', '2026', '--report-type', 'semiannual'])
            for forbidden in ['--retry-failed', '--force-reviewed', '--report-id']:
                self.assertNotIn(forbidden, cmd)

    def test_queue_requires_confirmation_before_any_side_effect(self):
        module = pipeline()
        with patch.object(module.subprocess, 'run') as runner:
            with self.assertRaises(ValueError):
                module.run_pipeline(stage='queue')
            runner.assert_not_called()

    def test_small_pilot_limits_are_preserved(self):
        commands = self.run_stage(stage='queue', confirm_llm=True, locate_limit=3, extract_limit=3)
        self.assertEqual(commands[1][-3:], ['--limit', '3', '--write'])
        self.assertEqual(commands[2][-3:], ['--limit', '3', '--confirm-llm'])

    def test_invalid_limits_and_stages_do_not_start_work(self):
        module = pipeline()
        for args in [dict(locate_limit=0), dict(extract_limit=0), dict(locate_limit=49),
                     dict(extract_limit=37), dict(stage='annual')]:
            with self.subTest(args=args), patch.object(module.subprocess, 'run') as runner:
                with self.assertRaises(ValueError):
                    module.run_pipeline(**{'stage': 'queue', 'confirm_llm': True, **args})
                runner.assert_not_called()

    def test_locate_error_prevents_llm_but_still_records_progress(self):
        module = pipeline()
        commands = []
        def run(cmd, **kwargs):
            commands.append(cmd[1])
            if cmd[1] == 'scripts/locate_periodic_pages.py':
                raise subprocess.CalledProcessError(1, cmd)
        with patch.object(module.subprocess, 'run', side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError):
                module.run_pipeline(stage='queue', confirm_llm=True)
        self.assertEqual(commands, ['scripts/periodic_progress.py',
                                   'scripts/locate_periodic_pages.py', 'scripts/periodic_progress.py'])

    def test_extract_error_is_not_swallowed(self):
        module = pipeline()
        commands = []
        def run(cmd, **kwargs):
            commands.append(cmd[1])
            if cmd[1] == 'scripts/extract_periodic_reports.py':
                raise subprocess.CalledProcessError(1, cmd)
        with patch.object(module.subprocess, 'run', side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError):
                module.run_pipeline(stage='queue', confirm_llm=True)
        self.assertEqual(commands[-1], 'scripts/periodic_progress.py')


if __name__ == '__main__':
    unittest.main()
