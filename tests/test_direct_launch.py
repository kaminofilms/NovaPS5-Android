#!/usr/bin/env python3
"""Exercise direct-route validation, exact game argv, and failure propagation.

Wine is a fake process here. These checks never claim emulator compatibility.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ASSETS = Path(__file__).resolve().parents[1] / 'droid-runtime/app/src/main/assets/engine'


class DirectLaunch(unittest.TestCase):
    def test_guard(self):
        for mode, target, expected in [('run', '/opt/novaps5/launch.sh', 0),
                ('steam', '/opt/novaps5/launch.sh', 64),
                ('run', '/usr/bin/steam', 64), ('lxqt', '', 64), ('', '', 64)]:
            result = subprocess.run(['bash', '-c', 'source "$1" "$2" "$3"',
                'test', str(ASSETS / 'session-guard.sh'), mode, target], capture_output=True)
            self.assertEqual(result.returncode, expected)

    def run_launch(self, preflight=0, game_status=0, missing=False):
        with tempfile.TemporaryDirectory(prefix='nova-game-') as directory:
            root = Path(directory)
            base = root / 'engine'
            files = base / 'proton/GE-Proton11-7-aarch64/files'
            (files / 'bin').mkdir(parents=True)
            (files / 'lib/wine/aarch64-unix').mkdir(parents=True)
            (files / 'lib/wine/aarch64-unix/libarm64ecfex.so').touch()
            (base / 'kyty').mkdir()
            game = root / 'Game folder with spaces'
            game.mkdir()
            if not missing:
                (game / 'eboot.bin').touch()
            wine = files / 'bin/wine'
            wine.write_text('#!/usr/bin/env python3\nimport json,os,sys\n'
                'with open(os.environ["NOVA_TEST_CALLS"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                f'sys.exit({preflight} if "--help" in sys.argv else {game_status})\n')
            wine.chmod(0o755)
            server = files / 'bin/wineserver'
            server.write_text('#!/bin/bash\nexit 0\n')
            server.chmod(0o755)
            script = (ASSETS / 'launch.sh').read_text().replace('base=/opt/novaps5', 'base=' + str(base))
            script = script.replace('/root/.local/share/novaps5', str(root / 'private'))
            path = root / 'launch.sh'
            path.write_text(script)
            calls = root / 'calls.jsonl'
            env = dict(os.environ, NOVA_TEST_CALLS=str(calls))
            result = subprocess.run(['bash', str(path), str(game)], env=env, text=True, capture_output=True, timeout=10)
            argv = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
            return result, argv, str(game)

    def test_direct_game_arguments(self):
        result, calls, game = self.run_launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1:], ['--help'])
        self.assertTrue(calls[1][0].endswith('/kyty/kyty_emulator.exe'))
        self.assertEqual(calls[1][1:3], ['--game', 'Z:' + game.replace('/', '\\')])
        self.assertIn('NOVA_PREFLIGHT:', result.stdout)
        self.assertIn('NOVA_EXIT: Kyty launch ended with status 0', result.stdout)
        self.assertNotIn('steam.exe', repr(calls))

    def test_preflight_failure_stops_before_game(self):
        result, calls, _ = self.run_launch(preflight=7)
        self.assertEqual(result.returncode, 69)
        self.assertEqual(len(calls), 1)
        self.assertIn('preflight failed (status 7', result.stdout)

    def test_game_failure_keeps_exit_code(self):
        result, calls, _ = self.run_launch(game_status=42)
        self.assertEqual(result.returncode, 42)
        self.assertEqual(len(calls), 2)
        self.assertIn('NOVA_ERROR: Kyty game process exited with status 42', result.stdout)

    def test_missing_game_never_starts_wine(self):
        result, calls, _ = self.run_launch(missing=True)
        self.assertEqual(result.returncode, 66)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
