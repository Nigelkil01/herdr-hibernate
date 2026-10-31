import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

loader = importlib.machinery.SourceFileLoader(
    'board_safe_hibernate', str(Path(__file__).resolve().parents[1] / 'contrib/board-safe-hibernate'))
spec = importlib.util.spec_from_loader(loader.name, loader)
guard = importlib.util.module_from_spec(spec)
loader.exec_module(guard)


class BoardSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / 'data'
        self.env = mock.patch.dict(os.environ, {'HERDR_PROJECTS_DATA_DIR': str(self.data)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.plugin = types.SimpleNamespace(
            classify=mock.Mock(return_value=('hibernate', 'idle 2h')),
            hibernate_pane=mock.Mock(return_value=True),
            herdr=mock.Mock(), log=mock.Mock())
        guard.install_guard(self.plugin)
        self.pane = {'pane_id': 'w1:p1', 'tab_id': 'w1:t1', 'workspace_id': 'w1',
                     'agent': 'codex', 'agent_status': 'done'}

    def classify(self, pane=None):
        return self.plugin.classify(pane or self.pane, {}, {}, {}, '')

    def test_board_metadata_labels_are_exempt_in_every_state(self):
        for label in ('Agent', 'Agent (codex)', 'Reviewer #3', '💤 Agent', 'Coordinator',
                      'apex-dashboard coordinator'):
            for status in ('idle', 'done', 'unknown', 'working', 'blocked'):
                with self.subTest(label=label, status=status):
                    pane = {**self.pane, 'tokens': {'title': label}, 'agent_status': status}
                    self.assertEqual('exempt', self.classify(pane)[0])

    def test_tab_and_pane_labels_are_also_exempt(self):
        self.assertEqual('exempt', self.classify({**self.pane, 'label': 'Reviewer #8'})[0])
        self.assertEqual('exempt', self.plugin.classify(self.pane, {'w1:t1': 'Agent'}, {}, {}, '')[0])

    def test_legacy_coordinator_is_protected_by_terminal_title(self):
        for title in ('Take over coordinator position | checkout',
                      '✳ Omarchy machine coordinator setup'):
            self.assertEqual('exempt', self.classify(
                {**self.pane, 'tokens': {'title': '2'}, 'terminal_title': title})[0])

    def test_owned_workspace_is_exempt_even_with_custom_label_and_pending_text(self):
        path = self.data / 'tasks/repo/1/task.json'
        path.parent.mkdir(parents=True)
        for stage in ('working', 'asks', 'approval', 'done'):
            path.write_text(json.dumps({'stage': stage, 'pendingText': 'do this',
                                        'link': {'workspace': 'w1'}}))
            self.assertEqual('exempt', self.classify()[0])

    def test_coordinator_folder_is_exempt_without_metadata(self):
        pane = {**self.pane, 'cwd': str(self.data / 'coordinator/aide/chat')}
        self.assertEqual('exempt', self.classify(pane)[0])

    def test_task_in_another_server_does_not_own_same_pane_id(self):
        path = self.data / 'tasks/repo/1/task.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'link': {'workspace': 'w1', 'pane': 'w1:p1',
                                               'socket': '/other/herdr.sock'}}))
        with mock.patch.dict(os.environ, {'HERDR_SOCKET_PATH': '/current/herdr.sock'}):
            self.assertEqual(('hibernate', 'idle 2h'), self.classify())

    def test_unreadable_ownership_prevents_kill(self):
        path = self.data / 'tasks/repo/1/task.json'
        path.parent.mkdir(parents=True)
        path.write_text('{')
        self.assertEqual('exempt', self.classify()[0])

    def test_unreadable_task_directories_protect_custom_labelled_panes(self):
        path = self.data / 'tasks/repo/1/task.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'link': {'workspace': 'w1'}}))
        pane = {**self.pane, 'label': 'Implementation'}
        for directory in (self.data / 'tasks', path.parent.parent, path.parent):
            with self.subTest(directory=directory):
                mode = directory.stat().st_mode
                directory.chmod(0)
                try:
                    self.assertEqual('exempt', self.classify(pane)[0])
                finally:
                    directory.chmod(mode)

    def test_directory_becoming_unreadable_before_force_prevents_kill(self):
        path = self.data / 'tasks/repo/1/task.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'link': {'workspace': 'w1'}}))
        self.plugin.herdr.side_effect = [
            {'pane': {**self.pane, 'label': 'Implementation'}}, {'tab': {'label': 'Custom'}}]
        directory = path.parent.parent
        mode = directory.stat().st_mode
        directory.chmod(0)
        try:
            self.assertFalse(self.plugin.hibernate_pane(
                self.pane, {}, {}, {}, '2h', False, force=True))
        finally:
            directory.chmod(mode)

    def test_readable_unrelated_tasks_do_not_prevent_ordinary_hibernation(self):
        path = self.data / 'tasks/repo/1/task.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'link': {'workspace': 'w2'}}))
        (path.parent.parent / 'notes.txt').write_text('not a task directory')
        (path.parent.parent / 'review').mkdir()  # Board helper folder, no task record.
        self.assertEqual(('hibernate', 'idle 2h'), self.classify())

    def test_non_board_pane_uses_upstream_rules_unchanged(self):
        self.assertEqual(('hibernate', 'idle 2h'), self.classify())
        self.plugin.herdr.return_value = {'pane': self.pane, 'tab': {'label': 'ordinary'}}
        self.assertTrue(self.plugin.hibernate_pane(self.pane, {}, {}, {}, '2h', False, force=True))

    def test_fresh_ownership_is_checked_before_kill_even_with_force(self):
        self.plugin.herdr.return_value = {
            'pane': {**self.pane, 'tokens': {'title': 'Agent'}}, 'tab': {'label': 'ordinary'}}
        self.assertFalse(self.plugin.hibernate_pane(self.pane, {}, {}, {}, '2h', False, force=True))

    def test_missing_fresh_pane_prevents_kill(self):
        self.plugin.herdr.return_value = {}
        self.assertFalse(self.plugin.hibernate_pane(self.pane, {}, {}, {}, '2h', False))

    def test_tab_renamed_after_scan_is_protected_before_kill(self):
        self.plugin.herdr.side_effect = [{'pane': self.pane}, {'tab': {'label': 'Agent'}}]
        self.assertFalse(self.plugin.hibernate_pane(
            self.pane, {'w1:t1': 'ordinary'}, {}, {}, '2h', False, force=True))
