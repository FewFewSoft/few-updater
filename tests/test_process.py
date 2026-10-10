"""Verify terminal inheritance and error handling for native command output."""

import subprocess
import unittest
from unittest.mock import patch

from few_updater.process import Error, run


class ProcessTests(unittest.TestCase):
    def test_inherit_terminal_streams(self):
        for args in (
            ('uv', 'lock', '--upgrade'),
            ('npm', 'update'),
            ('npm', 'version', 'patch', '--no-git-tag-version'),
            ('git', 'commit', '-m', 'build: update dependencies'),
            ('git', 'push', 'origin', 'main'),
            ('uv', 'version', '--bump', 'patch'),
            ('git', 'commit', '-m', 'build: bump version'),
            ('git', 'push', '--atomic', 'origin', 'main', '1.2.4'),
        ):
            with self.subTest(args=args):
                with patch('few_updater.process.subprocess.run',
                           return_value=subprocess.CompletedProcess(args, 0)) as command:
                    self.assertEqual(run(*args, capture_output=False), '')
                command.assert_called_once_with(args, capture_output=False, text=True)

    def test_inherited_streams_failure(self):
        args = ('uv', 'lock', '--upgrade')
        with patch('few_updater.process.subprocess.run',
                   return_value=subprocess.CompletedProcess(args, 2)):
            with self.assertRaisesRegex(Error, r'uv lock --upgrade failed \(2\)'):
                run(*args, capture_output=False)

    def test_capture_remains_default(self):
        args = ('uv', 'version', '--short')
        with patch('few_updater.process.subprocess.run',
                   return_value=subprocess.CompletedProcess(args, 0, '1.2.3\n', '')) as command:
            self.assertEqual(run(*args), '1.2.3\n')
        command.assert_called_once_with(args, capture_output=True, text=True)

    def test_captured_error_keeps_diagnostic(self):
        args = ('uv', 'version', '--bump', 'patch')
        with patch('few_updater.process.subprocess.run',
                   return_value=subprocess.CompletedProcess(args, 1, '', 'uv diagnostic\n')):
            with self.assertRaisesRegex(Error, 'uv diagnostic'):
                run(*args)
