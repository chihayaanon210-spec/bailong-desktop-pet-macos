"""Opt-in monitor: start the pet when a supported desktop client opens."""
import ctypes
import json
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime
import psutil
from runtime_paths import resource_root, data_root

ROOT = resource_root()
MAC_AGENT_LABEL = 'local.bailongpet.macos.autostart'
MAC_CLIENT_BUNDLES = {'com.openai.codex', 'com.openai.chat'}


def _state_file():
    return data_root()/'自启动状态.json' if sys.platform == 'darwin' else ROOT/'app/自启动状态.json'


def gpt_is_open():
    if sys.platform == 'darwin':
        from desktop_visibility import mac_running_bundle_ids
        return bool(MAC_CLIENT_BUNDLES & mac_running_bundle_ids())
    for process in psutil.process_iter(['name', 'exe']):
        try:
            name = (process.info['name'] or '').lower()
            path = (process.info['exe'] or '').lower().replace('/', '\\')
            if name == 'chatgpt.exe' and any(package in path for package in ('\\openai.codex_', '\\openai.chatgpt_')):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _monitor_command():
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--autostart']
    python = Path(sys.executable)
    if sys.platform == 'win32':
        python = python.with_name('pythonw.exe')
    return [str(python), str(ROOT/'app/pet.py'), '--autostart']


def launch_pet():
    if getattr(sys, 'frozen', False):
        command = [sys.executable]
    else:
        python = Path(sys.executable)
        if sys.platform == 'win32':
            python = python.with_name('pythonw.exe')
        command = [str(python), str(ROOT/'app/pet.py')]
    options = {'cwd': ROOT}
    if sys.platform == 'win32':
        options['creationflags'] = subprocess.CREATE_NO_WINDOW
    else:
        directory = data_root()
        directory.mkdir(parents=True, exist_ok=True)
        options.update(cwd=directory, start_new_session=True)
    return subprocess.Popen(command, **options).pid


def startup_entry():
    if sys.platform == 'darwin':
        return Path.home()/'Library/LaunchAgents'/f'{MAC_AGENT_LABEL}.plist'
    if sys.platform != 'win32':
        raise RuntimeError('自动启动目前支持 macOS 和 Windows。')
    buffer = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.shell32.SHGetFolderPathW(None, 7, None, 0, buffer)
    if result != 0:
        raise RuntimeError('无法找到当前用户的Windows启动文件夹。')
    return Path(buffer.value)/'BailongPetAutostart.vbs'


def mac_agent_manifest():
    directory = data_root()
    return {
        'Label': MAC_AGENT_LABEL,
        'ProgramArguments': _monitor_command(),
        'RunAtLoad': True,
        'LimitLoadToSessionType': 'Aqua',
        'ProcessType': 'Background',
        'WorkingDirectory': str(directory),
        'StandardOutPath': str(directory/'autostart.log'),
        'StandardErrorPath': str(directory/'autostart.log'),
    }


def _launchctl(*arguments, check=True):
    result = subprocess.run(['/bin/launchctl', *arguments], capture_output=True,
                            text=True, timeout=10)
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError('登录启动项未能在当前会话中加载。请保留错误信息：\n'+detail)
    return result


def _mac_service():
    domain = f'gui/{os.getuid()}'
    return domain, f'{domain}/{MAC_AGENT_LABEL}'


def _verify_owned_entry(entry):
    if not entry.exists():
        return
    try:
        with entry.open('rb') as file:
            manifest = plistlib.load(file)
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        raise RuntimeError('现有自动启动文件无法识别，未修改。') from error
    if manifest.get('Label') != MAC_AGENT_LABEL:
        raise RuntimeError('现有自动启动文件属于其他程序，未修改。')


def enable_autostart():
    if sys.platform == 'darwin':
        entry = startup_entry()
        _verify_owned_entry(entry)
        entry.parent.mkdir(parents=True, exist_ok=True)
        data_root().mkdir(parents=True, exist_ok=True)
        with entry.open('wb') as file:
            plistlib.dump(mac_agent_manifest(), file)
        domain, service = _mac_service()
        _launchctl('bootout', service, check=False)
        _launchctl('enable', service)
        _launchctl('bootstrap', domain, str(entry))
        # Report success only after the background process is still running.
        for _ in range(10):
            result = _launchctl('print', service, check=False)
            if result.returncode == 0 and 'state = running' in result.stdout:
                return
            time.sleep(.2)
        raise RuntimeError('登录启动项已保存，但监视器没有保持运行。请查看 '+str(data_root()/'autostart.log'))
    command = _monitor_command()
    script = 'Option Explicit\nDim shell\nSet shell = CreateObject("WScript.Shell")\n'
    script += f'shell.CurrentDirectory = "{ROOT}"\n'
    # Windows VBS uses doubled quotes rather than shell escaping.
    quoted = subprocess.list2cmdline(command)
    script += 'shell.Run "'+quoted.replace('"', '""')+'", 0, False\n'
    startup_entry().write_text(script, encoding='utf-16')
    subprocess.Popen(command, cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)


def _is_our_monitor(command):
    if not command:
        return False
    if '--autostart' in command:
        return (Path(command[0]).resolve() == Path(sys.executable).resolve()
                and (getattr(sys, 'frozen', False) or str(ROOT/'app/pet.py') in command))
    # Retain compatibility with the original Windows source launcher.
    return str(ROOT/'app/autostart.py') in command


def _stop_monitor_from_state():
    path = _state_file()
    if not path.is_file():
        return
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
        if state['pid'] == os.getpid():
            return
        process = psutil.Process(state['pid'])
        if 'processCreateTime' in state and abs(process.create_time()-state['processCreateTime']) > .01:
            return
        if _is_our_monitor(process.cmdline()):
            process.terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError, KeyError):
        pass


def disable_autostart():
    entry = startup_entry()
    if sys.platform == 'darwin':
        _verify_owned_entry(entry)
        _, service = _mac_service()
        _launchctl('disable', service)
        _launchctl('bootout', service, check=False)
    if entry.is_file():
        entry.unlink()
    _stop_monitor_from_state()


def _acquire_monitor_lock():
    if sys.platform == 'win32':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateMutexW(None, False, 'Local\\BailongPetAutostartV1')
        if not handle:
            raise RuntimeError('无法创建自动启动监视器锁。')
        if ctypes.get_last_error() == 183:
            kernel.CloseHandle(handle)
            return None, None
        return handle, lambda: kernel.CloseHandle(handle)
    import fcntl
    directory = data_root()
    directory.mkdir(parents=True, exist_ok=True)
    lock = (directory/'autostart.lock').open('a+')
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None, None
    return lock, lock.close


def main():
    handle, close = _acquire_monitor_lock()
    if handle is None:
        return 0
    previous = False
    state = {'pid': os.getpid(), 'processCreateTime': psutil.Process().create_time(),
             'started': datetime.now().isoformat(timespec='seconds')}
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        while True:
            current = gpt_is_open()
            if current and not previous:
                try:
                    state.update(lastLaunch=datetime.now().isoformat(timespec='seconds'), petPid=launch_pet())
                    state.pop('error', None)
                except Exception as error:
                    state['error'] = str(error)
            if current != previous or 'gptOpen' not in state:
                state['gptOpen'] = current
                path.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
            previous = current
            time.sleep(2)
    finally:
        close()


if __name__ == '__main__':
    sys.exit(main())
