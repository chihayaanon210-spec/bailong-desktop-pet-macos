"""Platform regression checks; never install or launch a real login service."""
import json
from pathlib import Path
import plistlib
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import autostart
from desktop_visibility import mac_fullscreen_window, FullscreenDetector, configure_macos_window, mac_window_status


def window(pid=20, x=0, y=0, width=1920, height=1080, **extra):
    result = {'kCGWindowOwnerPID': pid, 'kCGWindowLayer': 0,
              'kCGWindowAlpha': 1, 'kCGWindowIsOnscreen': True,
              'kCGWindowBounds': {'X': x, 'Y': y, 'Width': width, 'Height': height}}
    result.update(extra)
    return result


class MacGeometryTests(unittest.TestCase):
    def test_fullscreen_requires_foreground_application(self):
        screens = [(0, 0, 1920, 1080)]
        self.assertTrue(mac_fullscreen_window(20, [window()], screens, own_pid=30))
        self.assertFalse(mac_fullscreen_window(25, [window()], screens, own_pid=30))
        self.assertFalse(mac_fullscreen_window(20, [window()], screens, own_pid=20))
        self.assertFalse(mac_fullscreen_window(None, [window()], screens, own_pid=30))

    def test_menu_bar_and_dock_space_is_not_fullscreen(self):
        self.assertFalse(mac_fullscreen_window(20, [window(y=25, height=1055)], [(0, 0, 1920, 1080)], 30))
        self.assertFalse(mac_fullscreen_window(20, [window(height=1040)], [(0, 0, 1920, 1080)], 30))

    def test_monitor_coordinates_do_not_depend_on_primary_screen(self):
        screens = [(0, 0, 1920, 1080), (-1440, -900, 0, 0)]
        self.assertTrue(mac_fullscreen_window(20, [window(x=-1440, y=-900, width=1440, height=900)], screens, 30))
        self.assertFalse(mac_fullscreen_window(20, [window(x=-1400, y=-900, width=1400, height=900)], screens, 30))

    def test_ignores_invisible_and_non_document_windows(self):
        screens = [(0, 0, 1920, 1080)]
        for properties in ({'kCGWindowLayer': 25}, {'kCGWindowAlpha': 0}, {'kCGWindowIsOnscreen': False}):
            self.assertFalse(mac_fullscreen_window(20, [window(**properties)], screens, 30))

    def test_mac_detector_uses_metadata_bridge(self):
        bridge = Mock()
        bridge.frontmost_pid.return_value = 20
        bridge.windows.return_value = [window()]
        bridge.monitors.return_value = [(0, 0, 1920, 1080)]
        with patch('desktop_visibility.sys.platform', 'darwin'), patch('desktop_visibility._get_mac_desktop', return_value=bridge), patch('desktop_visibility._cocoa_windows_available', return_value=True):
            self.assertTrue(FullscreenDetector().active())
            configure_macos_window(12345)
            bridge.configure_window.assert_called_once_with(12345)
            configure_macos_window(0)
            self.assertEqual(bridge.configure_window.call_count, 1)

    def test_synthetic_offscreen_window_ids_never_reach_objective_c(self):
        with patch('desktop_visibility.sys.platform', 'darwin'), patch('desktop_visibility._cocoa_windows_available', return_value=False), patch('desktop_visibility._get_mac_desktop') as bridge:
            configure_macos_window(1)
            self.assertEqual(mac_window_status(1), {})
            bridge.assert_not_called()

    def test_native_status_reports_only_the_requested_own_window(self):
        bridge = Mock()
        expected = {'windowNumber': 30, 'isVisible': True, 'isOnActiveSpace': True,
                    'hidesOnDeactivate': False, 'level': 3}
        bridge.window_status.return_value = expected
        with patch('desktop_visibility.sys.platform', 'darwin'), patch('desktop_visibility._get_mac_desktop', return_value=bridge), patch('desktop_visibility._cocoa_windows_available', return_value=True):
            self.assertEqual(mac_window_status(12345), expected)
            bridge.window_status.assert_called_once_with(12345)
            self.assertEqual(mac_window_status(0), {})
            self.assertEqual(bridge.window_status.call_count, 1)


class MacAutostartTests(unittest.TestCase):
    def test_supported_client_is_detected_by_exact_bundle_id(self):
        with patch('autostart.sys.platform', 'darwin'), patch('desktop_visibility.mac_running_bundle_ids') as bundles:
            for value in ('com.openai.codex', 'com.openai.chat'):
                bundles.return_value = {value}
                self.assertTrue(autostart.gpt_is_open())
            bundles.return_value = {'com.example.chatgpt-helper'}
            self.assertFalse(autostart.gpt_is_open())

    def test_source_monitor_uses_current_python_without_windows_flags(self):
        with patch('autostart.sys.platform', 'darwin'), patch.object(autostart.sys, 'frozen', False, create=True), patch.object(autostart.sys, 'executable', '/tmp/Python With Spaces/bin/python'):
            self.assertEqual(autostart._monitor_command(), ['/tmp/Python With Spaces/bin/python', str(autostart.ROOT/'app/pet.py'), '--autostart'])
            with tempfile.TemporaryDirectory() as directory, patch('autostart.data_root', return_value=Path(directory)), patch('autostart.subprocess.Popen') as popen:
                popen.return_value.pid = 88
                self.assertEqual(autostart.launch_pet(), 88)
                arguments, options = popen.call_args
                self.assertEqual(arguments[0][0], '/tmp/Python With Spaces/bin/python')
                self.assertNotIn('creationflags', options)
                self.assertTrue(options['start_new_session'])
                self.assertEqual(options['cwd'], Path(directory))

    def test_packaged_monitor_uses_actual_bundle_executable(self):
        with patch('autostart.sys.platform', 'darwin'), patch.object(autostart.sys, 'frozen', True, create=True), patch.object(autostart.sys, 'executable', '/Applications/BailongPet.app/Contents/MacOS/BailongPet'):
            self.assertEqual(autostart._monitor_command(), ['/Applications/BailongPet.app/Contents/MacOS/BailongPet', '--autostart'])

    def test_enable_writes_opt_in_manifest_and_checks_running_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = root/'LaunchAgents/agent.plist'
            def launchctl(*args, **kwargs):
                return types.SimpleNamespace(returncode=0, stdout='state = running' if args[0] == 'print' else '', stderr='')
            with patch('autostart.sys.platform', 'darwin'), patch('autostart.startup_entry', return_value=entry), patch('autostart.data_root', return_value=root/'state'), patch('autostart._launchctl', side_effect=launchctl) as control:
                autostart.enable_autostart()
                manifest = plistlib.loads(entry.read_bytes())
                self.assertEqual(manifest['Label'], autostart.MAC_AGENT_LABEL)
                self.assertEqual(manifest['ProgramArguments'][-1], '--autostart')
                self.assertTrue(manifest['RunAtLoad'])
                self.assertEqual(manifest['WorkingDirectory'], str(root/'state'))
                self.assertEqual(control.call_args_list[-1].args[0], 'print')

    def test_failed_bootstrap_never_reports_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def launchctl(*args, **kwargs):
                if args[0] == 'bootstrap':
                    raise RuntimeError('bootstrap rejected')
                return types.SimpleNamespace(returncode=0, stdout='', stderr='')
            with patch('autostart.sys.platform', 'darwin'), patch('autostart.startup_entry', return_value=root/'agent.plist'), patch('autostart.data_root', return_value=root), patch('autostart._launchctl', side_effect=launchctl):
                with self.assertRaisesRegex(RuntimeError, 'bootstrap rejected'):
                    autostart.enable_autostart()

    def test_enable_preserves_unrelated_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            entry = Path(directory)/'agent.plist'
            original = plistlib.dumps({'Label': 'com.example.other-service'})
            entry.write_bytes(original)
            with patch('autostart.sys.platform', 'darwin'), patch('autostart.startup_entry', return_value=entry), patch('autostart._launchctl') as control:
                with self.assertRaises(RuntimeError):
                    autostart.enable_autostart()
                self.assertEqual(entry.read_bytes(), original)
                control.assert_not_called()

    def test_reused_pid_is_never_terminated(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)/'state.json'
            state.write_text(json.dumps({'pid': 1234, 'processCreateTime': 100}))
            process = Mock()
            process.create_time.return_value = 200
            with patch('autostart._state_file', return_value=state), patch('autostart.psutil.Process', return_value=process):
                autostart._stop_monitor_from_state()
            process.terminate.assert_not_called()
            process.cmdline.assert_not_called()

    def test_unrelated_python_command_is_not_our_monitor(self):
        with patch.object(autostart.sys, 'frozen', False, create=True):
            self.assertFalse(autostart._is_our_monitor([autostart.sys.executable, '/tmp/unrelated.py', '--autostart']))
            self.assertTrue(autostart._is_our_monitor([autostart.sys.executable, str(autostart.ROOT/'app/pet.py'), '--autostart']))

    def test_windows_source_command_keeps_pythonw(self):
        with patch('autostart.sys.platform', 'win32'), patch.object(autostart.sys, 'frozen', False, create=True), patch.object(autostart.sys, 'executable', '/tmp/python.exe'):
            self.assertEqual(autostart._monitor_command()[0], '/tmp/pythonw.exe')


if __name__ == '__main__':
    unittest.main()
