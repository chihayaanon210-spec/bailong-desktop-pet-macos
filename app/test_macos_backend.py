"""macOS backend regressions; no account access or model requests are made."""
import io
import json
import os
from pathlib import Path
import plistlib
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import chat_backend
import quota


def executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    path.chmod(0o755)
    return path


class MacCodexDiscoveryTests(unittest.TestCase):
    def test_finder_minimal_path_finds_bundled_cli(self):
        with tempfile.TemporaryDirectory(prefix='bailong test ') as folder:
            bundle = Path(folder) / 'ChatGPT.app'
            contents = bundle / 'Contents'
            contents.mkdir(parents=True)
            with (contents / 'Info.plist').open('wb') as stream:
                plistlib.dump({'CFBundleIdentifier': 'com.openai.codex'}, stream)
            binary = executable(contents / 'Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
            with patch.object(quota.sys, 'platform', 'darwin'), \
                    patch.dict(os.environ, {'BAILONG_CODEX': '', 'PATH': '/usr/bin:/bin'}), \
                    patch('quota.shutil.which', return_value=None), \
                    patch('quota._macos_application_roots', return_value=[bundle]):
                self.assertEqual(quota.find_codex(), str(binary))

    def test_user_override_takes_precedence_over_path_and_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = executable(Path(folder) / 'custom codex')
            with patch.object(quota.sys, 'platform', 'darwin'), \
                    patch.dict(os.environ, {'BAILONG_CODEX': '"' + str(binary) + '"'}), \
                    patch('quota.shutil.which', return_value=None), \
                    patch('quota._macos_codex_candidates') as candidates:
                self.assertEqual(quota.find_codex(), str(binary))
                candidates.assert_not_called()

    def test_non_executable_file_is_not_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'codex'
            path.write_text('not executable', encoding='utf-8')
            with patch.object(quota.sys, 'platform', 'darwin'), \
                    patch.dict(os.environ, {'BAILONG_CODEX': str(path)}), \
                    patch('quota.shutil.which', return_value=None), \
                    patch('quota._macos_codex_candidates', return_value=[path]):
                with self.assertRaisesRegex(RuntimeError, '可执行'):
                    quota.find_codex()

    def test_classic_chatgpt_bundle_is_not_a_codex_source(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / 'ChatGPT.app'
            contents = bundle / 'Contents'
            contents.mkdir(parents=True)
            with (contents / 'Info.plist').open('wb') as stream:
                plistlib.dump({'CFBundleIdentifier': 'com.openai.chat'}, stream)
            binary = executable(contents / 'Resources/codex')
            with patch('quota._macos_application_roots', return_value=[bundle]):
                self.assertNotIn(binary, list(quota._macos_codex_candidates()))


class MacPersistenceTests(unittest.TestCase):
    def test_history_defaults_to_writable_user_data_directory(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(chat_backend.sys, 'platform', 'darwin'), \
                patch.dict(os.environ, {'BAILONG_DATA_DIR': ''}), \
                patch('chat_backend.data_root', return_value=Path(folder)):
            store = chat_backend.HistoryStore()
            store.new(folder)
            self.assertEqual(store.path, Path(folder) / 'conversations.json')
            self.assertEqual(len(chat_backend.HistoryStore().conversations), 1)

    def test_explicit_history_directory_override_remains_supported(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(os.environ, {'BAILONG_DATA_DIR': folder}):
            self.assertEqual(chat_backend.data_directory(), Path(folder))

    def test_quota_diagnostics_go_to_user_data_and_keep_only_safe_fields(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(quota.sys, 'platform', 'darwin'), \
                patch('quota.data_root', return_value=Path(folder) / 'nested'):
            failure = quota.classify_error('DNS error https://example.invalid/?token=SECRET_TEST')
            quota.log_attempt(1, 0.25, failure)
            path = Path(folder) / 'nested/额度查询日志.jsonl'
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('SECRET_TEST', text)
            self.assertNotIn('http', text)
            self.assertEqual(json.loads(text)['result'], 'network')


class RecordingPipe(io.StringIO):
    def close(self):
        self.recorded = self.getvalue()
        super().close()


class FakeQuotaProcess:
    def __init__(self):
        self.stdin = RecordingPipe()
        result = {'rateLimitsByLimitId': {'codex': {'primary': {'usedPercent': 21}}}}
        self.stdout = io.StringIO(json.dumps({'id': 1, 'result': {}}) + '\n' +
                                  json.dumps({'id': 2, 'result': result}) + '\n')
        self.stopped = False

    def poll(self):
        return 0 if self.stopped else None

    def terminate(self):
        self.stopped = True

    def wait(self, timeout=None):
        return 0


class MacTransportTests(unittest.TestCase):
    def test_quota_handshake_is_read_only_and_process_is_closed(self):
        process = FakeQuotaProcess()
        with patch('quota.find_codex', return_value='/Applications/Codex.app/Contents/Resources/codex'), \
                patch('quota.subprocess.Popen', return_value=process):
            result = quota._read_quota_once(timeout=1)
        sent = [json.loads(line) for line in process.stdin.recorded.splitlines()]
        self.assertEqual([message['method'] for message in sent],
                         ['initialize', 'initialized', 'account/rateLimits/read'])
        self.assertEqual(result['rateLimitsByLimitId']['codex']['primary']['usedPercent'], 21)
        self.assertTrue(process.stopped)
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)

    def test_unsupported_approval_request_is_rejected(self):
        session = chat_backend.CodexSession('.')
        with patch.object(session, 'send') as send:
            session.answer_request({'id': 12, 'method': 'unknown/privilegedTool', 'params': {}})
        response = send.call_args.args[0]
        self.assertIn('error', response)
        self.assertNotIn('result', response)

    def test_work_mode_retains_workspace_sandbox_and_user_approvals(self):
        session = chat_backend.CodexSession('.')
        session.process = SimpleNamespace(poll=lambda: None)
        calls = []

        def rpc(method, params, timeout=45):
            calls.append((method, params))
            if method == 'thread/start':
                return {'thread': {'id': 'mock-thread'}}
            if method == 'turn/start':
                session.finished_turn = {'status': 'completed'}
                return {'turn': {'id': 'mock-turn'}}
            return {}

        with patch.object(session, 'send'), patch.object(session, 'rpc', side_effect=rpc):
            session.run('test request handled only by mocks')
        thread = next(params for method, params in calls if method == 'thread/start')
        turn = next(params for method, params in calls if method == 'turn/start')
        self.assertEqual(thread['approvalPolicy'], 'on-request')
        self.assertEqual(turn['approvalPolicy'], 'on-request')
        self.assertEqual(thread['approvalsReviewer'], 'user')
        self.assertEqual(turn['approvalsReviewer'], 'user')
        self.assertEqual(turn['sandboxPolicy']['type'], 'workspaceWrite')
        self.assertFalse(turn['sandboxPolicy']['networkAccess'])


if __name__ == '__main__':
    unittest.main()
