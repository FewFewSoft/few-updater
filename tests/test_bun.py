"""Bun coverage without external commands or Git repositories."""

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch, call

from few_updater.tools import git, pm_selector
from few_updater.tools.pm.bun import Bun
from few_updater.tools.process import Error
from few_updater.workflows.bump import bump
from few_updater.workflows.release import release
from few_updater.workflows.upgrade import upgrade


class BunTests(unittest.TestCase):
    def setUp(self):
        self.previous = Path.cwd()
        self.directory = tempfile.TemporaryDirectory()
        os.chdir(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(os.chdir, self.previous)
        Path('package.json').write_text(json.dumps({'version': '1.2.3'}))
        self.manager = Bun()

    def test_detection(self):
        for lock in ('bun.lock', 'bun.lockb'):
            with self.subTest(lock=lock):
                Path(lock).touch()
                self.assertEqual(pm_selector.select().name, 'bun')
                Path('package-lock.json').touch()
                self.assertEqual(pm_selector.select().name, 'bun')
                Path(lock).unlink()
                self.assertEqual(pm_selector.select().name, 'npm')
                Path('package-lock.json').unlink()
        for marker, expected in (('bun@1.3.3', True), ('npm@10', False), ('bun@', False), (None, False)):
            Path('package.json').write_text(json.dumps({'packageManager': marker}))
            self.assertEqual(self.manager.detect(), expected)
        Path('package.json').unlink()
        Path('bun.lock').touch()
        self.assertFalse(self.manager.detect())

    def test_ambiguity_with_uv(self):
        Path('bun.lock').touch()
        Path('package-lock.json').touch()
        Path('pyproject.toml').touch()
        Path('uv.lock').touch()
        with self.assertRaisesRegex(Error, 'uv, bun'):
            pm_selector.select()

    def test_invalid_manifest(self):
        for content in ('{', '[]', '{}'):
            Path('package.json').write_text(content)
            self.assertFalse(self.manager.detect())
            with self.assertRaises(Error):
                self.manager.get_version()

    def test_missing_executable(self):
        Path('bun.lock').touch()
        Path('package-lock.json').touch()
        def command(*args):
            return {('git', 'rev-parse', '--show-toplevel'): str(Path.cwd()),
                    ('git', 'symbolic-ref', '--short', 'HEAD'): 'main'}.get(args, '')
        with patch.object(git, 'run', side_effect=command) as native, \
                patch('shutil.which', side_effect=lambda name: None if name == 'bun' else '/tool'):
            with self.assertRaisesRegex(Error, 'Required executable not found: bun'):
                git.check_preconditions()
            self.assertFalse(any(c.args[:2] == ('git', 'fetch') for c in native.call_args_list))

    def test_native_operations(self):
        Path('bun.lockb').touch()
        with patch('few_updater.tools.pm.bun.run') as native:
            self.manager.upgrade()
            self.assertEqual(native.call_args_list, [call('bun', 'update', capture_output=False)])
        for level in ('major', 'minor', 'patch'):
            with patch('few_updater.tools.pm.bun.run') as native:
                self.manager.bump(level)
                self.assertEqual(native.call_args_list, [
                    call('bun', 'pm', 'version', level, '--no-git-tag-version', capture_output=False),
                    call('bun', 'install', '--lockfile-only', capture_output=False)])

    def test_failure_stops_lock_sync(self):
        with patch('few_updater.tools.pm.bun.run', side_effect=Error('failed')) as native:
            with self.assertRaises(Error):
                self.manager.bump('patch')
            self.assertEqual(native.call_count, 1)

    def test_new_lock_stops_publication(self):
        def command(*args, **kwargs):
            Path('bun.lock').touch()
        with patch('few_updater.tools.pm.bun.run', side_effect=command), \
                patch.object(git, 'commit') as commit:
            with self.assertRaisesRegex(Error, 'new untracked files'):
                upgrade(self.manager)
            commit.assert_not_called()

    def test_workflow_confirmation_and_atomic_release(self):
        Path('bun.lock').touch()
        def command(*args, **kwargs):
            if args[:3] == ('bun', 'pm', 'version'):
                Path('package.json').write_text('{"version":"1.2.4"}')
        with contextlib.redirect_stdout(io.StringIO()), \
                patch('few_updater.tools.pm.bun.run', side_effect=command) as native, \
                patch.object(git, 'changed_files', return_value=['bun.lock', 'package.json']), \
                patch.object(git, 'already_released', return_value=False), \
                patch.object(git, 'check_tag_available'), patch.object(git, 'commit') as commit, \
                patch('few_updater.workflows.release.run') as publication:
            decline = Mock(return_value=False)
            bump(self.manager, 'patch', decline)
            decline.assert_called_once()
            native.assert_not_called()
            confirm = Mock(return_value=True)
            release(self.manager, 'patch', confirm)
            confirm.assert_called_once()
            commit.assert_called_once_with(['bun.lock', 'package.json'], 'build: bump version', capture_output=False)
            self.assertEqual(publication.call_args_list, [
                call('git', 'tag', '-a', '1.2.4', '-m', '1.2.4'),
                call('git', 'push', '--atomic', 'origin', 'main', '1.2.4', capture_output=False)])

    def test_no_bump_release_never_runs_bun(self):
        with contextlib.redirect_stdout(io.StringIO()), \
                patch('few_updater.tools.pm.bun.run') as native, \
                patch.object(git, 'already_released', return_value=False), \
                patch.object(git, 'check_tag_available') as available, \
                patch.object(git, 'changed_files', return_value=[]), \
                patch.object(git, 'commit') as commit, \
                patch('few_updater.workflows.release.run') as publication:
            confirm = Mock(return_value=True)
            release(self.manager, None, confirm)
            confirm.assert_called_once()
            available.assert_called_once_with('1.2.3')
            native.assert_not_called()
            commit.assert_not_called()
            self.assertEqual(publication.call_args_list[-1],
                             call('git', 'push', '--atomic', 'origin', 'main', '1.2.3', capture_output=False))

    def test_lock_sync_failure_preserves_manifest_and_stops_release(self):
        Path('bun.lock').touch()
        def command(*args, **kwargs):
            if args[:3] == ('bun', 'pm', 'version'):
                Path('package.json').write_text('{"version":"1.2.4"}')
            else:
                raise Error('lock sync failed')
        with contextlib.redirect_stdout(io.StringIO()), \
                patch('few_updater.tools.pm.bun.run', side_effect=command), \
                patch.object(git, 'already_released', return_value=False), \
                patch.object(git, 'commit') as commit, \
                patch('few_updater.workflows.release.run') as publication:
            with self.assertRaisesRegex(Error, 'lock sync failed'):
                release(self.manager, 'patch', Mock(return_value=True))
            self.assertEqual(self.manager.get_version(), '1.2.4')
            commit.assert_not_called()
            publication.assert_not_called()
