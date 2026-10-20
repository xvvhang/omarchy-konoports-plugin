import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import collect


class DiscoveryTests(unittest.TestCase):
    def test_short_framework_command(self):
        argv = ['/home/user/.local/node/bin/node', '/app/node_modules/@vendor/vite/node/cli.js', 'dev', '--force']
        self.assertEqual(collect.display_command(argv), 'vite dev --force')
        self.assertEqual(collect.display_command(['/usr/bin/node', '/app/node_modules/next/dist/bin/next', 'dev']), 'next dev')

    def test_short_command_keeps_arguments(self):
        self.assertEqual(collect.display_command(['/usr/bin/node', '/app/server.js', '--root', '/some/project']), 'node server.js --root /some/project')
        self.assertEqual(collect.display_command(['/usr/bin/python3', '-m', 'http.server', '8000']), 'python3 -m http.server 8000')
        self.assertEqual(collect.display_command(['/usr/bin/node', '--inspect', '/app/server.js']), 'node --inspect /app/server.js')
        self.assertEqual(collect.display_command(['/app/target/debug/server', '--config', '/app/dev.toml']), 'server --config /app/dev.toml')
        self.assertEqual(collect.display_command(['/usr/bin/python3', '/app/my server.py']), "python3 'my server.py'")
        self.assertEqual(collect.display_command([]), '')

    def test_frameworks(self):
        self.assertEqual(collect.classify(['node', '/app/vite/bin/vite.js'], ''), 'Vite')
        self.assertEqual(collect.classify(['python3', '-m', 'http.server'], ''), 'Python HTTP')
        self.assertEqual(collect.classify(['python3', '-m', 'uvicorn', 'app:app'], ''), 'FastAPI / ASGI')

    def test_internal_tools_excluded(self):
        for argv in [['opencode', 'serve'], ['codex'], ['claude'],
                     ['node', '/usr/lib/typescript-language-server/cli.js'],
                     ['quickshell'], ['chrome']]:
            self.assertIsNone(collect.classify(argv, '/tmp'))

    def test_custom_project(self):
        with tempfile.TemporaryDirectory(prefix='konoports-', dir='/tmp/opencode') as directory:
            Path(directory, 'Cargo.toml').touch()
            self.assertEqual(collect.classify(['./target/debug/server'], directory), 'server')
        self.assertIsNone(collect.classify(['sshd'], ''))

    def test_internal_names_in_arguments_are_not_programs(self):
        self.assertEqual(collect.classify(['python3', '-u', '-m', 'http.server', '8765', '--directory', '/tmp/opencode'], ''), 'Python HTTP')
        self.assertEqual(collect.classify(['node', '/home/opencode/project/server.js', '--root', '/tmp/code'], ''), 'node')
        self.assertIsNone(collect.classify(['node', '/app/bin/opencode.js'], ''))

    def test_urls(self):
        self.assertEqual(collect.local_url('0.0.0.0', 3000, []), 'http://localhost:3000')
        self.assertEqual(collect.local_url('::', 5173, []), 'http://localhost:5173')
        self.assertEqual(collect.local_url('::1', 9527, []), 'http://localhost:9527')
        self.assertEqual(collect.local_url('127.0.0.1', 443, ['--https']), 'https://localhost:443')
        self.assertEqual(collect.local_url('192.168.1.2', 8000, []), 'http://192.168.1.2:8000')
        self.assertEqual(collect.local_url('127.0.0.2', 8000, []), 'http://127.0.0.2:8000')
        self.assertEqual(collect.local_url('2001:db8::1', 8000, []), 'http://[2001:db8::1]:8000')

    def test_proc_decoding(self):
        with tempfile.TemporaryDirectory(prefix='konoports-', dir='/tmp/opencode') as directory:
            net = Path(directory, 'net')
            net.mkdir()
            (net / 'tcp').write_text('header\n0: 0100007F:0BB8 00000000:0000 0A 0 0 0 1000 0 123\n'
                                     '1: 0100007F:1234 00000000:0000 01 0 0 0 1000 0 456\n')
            with patch.object(collect, 'PROC', Path(directory)):
                self.assertEqual(collect.listeners(), {'123': {'address': '127.0.0.1', 'port': 3000, 'inode': '123'}})

    def test_unreadable_proc_is_error(self):
        with tempfile.TemporaryDirectory(prefix='konoports-', dir='/tmp/opencode') as directory:
            with patch.object(collect, 'PROC', Path(directory)):
                with self.assertRaises(OSError):
                    collect.listeners()

    def test_foreign_owner(self):
        with patch.object(collect.os, 'getuid', return_value=os.getuid() + 1):
            with self.assertRaises(PermissionError):
                collect.identity(os.getpid())


@contextlib.contextmanager
def server(ignore_term=False):
    # Only processes created by these tests are ever terminated.
    code = ('import socket, signal, time\n'
            + ('signal.signal(signal.SIGTERM, signal.SIG_IGN)\n' if ignore_term else '')
            + 's=socket.socket(); s.bind(("127.0.0.1",0)); s.listen()\n'
              'print(s.getsockname()[1],flush=True)\ntime.sleep(60)\n')
    process = subprocess.Popen([sys.executable, '-u', '-c', code], stdout=subprocess.PIPE, text=True)
    try:
        port = int(process.stdout.readline())
        rows = [row for row in collect.snapshot()['servers'] if row['pid'] == process.pid and row['port'] == port]
        if len(rows) != 1:
            raise AssertionError(f'Test server was not discovered: {rows}')
        yield process, rows[0]
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stdout.close()


class ProcessTests(unittest.TestCase):
    def test_live_discovery_and_stop(self):
        with server() as (process, row):
            self.assertTrue(row['command'])
            self.assertTrue(row['url'].startswith('http://localhost:'))
            result = collect.stop_process(process.pid, row['startTime'], row['port'], row['inode'])
            self.assertTrue(result['ok'])
            self.assertNotIn('forced', result['message'])
            process.wait(timeout=5)
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', row['port']))

    def test_stale_identity_rejected(self):
        with server() as (process, row):
            with self.assertRaisesRegex(ValueError, 'identity'):
                collect.stop_process(process.pid, '0', row['port'], row['inode'])
            self.assertIsNone(process.poll())

    def test_wrong_port_rejected(self):
        with server() as (process, row):
            with self.assertRaisesRegex(ValueError, 'listening port'):
                collect.stop_process(process.pid, row['startTime'], row['port'] + 1, row['inode'])
            self.assertIsNone(process.poll())

    def test_wrong_inode_rejected(self):
        with server() as (process, row):
            with self.assertRaises(ValueError):
                collect.stop_process(process.pid, row['startTime'], row['port'], '0')
            self.assertIsNone(process.poll())

    def test_force_stop(self):
        with server(ignore_term=True) as (process, row):
            result = collect.stop_process(process.pid, row['startTime'], row['port'], row['inode'])
            self.assertTrue(result['ok'])
            self.assertIn('forced', result['message'])

    def test_self_rejected(self):
        with self.assertRaises(ValueError):
            collect.stop_process(os.getpid(), '0', 3000, '0')

    def test_cli_error_json(self):
        output = subprocess.check_output([sys.executable, '-B', str(Path(collect.__file__)), '--stop', '1', '0', '3000', '0'], text=True)
        self.assertFalse(json.loads(output)['ok'])


if __name__ == '__main__':
    unittest.main()
