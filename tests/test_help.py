"""Help explains each workflow without running commands or requiring a TTY."""

import contextlib
import io
import unittest
from unittest.mock import patch

from few_updater import cli


class HelpTests(unittest.TestCase):
    def help_text(self, *args):
        output = io.StringIO()
        with patch('sys.stdin.isatty', return_value=False), \
                patch.object(cli.git, 'check_preconditions') as check, \
                patch.object(cli, 'upgrade') as upgrade, \
                patch.object(cli, 'release') as release, \
                contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as result:
                cli.main([*args, '--help'])
            self.assertEqual(result.exception.code, 0)
            check.assert_not_called()
            upgrade.assert_not_called()
            release.assert_not_called()
        return ' '.join(output.getvalue().split())

    def test_main_help(self):
        text = self.help_text()
        for expected in ('uv and npm', 'upgrade', 'release', 'automatically commit',
                         'Confirm a patch bump', 'atomically'):
            self.assertIn(expected, text)

    def test_common_requirements(self):
        for command in ('upgrade', 'release'):
            with self.subTest(command=command):
                text = self.help_text(command)
                for expected in ('Automatically detect uv or npm', 'pyproject.toml + uv.lock',
                                 'package.json + package-lock.json', 'Both complete sets',
                                 'interactive terminal (TTY)', 'repository root, on main',
                                 'index and tracked working-tree files must be clean',
                                 'Untracked files are allowed and never staged',
                                 'git fetch origin', 'HEAD must match origin/main exactly',
                                 'without automatic rollback'):
                    self.assertIn(expected, text)

    def test_upgrade_help(self):
        text = self.help_text('upgrade')
        for expected in ('within existing version constraints', 'uv lock --upgrade',
                         'npm update', 'build: update dependencies', 'git push origin main',
                         'No changes means success without a commit or push',
                         'No confirmation required', 'no diff displayed'):
            self.assertIn(expected, text)

    def test_release_help(self):
        text = self.help_text('release')
        for expected in ('next patch version', 'explicit user confirmation once (default: no)',
                         'uv version --bump patch', 'npm version patch --no-git-tag-version',
                         'build: bump version', 'annotated Git tag X.Y.Z (no v prefix)',
                         'git push --atomic origin main X.Y.Z',
                         'Declining confirmation makes no changes'):
            self.assertIn(expected, text)
