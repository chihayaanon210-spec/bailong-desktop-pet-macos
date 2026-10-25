"""Native chat input behavior, without assets or live Codex requests."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from chat_ui import Composer, ChatWindow, send_shortcut_label, send_shortcut_sequence, ui_font_family

app = QApplication.instance() or QApplication([])


class MacInputTests(unittest.TestCase):
    def open_widget(self, kind):
        widget = kind()
        widget.show()
        app.setActiveWindow(widget)
        widget.editor.setFocus()
        app.processEvents()
        self.addCleanup(widget.hide)
        self.addCleanup(widget.deleteLater)
        return widget

    def test_platform_labels_and_fonts_preserve_windows(self):
        self.assertEqual(send_shortcut_label('darwin'), '⌘ Return')
        self.assertEqual(send_shortcut_label('win32'), 'Ctrl+Enter')
        self.assertIn('PingFang SC', ui_font_family('darwin'))
        self.assertIn('.AppleSystemUIFont', ui_font_family('darwin'))
        self.assertEqual(ui_font_family('win32'), '"Microsoft YaHei","Segoe UI"')

    def test_mac_composer_remains_visible_when_application_is_inactive(self):
        for platform, expected in (('darwin', True), ('win32', False)):
            with self.subTest(platform=platform), patch('chat_ui.sys.platform', platform):
                widget = Composer()
                self.addCleanup(widget.deleteLater)
                self.assertEqual(widget.testAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow), expected)

    def test_shortcut_uses_qt_command_mapping_and_visible_hint(self):
        expected = QKeySequence('Ctrl+Return', QKeySequence.SequenceFormat.PortableText)
        self.assertEqual(send_shortcut_sequence(), expected)
        for kind in (Composer, ChatWindow):
            with self.subTest(kind=kind.__name__):
                widget = self.open_widget(kind)
                self.assertEqual(widget.shortcut.key(), expected)
                self.assertIn(send_shortcut_label(), widget.editor.placeholderText())

    def test_return_inserts_newline_and_command_return_sends_once(self):
        for kind in (Composer, ChatWindow):
            with self.subTest(kind=kind.__name__):
                widget = self.open_widget(kind)
                sent = []
                widget.send.connect(sent.append)
                widget.editor.setPlainText('local input')
                widget.editor.moveCursor(widget.editor.textCursor().MoveOperation.End)
                QTest.keyClick(widget.editor, Qt.Key.Key_Return)
                self.assertEqual(widget.editor.toPlainText(), 'local input\n')
                self.assertEqual(sent, [])
                # On macOS Qt.ControlModifier is Command, matching QKeySequence.
                QTest.keyClick(widget.editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
                self.assertEqual(sent, ['local input'])

    def test_busy_input_shortcut_does_not_start_a_second_task(self):
        for kind in (Composer, ChatWindow):
            with self.subTest(kind=kind.__name__):
                widget = self.open_widget(kind)
                sent = []
                widget.send.connect(sent.append)
                widget.editor.setPlainText('must not start')
                widget.busy(True)
                QTest.keyClick(widget.editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
                self.assertEqual(sent, [])


if __name__ == '__main__':
    unittest.main()
