import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from few_updater import cli, git, uv
from few_updater.process import Error, run


class RepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.previous = Path.cwd()
        self.addCleanup(os.chdir, self.previous)
        # Isolate identity, signing, hooks and configuration from the developer.
        self.env = patch.dict(os.environ, {
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.invalid',
            'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.invalid',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.remote = self.base / 'origin.git'
        run('git', 'init', '--bare', '--initial-branch=main', str(self.remote))
        self.repo = self.base / 'project'
        run('git', 'init', '--initial-branch=main', str(self.repo))
        os.chdir(self.repo)
        Path('pyproject.toml').write_text('[project]\nname = "test"\nversion = "1.2.3"\n')
        Path('uv.lock').write_text('initial lock\n')
        Path('app.py').write_text('print("hello")\n')
        run('git', 'add', '.')
        run('git', 'commit', '-m', 'initial')
        run('git', 'tag', '-a', '1.2.3', '-m', '1.2.3')
        run('git', 'remote', 'add', 'origin', str(self.remote))
        run('git', 'push', 'origin', 'main', '--tags')
        self.initial = run('git', 'rev-parse', 'HEAD')
        self.calls = []
        self.fail = None
        self.uv_mode = 'normal'
        self.current = '1.2.3'

    def command(self, *args, capture_output=True):
        self.calls.append(args)
        native_commands = {
            ('uv', 'lock', '--upgrade'),
            ('git', 'commit', '-m', 'build: update dependencies'),
            ('git', 'push', 'origin', 'main'),
            ('uv', 'version', '--bump', 'patch'),
            ('git', 'commit', '-m', 'build: bump version'),
            ('git', 'push', '--atomic', 'origin', 'main', '1.2.4'),
        }
        self.assertEqual(capture_output, args not in native_commands)
        if args == ('git', 'commit', '-m', 'build: update dependencies'):
            self.assertIn('Committing dependency updates...\n', sys.stdout.getvalue())
            self.assertNotIn('Pushing to origin/main...', sys.stdout.getvalue())
        if args == ('git', 'push', 'origin', 'main'):
            self.assertIn('Pushing to origin/main...\n', sys.stdout.getvalue())
        release_steps = [
            (('uv', 'version', '--bump', 'patch'), 'Bumping version...'),
            (('git', 'commit', '-m', 'build: bump version'), 'Committing version bump...'),
            (('git', 'tag', '-a', '1.2.4', '-m', '1.2.4'), 'Creating annotated tag 1.2.4...'),
            (('git', 'push', '--atomic', 'origin', 'main', '1.2.4'), 'Pushing main and 1.2.4 atomically...'),
        ]
        for index, (command, message) in enumerate(release_steps):
            if args == command:
                self.input.assert_called_once()
                self.assertIn(message + '\n', sys.stdout.getvalue())
                for _, later_message in release_steps[index + 1:]:
                    self.assertNotIn(later_message, sys.stdout.getvalue())
        if self.fail and args[:len(self.fail)] == self.fail:
            if args[0] == 'uv':
                Path('uv.lock').write_text('partial uv write\n')
            raise Error('Simulated failure: ' + ' '.join(args))
        if args[0] != 'uv':
            return run(*args)
        if args == ('uv', 'version', '--short'):
            return self.current + '\n'
        if args == ('uv', 'lock', '--upgrade'):
            if self.uv_mode != 'unchanged':
                Path('uv.lock').write_text('upgraded lock\n')
        elif args == ('uv', 'version', '--bump', 'patch'):
            self.current = '1.2.5' if self.uv_mode == 'wrong-version' else '1.2.4'
            Path('pyproject.toml').write_text(f'[project]\nname = "test"\nversion = "{self.current}"\n')
            Path('uv.lock').write_text('bumped lock\n')
        else:
            self.failTest(f'Unexpected uv command: {args}')
        if self.uv_mode == 'unexpected':
            Path('app.py').write_text('unexpected\n')
        return ''

    def invoke(self, command, answer='y'):
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            for module in (cli, git, uv):
                stack.enter_context(patch.object(module, 'run', side_effect=self.command))
            stack.enter_context(patch('shutil.which', return_value='/test/executable'))
            stack.enter_context(contextlib.redirect_stdout(output))
            stack.enter_context(contextlib.redirect_stderr(output))
            stack.enter_context(patch.object(output, 'isatty', return_value=True))
            stack.enter_context(patch('sys.stdin.isatty', return_value=True))
            self.input = stack.enter_context(patch('builtins.input', return_value=answer))
            result = cli.main([command])
        self.output = output.getvalue()
        return result

    def new_commit(self):
        Path('app.py').write_text('print("new")\n')
        run('git', 'add', 'app.py')
        run('git', 'commit', '-m', 'feature')
        run('git', 'push', 'origin', 'main')
        self.initial = run('git', 'rev-parse', 'HEAD')

    def assert_no_push(self):
        self.assertFalse(any(call[:2] == ('git', 'push') for call in self.calls))

    def assert_no_commit(self):
        self.assertEqual(run('git', 'rev-parse', 'HEAD'), self.initial)
        self.assert_no_push()


class GitTests(RepositoryTest):
    def test_invalid_repository(self):
        os.chdir(self.base)
        self.assertEqual(self.invoke('upgrade'), 1)

    def test_not_root(self):
        Path('sub').mkdir()
        os.chdir('sub')
        self.assertEqual(self.invoke('upgrade'), 1)

    def test_wrong_branch(self):
        run('git', 'checkout', '-b', 'feature')
        self.assertEqual(self.invoke('upgrade'), 1)

    def test_detached_head(self):
        run('git', 'checkout', '--detach')
        self.assertEqual(self.invoke('upgrade'), 1)

    def test_dirty_worktree(self):
        Path('app.py').write_text('dirty')
        self.assertEqual(self.invoke('upgrade'), 1)

    def test_dirty_index(self):
        Path('app.py').write_text('dirty')
        run('git', 'add', 'app.py')
        self.assertEqual(self.invoke('upgrade'), 1)

    def test_release_already_done_with_untracked(self):
        Path('new').write_text('dirty')
        self.assertEqual(self.invoke('release'), 0)
        self.assertFalse(any(call[0] == 'uv' for call in self.calls))
        self.input.assert_not_called()
        self.assert_no_commit()
        self.assertEqual(Path('new').read_text(), 'dirty')

    def test_no_origin(self):
        run('git', 'remote', 'remove', 'origin')
        self.assertEqual(self.invoke('upgrade'), 1)

    def test_fetch_failure(self):
        self.fail = ('git', 'fetch')
        self.assertEqual(self.invoke('upgrade'), 1)
        self.assert_no_commit()

    def test_ahead(self):
        run('git', 'commit', '--allow-empty', '-m', 'ahead')
        self.assertEqual(self.invoke('upgrade'), 1)

    def test_behind(self):
        clone = self.base / 'clone'
        run('git', 'clone', str(self.remote), str(clone))
        run('git', '-C', str(clone), 'commit', '--allow-empty', '-m', 'ahead')
        run('git', '-C', str(clone), 'push', 'origin', 'main')
        self.assertEqual(self.invoke('upgrade'), 1)

    def test_missing_remote_main(self):
        run('git', '--git-dir=' + str(self.remote), 'update-ref', '-d', 'refs/heads/main')
        run('git', 'update-ref', '-d', 'refs/remotes/origin/main')
        self.assertEqual(self.invoke('upgrade'), 1)

    def test_stale_remote_main(self):
        run('git', '--git-dir=' + str(self.remote), 'update-ref', '-d', 'refs/heads/main')
        self.assertEqual(self.invoke('upgrade'), 1)
        self.assert_no_commit()

    def test_missing_files(self):
        for filename in ('uv.lock', 'pyproject.toml'):
            with self.subTest(filename=filename):
                contents = Path(filename).read_text()
                Path(filename).unlink()
                run('git', 'add', filename)
                run('git', 'commit', '-m', 'remove')
                self.assertEqual(self.invoke('upgrade'), 1)
                Path(filename).write_text(contents)
                run('git', 'add', filename)
                run('git', 'commit', '-m', 'restore')

    def test_missing_executables(self):
        for executable in ('git', 'uv'):
            with self.subTest(executable=executable):
                with patch('shutil.which', side_effect=lambda x: None if x == executable else '/bin/git'):
                    with self.assertRaisesRegex(Error, executable):
                        git.check_preconditions()

    def test_annotated_tag_and_new_commits(self):
        self.assertTrue(git.already_released())
        self.new_commit()
        self.assertFalse(git.already_released())

    def test_no_annotated_tag(self):
        run('git', 'tag', '-d', '1.2.3')
        run('git', 'tag', '1.2.3')
        with self.assertRaises(Error):
            git.already_released()

    def test_bad_description(self):
        for value in ('v1.2.3', '1.2', '1.2.3rc1', '01.2.3', '1.2.3-0-gabc', '1.2.3-1-gxyz'):
            with self.subTest(value=value), patch.object(git, 'run', return_value=value):
                with self.assertRaises(Error):
                    git.already_released()


class UpgradeTests(RepositoryTest):
    def test_untracked_with_lock_update(self):
        Path('notes').mkdir()
        Path('notes/local.txt').write_text('keep locally')
        self.assertEqual(self.invoke('upgrade'), 0)
        self.assertEqual(Path('notes/local.txt').read_text(), 'keep locally')
        self.assertEqual(run('git', 'ls-files', '--', 'notes/local.txt'), '')
        self.assertEqual(run('git', 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').strip(), 'uv.lock')
        self.assertIn(('git', 'push', 'origin', 'main'), self.calls)

    def test_untracked_without_lock_update(self):
        Path('local.txt').write_text('keep locally')
        self.uv_mode = 'unchanged'
        self.assertEqual(self.invoke('upgrade'), 0)
        self.assertIn('Dependencies already up to date', self.output)
        self.assert_no_commit()
        self.assertEqual(Path('local.txt').read_text(), 'keep locally')

    def test_untracked_does_not_allow_tracked_changes(self):
        Path('local.txt').write_text('keep locally')
        Path('app.py').write_text('dirty tracked file')
        for staged in (False, True):
            with self.subTest(staged=staged):
                if staged:
                    run('git', 'add', 'app.py')
                self.assertEqual(self.invoke('upgrade'), 1)
                self.assertFalse(any(call[0] == 'uv' for call in self.calls))
                self.assert_no_commit()

    def test_no_change(self):
        self.uv_mode = 'unchanged'
        self.assertEqual(self.invoke('upgrade'), 0)
        self.assertIn('Dependencies already up to date', self.output)
        self.assertNotIn('Committing dependency updates...', self.output)
        self.assertNotIn('Pushing to origin/main...', self.output)
        self.input.assert_not_called()
        self.assert_no_commit()

    def test_success(self):
        self.assertEqual(self.invoke('upgrade'), 0)
        self.input.assert_not_called()
        self.assertNotIn('+upgraded lock', self.output)
        self.assertFalse(any(call[0] == 'git' and 'diff' in call for call in self.calls))
        self.assertEqual(run('git', 'log', '-1', '--format=%s').strip(), 'build: update dependencies')
        self.assertEqual(run('git', 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').strip(), 'uv.lock')
        self.assertEqual(run('git', 'rev-parse', 'HEAD'), run('git', '--git-dir=' + str(self.remote), 'rev-parse', 'main'))
        self.assertEqual(run('git', 'tag').strip(), '1.2.3')
        self.assertLess(self.calls.index(('git', 'commit', '-m', 'build: update dependencies')), self.calls.index(('git', 'push', 'origin', 'main')))

    def test_uv_failure(self):
        self.fail = ('uv', 'lock')
        self.assertEqual(self.invoke('upgrade'), 1)
        self.assert_no_commit()
        self.assertEqual(Path('uv.lock').read_text(), 'partial uv write\n')

    def test_commit_failure(self):
        self.fail = ('git', 'commit')
        self.assertEqual(self.invoke('upgrade'), 1)
        self.assert_no_commit()
        self.assertTrue(run('git', 'diff', '--cached'))
        self.assertNotIn('Pushing to origin/main...', self.output)

    def test_push_failure(self):
        self.fail = ('git', 'push')
        self.assertEqual(self.invoke('upgrade'), 1)
        self.assertNotEqual(run('git', 'rev-parse', 'HEAD'), self.initial)
        self.assertIn('No rollback', self.output)

    def test_unexpected_files(self):
        self.uv_mode = 'unexpected'
        self.assertEqual(self.invoke('upgrade'), 1)
        self.assert_no_commit()
        self.assertEqual(Path('app.py').read_text(), 'unexpected\n')


class ReleaseTests(RepositoryTest):
    def test_untracked_excluded_from_release(self):
        self.new_commit()
        Path('notes').mkdir()
        Path('notes/local.txt').write_text('keep locally')
        self.assertEqual(self.invoke('release'), 0)
        self.input.assert_called_once()
        self.assertEqual(Path('notes/local.txt').read_text(), 'keep locally')
        self.assertEqual(run('git', 'ls-files', '--', 'notes/local.txt'), '')
        self.assertEqual(set(run('git', 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').splitlines()), {'pyproject.toml', 'uv.lock'})
        adds = [call for call in self.calls if call[:2] == ('git', 'add')]
        self.assertEqual(adds, [('git', 'add', '--', 'pyproject.toml', 'uv.lock')])
        self.assertEqual(run('git', 'cat-file', '-t', '1.2.4').strip(), 'tag')
        self.assertIn(('git', 'push', '--atomic', 'origin', 'main', '1.2.4'), self.calls)
        self.assertEqual(run('git', '--git-dir=' + str(self.remote), 'ls-tree', '-r', '--name-only', 'main', '--', 'notes'), '')

    def test_untracked_does_not_allow_tracked_changes(self):
        self.new_commit()
        Path('local.txt').write_text('keep locally')
        Path('app.py').write_text('dirty tracked file')
        for staged in (False, True):
            with self.subTest(staged=staged):
                if staged:
                    run('git', 'add', 'app.py')
                self.assertEqual(self.invoke('release'), 1)
                self.input.assert_not_called()
                self.assertFalse(any(call[0] == 'uv' for call in self.calls))
                self.assert_no_commit()

    progress = [
        'Bumping version...',
        'Committing version bump...',
        'Creating annotated tag 1.2.4...',
        'Pushing main and 1.2.4 atomically...',
    ]

    def test_already_released(self):
        self.assertEqual(self.invoke('release'), 0)
        self.input.assert_not_called()
        self.assertFalse(any(call[0] == 'uv' for call in self.calls))
        self.assert_no_commit()
        for message in self.progress:
            self.assertNotIn(message, self.output)

    def test_success(self):
        self.new_commit()
        self.assertEqual(self.invoke('release'), 0)
        self.input.assert_called_once()
        positions = [self.output.index(message) for message in self.progress]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(run('git', 'log', '-1', '--format=%s').strip(), 'build: bump version')
        self.assertEqual(run('git', 'cat-file', '-t', '1.2.4').strip(), 'tag')
        self.assertEqual(run('git', 'for-each-ref', '--format=%(contents)', 'refs/tags/1.2.4').strip(), '1.2.4')
        self.assertEqual(run('git', 'rev-list', '-1', '1.2.4'), run('git', 'rev-parse', 'HEAD'))
        self.assertIn(('git', 'push', '--atomic', 'origin', 'main', '1.2.4'), self.calls)
        self.assertEqual(run('git', '--git-dir=' + str(self.remote), 'rev-parse', 'main'), run('git', 'rev-parse', 'HEAD'))
        self.assertEqual(run('git', '--git-dir=' + str(self.remote), 'rev-parse', '1.2.4'), run('git', 'rev-parse', '1.2.4'))
        self.assertEqual(set(run('git', 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').splitlines()), {'pyproject.toml', 'uv.lock'})
        self.assertEqual(run('git', 'status', '--porcelain'), '')

    def test_patch(self):
        for current, expected in [('0.1.0', '0.1.1'), ('1.2.9', '1.2.10'), ('2.0.99', '2.0.100')]:
            self.assertEqual(uv.next_patch(current), expected)
        for invalid in ('1.2', 'v1.2.3', '1.2.3rc1', '1.2.03'):
            with self.assertRaises(Error):
                uv.next_patch(invalid)

    def test_refusal(self):
        self.new_commit()
        Path('local.txt').write_text('keep locally')
        self.assertEqual(self.invoke('release', 'n'), 0)
        self.assert_no_commit()
        self.assertEqual(run('git', 'status', '--porcelain'), '?? local.txt\n')
        self.assertEqual(Path('local.txt').read_text(), 'keep locally')
        for message in self.progress:
            self.assertNotIn(message, self.output)

    def test_existing_local_tag(self):
        self.new_commit()
        run('git', 'tag', '1.2.4')
        self.assertEqual(self.invoke('release'), 1)
        self.input.assert_not_called()
        self.assert_no_commit()

    def test_existing_remote_tag(self):
        self.new_commit()
        run('git', 'tag', '1.2.4')
        run('git', 'push', 'origin', '1.2.4')
        run('git', 'tag', '-d', '1.2.4')
        # Exercise the explicit remote check even if fetch cannot bring this tag in.
        with patch.object(git, 'run', side_effect=lambda *a: '' if a[:3] == ('git', 'tag', '--list') else run(*a)):
            with self.assertRaisesRegex(Error, 'origin'):
                git.check_tag_available('1.2.4')

    def test_failures_stop_publication(self):
        self.new_commit()
        for failure in [('uv', 'version', '--bump'), ('git', 'commit')]:
            with self.subTest(failure=failure):
                self.calls.clear()
                self.current = '1.2.3'
                self.fail = failure
                self.assertEqual(self.invoke('release'), 1)
                self.assert_no_commit()
                self.assertNotIn('1.2.4', run('git', 'tag'))
                self.assertNotIn(self.progress[2], self.output)
                self.assertNotIn(self.progress[3], self.output)
                if failure[0] == 'uv':
                    self.assertNotIn(self.progress[1], self.output)
                # Explicit test-fixture restoration, never application rollback.
                run('git', 'restore', '--staged', '--worktree', 'pyproject.toml', 'uv.lock')

    def test_tag_failure(self):
        self.new_commit()
        self.fail = ('git', 'tag', '-a')
        self.assertEqual(self.invoke('release'), 1)
        self.assert_no_push()
        self.assertNotEqual(run('git', 'rev-parse', 'HEAD'), self.initial)
        self.assertNotIn('1.2.4', run('git', 'tag'))
        self.assertNotIn(self.progress[3], self.output)

    def test_atomic_push_rejected(self):
        self.new_commit()
        hook = self.remote / 'hooks' / 'pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o755)
        self.assertEqual(self.invoke('release'), 1)
        self.assertNotEqual(run('git', 'rev-parse', 'HEAD'), self.initial)
        self.assertEqual(run('git', 'cat-file', '-t', '1.2.4').strip(), 'tag')
        self.assertEqual(run('git', '--git-dir=' + str(self.remote), 'rev-parse', 'main'), self.initial)
        self.assertNotIn('1.2.4', run('git', '--git-dir=' + str(self.remote), 'tag'))
        self.assertIn('git push --atomic origin main 1.2.4', self.output)

    def test_wrong_bump(self):
        self.new_commit()
        self.uv_mode = 'wrong-version'
        self.assertEqual(self.invoke('release'), 1)
        self.assert_no_commit()

    def test_unexpected_files(self):
        self.new_commit()
        self.uv_mode = 'unexpected'
        self.assertEqual(self.invoke('release'), 1)
        self.assert_no_commit()


class CliTests(unittest.TestCase):
    def test_tty_required(self):
        with patch('sys.stdin.isatty', return_value=False), patch('sys.stderr', new_callable=io.StringIO):
            with patch.object(git, 'check_preconditions') as check:
                self.assertEqual(cli.main(['upgrade']), 1)
                check.assert_not_called()

    def test_help_without_tty(self):
        for args in (['--help'], ['upgrade', '--help'], ['release', '--help']):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as error:
                cli.main(args)
            self.assertEqual(error.exception.code, 0)

    def test_confirmation_default(self):
        for answer in ('', 'n', 'no', 'anything'):
            with patch('builtins.input', return_value=answer):
                self.assertFalse(cli.confirm('Proceed?'))
        with patch('builtins.input', return_value='YES'):
            self.assertTrue(cli.confirm('Proceed?'))


if __name__ == '__main__':
    unittest.main()
