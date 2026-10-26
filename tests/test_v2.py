"""V2 workflows in isolated repositories; package managers are simulated."""

from pathlib import Path
from unittest.mock import Mock, patch
import unittest

from few_updater import cli
from few_updater.tools import pm_selector
from few_updater.tools.pm.uv import Uv
from few_updater.tools.process import Error, run
from test_workflows import RepositoryTest


class SelectorTests(unittest.TestCase):
    def test_all_candidates_are_checked(self):
        for detections in ((True, False, True), (False, False, False), (False, True, False)):
            candidates = [Mock(name=str(i), detect=Mock(return_value=value))
                          for i, value in enumerate(detections)]
            for i, candidate in enumerate(candidates):
                candidate.name = str(i)
            with self.subTest(detections=detections), patch.object(pm_selector, 'CANDIDATES', candidates):
                if sum(detections) == 1:
                    self.assertIs(pm_selector.select(), candidates[1])
                else:
                    with self.assertRaises(Error):
                        pm_selector.select()
                for candidate in candidates:
                    candidate.detect.assert_called_once_with()


class V2Tests(RepositoryTest):
    def native_bump(self, level):
        self.input.assert_called_once()
        self.current = {'major': '2.0.0', 'minor': '1.3.0', 'patch': '1.2.4'}[level]
        Path('pyproject.toml').write_text(f'[project]\nversion = "{self.current}"\n')
        Path('uv.lock').write_text('bumped\n')

    def test_local_bump_levels(self):
        for level in ('major', 'minor', 'patch'):
            with self.subTest(level=level), patch.object(Uv, 'bump', side_effect=self.native_bump) as bump:
                self.assertEqual(self.invoke(f'bump {level}'), 0)
                bump.assert_called_once_with(level)
                self.input.assert_called_once()
                self.assert_no_commit()
                self.assertEqual(run('git', 'tag').strip(), '1.2.3')
                self.assertTrue(run('git', 'diff'))
                run('git', 'restore', 'pyproject.toml', 'uv.lock')
                self.current = '1.2.3'

    def test_local_bump_declined(self):
        with patch.object(Uv, 'bump') as bump:
            self.assertEqual(self.invoke('bump patch', 'n'), 0)
            self.input.assert_called_once()
            bump.assert_not_called()
            self.assertEqual(run('git', 'status', '--porcelain'), '')
            self.assert_no_commit()

    def test_release_override(self):
        self.new_commit()
        with patch.object(Uv, 'bump', side_effect=self.native_bump) as bump:
            self.fail = ('git', 'tag', '-a')
            self.assertEqual(self.invoke('release --bump minor'), 1)
            bump.assert_called_once_with('minor')
            self.assertIn(('git', 'tag', '-a', '1.3.0', '-m', '1.3.0'), self.calls)
            self.assert_no_push()

    def assert_release_level(self, level, target):
        self.new_commit()
        with patch.object(Uv, 'bump', side_effect=self.native_bump) as bump:
            self.assertEqual(self.invoke(f'release --bump {level}'), 0)
            bump.assert_called_once_with(level)
        self.input.assert_called_once()
        self.assertEqual(run('git', 'cat-file', '-t', target).strip(), 'tag')
        self.assertEqual(run('git', 'for-each-ref', '--format=%(contents)',
                             f'refs/tags/{target}').strip(), target)
        self.assertIn(('git', 'push', '--atomic', 'origin', 'main', target), self.calls)

    def test_release_minor(self):
        self.assert_release_level('minor', '1.3.0')

    def test_release_major(self):
        self.assert_release_level('major', '2.0.0')

    def test_no_bump_without_changes(self):
        self.new_commit()
        self.current = '1.2.4'
        with patch.object(Uv, 'bump') as bump:
            self.assertEqual(self.invoke('release --no-bump'), 0)
            bump.assert_not_called()
        self.input.assert_called_once()
        self.assertEqual(run('git', 'rev-parse', 'HEAD'), self.initial)
        self.assertFalse(any(c[:2] == ('git', 'commit') for c in self.calls))
        self.assertEqual(run('git', 'cat-file', '-t', '1.2.4').strip(), 'tag')

    def test_no_bump_commits_version_files(self):
        self.new_commit()
        self.current = '1.2.4'
        Path('pyproject.toml').write_text('[project]\nversion = "1.2.4"\n')
        self.assertEqual(self.invoke('release --no-bump'), 0)
        self.input.assert_called_once()
        self.assertIn(('git', 'add', '--', 'pyproject.toml'), self.calls)
        self.assertFalse(any(c[:3] == ('uv', 'version', '--bump') for c in self.calls))

    def test_no_bump_rejects_unrelated_changes(self):
        Path('app.py').write_text('dirty')
        self.assertEqual(self.invoke('release --no-bump'), 1)
        self.input.assert_not_called()
        self.assert_no_commit()

    def test_no_bump_collision_before_confirmation(self):
        self.new_commit()
        self.assertEqual(self.invoke('release --no-bump'), 1)
        self.input.assert_not_called()
        self.assert_no_commit()

    def test_no_bump_declined_preserves_version_changes(self):
        self.new_commit()
        self.current = '1.2.4'
        Path('pyproject.toml').write_text('[project]\nversion = "1.2.4"\n')
        self.assertEqual(self.invoke('release --no-bump', 'n'), 0)
        self.input.assert_called_once()
        self.assert_no_commit()
        self.assertTrue(run('git', 'diff'))
        self.assertNotIn('1.2.4', run('git', 'tag'))

    def test_bump_rejects_unexpected_changes(self):
        self.uv_mode = 'unexpected'
        self.assertEqual(self.invoke('bump patch'), 1)
        self.input.assert_called_once()
        self.assert_no_commit()
        self.assertEqual(Path('app.py').read_text(), 'unexpected\n')

    def test_bump_failure_preserves_changes(self):
        self.fail = ('uv', 'version', '--bump')
        self.assertEqual(self.invoke('bump patch'), 1)
        self.input.assert_called_once()
        self.assert_no_commit()
        self.assertEqual(Path('uv.lock').read_text(), 'partial uv write\n')

    def test_cli_rejects_invalid_options(self):
        for args in (['bump'], ['bump', 'invalid'], ['release', '--bump', 'minor', '--no-bump']):
            with self.subTest(args=args), patch('sys.stderr'), self.assertRaises(SystemExit) as error:
                cli.main(args)
            self.assertEqual(error.exception.code, 2)


class NativeManagerTests(unittest.TestCase):
    def test_symmetric_native_bumps(self):
        from few_updater.tools.pm.npm import Npm
        for level in ('major', 'minor', 'patch'):
            for manager, module, command in (
                (Uv(), 'uv', ('uv', 'version', '--bump', level)),
                (Npm(), 'npm', ('npm', 'version', level, '--no-git-tag-version')),
            ):
                with self.subTest(manager=module, level=level), \
                        patch(f'few_updater.tools.pm.{module}.run') as native:
                    manager.bump(level)
                    native.assert_called_once_with(*command, capture_output=False)

    def test_native_bump_errors_propagate(self):
        from few_updater.tools.pm.npm import Npm
        for manager, module in ((Uv(), 'uv'), (Npm(), 'npm')):
            with self.subTest(manager=module), \
                    patch(f'few_updater.tools.pm.{module}.run', side_effect=Error('failed')):
                with self.assertRaises(Error):
                    manager.bump('patch')
