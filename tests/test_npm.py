import json
from pathlib import Path
import sys
from unittest.mock import patch

from few_updater.tools import git, pm_selector as project
from few_updater.tools.pm.npm import Npm
npm = Npm()
from few_updater.tools.process import Error, run
from test_workflows import RepositoryTest


class DetectionTests(RepositoryTest):
    def test_uv(self):
        self.assertEqual(project.select().name, 'uv')

    def test_both(self):
        Path('package.json').write_text('{}')
        Path('package-lock.json').write_text('{}')
        self.assertEqual(self.invoke('upgrade'), 1)
        self.assertIn('Ambiguous', self.output)
        self.assert_no_commit()

    def test_incomplete_sets(self):
        Path('uv.lock').unlink()
        Path('package.json').write_text('{}')
        with self.assertRaisesRegex(Error, 'No supported project'):
            project.select().name

    def test_partial_other_set(self):
        Path('package.json').write_text('{}')
        self.assertEqual(project.select().name, 'uv')

    def test_no_set(self):
        Path('uv.lock').unlink()
        Path('pyproject.toml').unlink()
        with self.assertRaisesRegex(Error, 'No supported project'):
            project.select().name


class NpmTests(RepositoryTest):
    def setUp(self):
        super().setUp()
        run('git', 'rm', 'pyproject.toml', 'uv.lock')
        self.write_package('1.2.3')
        run('git', 'add', '--', 'package.json', 'package-lock.json')
        run('git', 'commit', '-m', 'npm project')
        run('git', 'push', 'origin', 'main')
        self.initial = run('git', 'rev-parse', 'HEAD')
        self.mode = 'normal'

    def write_package(self, version):
        Path('package.json').write_text(json.dumps({'name': 'test', 'version': version,
                                                   'dependencies': {'example': '^1.0.0'}}))
        Path('package-lock.json').write_text(json.dumps({'version': version, 'lockfileVersion': 3}))

    def command(self, *args, capture_output=True):
        if args[0] != 'npm':
            return super().command(*args, capture_output=capture_output)
        self.calls.append(args)
        self.assertFalse(capture_output)
        if args == ('npm', 'version', 'patch', '--no-git-tag-version'):
            self.input.assert_called_once()
            self.assertIn('Bumping version...', sys.stdout.getvalue())
        else:
            self.assertEqual(args, ('npm', 'update'))
        if self.fail and args[:len(self.fail)] == self.fail:
            Path('package-lock.json').write_text('partial write')
            raise Error('Simulated npm failure')
        Path('node_modules').mkdir(exist_ok=True)
        Path('node_modules/local').write_text('npm managed')
        if self.mode == 'unchanged':
            return ''
        if args[1] == 'version':
            self.write_package('1.2.5' if self.mode == 'wrong-version' else '1.2.4')
        else:
            if self.mode != 'manifest-only':
                Path('package-lock.json').write_text('{"updated": true}')
            if self.mode in ('both', 'manifest-only'):
                with Path('package.json').open('a') as stream:
                    stream.write('\n')
        if self.mode == 'unexpected':
            Path('app.py').write_text('unexpected tracked change')
        return ''

    def test_detection_and_executable(self):
        self.assertEqual(project.select().name, 'npm')
        with patch('shutil.which', side_effect=lambda name: None if name == 'uv' else '/bin/tool'):
            self.assertEqual(git.check_preconditions(allow_untracked=True).name, 'npm')
        with patch('shutil.which', side_effect=lambda name: None if name == 'npm' else '/bin/tool'):
            with self.assertRaisesRegex(Error, 'npm'):
                git.check_preconditions(allow_untracked=True)

    def test_upgrade(self):
        self.mode = 'both'
        before = json.loads(Path('package.json').read_text())['dependencies']
        self.assertEqual(self.invoke('upgrade'), 0)
        self.input.assert_not_called()
        self.assertEqual(json.loads(Path('package.json').read_text())['dependencies'], before)
        self.assertEqual([c for c in self.calls if c[:2] == ('git', 'add')],
                         [('git', 'add', '--', 'package-lock.json', 'package.json')])
        self.assertEqual(run('git', 'log', '-1', '--format=%s').strip(), 'build: update dependencies')
        self.assertEqual(run('git', 'ls-files', 'node_modules'), '')
        self.assertIn(('git', 'push', 'origin', 'main'), self.calls)
        self.assertEqual(run('git', 'tag').strip(), '1.2.3')

    def test_upgrade_lock_only(self):
        self.assertEqual(self.invoke('upgrade'), 0)
        self.assertIn(('git', 'add', '--', 'package-lock.json'), self.calls)

    def test_upgrade_manifest_only(self):
        self.mode = 'manifest-only'
        self.assertEqual(self.invoke('upgrade'), 0)
        self.assertIn(('git', 'add', '--', 'package.json'), self.calls)

    def test_upgrade_unchanged(self):
        self.mode = 'unchanged'
        self.assertEqual(self.invoke('upgrade'), 0)
        self.assertIn('Dependencies already up to date', self.output)
        self.assert_no_commit()

    def test_release(self):
        Path('local.txt').write_text('untracked')
        self.assertEqual(self.invoke('release'), 0)
        self.input.assert_called_once()
        self.assertEqual(npm.get_version(), '1.2.4')
        self.assertIn(('npm', 'version', 'patch', '--no-git-tag-version'), self.calls)
        self.assertEqual([c for c in self.calls if c[:2] == ('git', 'add')],
                         [('git', 'add', '--', 'package-lock.json', 'package.json')])
        self.assertEqual(run('git', 'log', '-1', '--format=%s').strip(), 'build: bump version')
        self.assertEqual(run('git', 'cat-file', '-t', '1.2.4').strip(), 'tag')
        self.assertEqual(run('git', 'for-each-ref', '--format=%(contents)', 'refs/tags/1.2.4').strip(), '1.2.4')
        self.assertIn(('git', 'push', '--atomic', 'origin', 'main', '1.2.4'), self.calls)
        self.assertEqual(run('git', '--git-dir=' + str(self.remote), 'rev-parse', 'main'), run('git', 'rev-parse', 'HEAD'))
        self.assertEqual(run('git', '--git-dir=' + str(self.remote), 'rev-parse', '1.2.4'), run('git', 'rev-parse', '1.2.4'))
        self.assertEqual(run('git', 'ls-files', 'node_modules', 'local.txt'), '')

    def test_release_already_done(self):
        run('git', 'tag', '-a', '1.2.4', '-m', '1.2.4')
        self.assertEqual(self.invoke('release'), 0)
        self.assertFalse(any(c[0] == 'npm' for c in self.calls))
        self.assert_no_commit()

    def test_release_refusal(self):
        self.assertEqual(self.invoke('release', 'n'), 0)
        self.assertFalse(any(c[0] == 'npm' for c in self.calls))
        self.assert_no_commit()

    def test_target_tag_exists(self):
        run('git', 'tag', '1.2.4')
        self.assertEqual(self.invoke('release'), 1)
        self.input.assert_called_once()
        self.assert_no_commit()

    def test_invalid_versions(self):
        for value in ('1.2', 'v1.2.3', '1.2.3-beta', None, 123):
            Path('package.json').write_text(json.dumps({'version': value}))
            with self.subTest(value=value), self.assertRaises(Error):
                npm.get_version()
        for invalid in ('{', '[]', '{}'):
            Path('package.json').write_text(invalid)
            with self.subTest(invalid=invalid), self.assertRaises(Error):
                npm.get_version()

    def test_unchanged_bump(self):
        self.mode = 'unchanged'
        self.assertEqual(self.invoke('release'), 1)
        self.assert_no_commit()

    def test_failure_paths(self):
        for workflow, failure in (
            ('upgrade', ('npm', 'update')), ('release', ('npm', 'version')),
            ('upgrade', ('git', 'commit')), ('release', ('git', 'commit')),
        ):
            with self.subTest(workflow=workflow, failure=failure):
                self.calls.clear()
                self.fail = failure
                self.assertEqual(self.invoke(workflow), 1)
                self.assert_no_commit()
                self.assertTrue(run('git', 'status', '--porcelain'))
                run('git', 'restore', '--staged', '--worktree', 'package.json', 'package-lock.json')

    def test_tag_failure(self):
        self.fail = ('git', 'tag', '-a')
        self.assertEqual(self.invoke('release'), 1)
        self.assert_no_push()
        self.assertNotEqual(run('git', 'rev-parse', 'HEAD'), self.initial)

    def test_release_push_failure(self):
        hook = self.remote / 'hooks' / 'pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o755)
        self.assertEqual(self.invoke('release'), 1)
        self.assertEqual(run('git', 'cat-file', '-t', '1.2.4').strip(), 'tag')
        self.assertEqual(run('git', '--git-dir=' + str(self.remote), 'rev-parse', 'main'), self.initial)
        self.assertNotIn('1.2.4', run('git', '--git-dir=' + str(self.remote), 'tag'))

    def test_upgrade_push_failure(self):
        self.fail = ('git', 'push')
        self.assertEqual(self.invoke('upgrade'), 1)
        self.assertNotEqual(run('git', 'rev-parse', 'HEAD'), self.initial)

    def test_unexpected_tracked_changes(self):
        self.mode = 'unexpected'
        self.assertEqual(self.invoke('upgrade'), 1)
        self.assert_no_commit()

    def test_release_unexpected_tracked_changes(self):
        self.mode = 'unexpected'
        self.assertEqual(self.invoke('release'), 1)
        self.assert_no_commit()
        self.assertEqual(Path('app.py').read_text(), 'unexpected tracked change')

    def test_dirty_index_and_worktree(self):
        Path('app.py').write_text('dirty')
        for staged in (False, True):
            if staged:
                run('git', 'add', 'app.py')
            self.assertEqual(self.invoke('release'), 1)
            self.assert_no_commit()
            self.assertFalse(any(c[0] == 'npm' for c in self.calls))

    def test_standalone_bump(self):
        self.assertEqual(self.invoke('bump patch'), 0)
        self.input.assert_called_once()
        self.assertEqual(npm.get_version(), '1.2.4')
        self.assert_no_commit()
        self.assertEqual(run('git', 'tag').strip(), '1.2.3')
        self.assertEqual(run('git', 'diff', '--name-only').splitlines(),
                         ['package-lock.json', 'package.json'])

    def test_no_bump_with_local_version_changes(self):
        self.write_package('1.2.4')
        self.assertEqual(self.invoke('release --no-bump'), 0)
        self.input.assert_called_once()
        self.assertFalse(any(c[0] == 'npm' for c in self.calls))
        self.assertIn(('git', 'push', '--atomic', 'origin', 'main', '1.2.4'), self.calls)

    def test_no_bump_without_changes(self):
        self.write_package('1.2.4')
        run('git', 'add', '--', 'package.json', 'package-lock.json')
        run('git', 'commit', '-m', 'version prepared')
        run('git', 'push', 'origin', 'main')
        self.initial = run('git', 'rev-parse', 'HEAD')
        self.assertEqual(self.invoke('release --no-bump'), 0)
        self.assertEqual(run('git', 'rev-parse', 'HEAD'), self.initial)
        self.assertFalse(any(c[:2] == ('git', 'commit') for c in self.calls))
        self.input.assert_called_once()
