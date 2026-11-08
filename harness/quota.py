import json
import math
import os
import selectors
import subprocess
import time
from datetime import datetime

from .security import safe_env, validate_backend
from .state import atomic_json


class QuotaPause(Exception):
    def __init__(self, reason, retry_at, manual=False):
        super().__init__(reason)
        self.retry_at = retry_at
        self.manual = manual


def normalize(result, now):
    buckets = result.get('rateLimitsByLimitId') or {'default': result.get('rateLimits') or result.get('quota')}
    windows = []
    for bucket in buckets.values():
        if not isinstance(bucket, dict):
            continue
        for name in ('primary', 'secondary'):
            window = bucket.get(name)
            if not isinstance(window, dict):
                continue
            used, reset = window.get('usedPercent'), window.get('resetsAt')
            if type(used) not in (int, float) or not math.isfinite(used) or not 0 <= used <= 100:
                raise ValueError('Некорректный расход лимита')
            if type(reset) not in (int, float) or not math.isfinite(reset) or reset <= now:
                raise ValueError('Нет свежего времени сброса лимита')
            windows.append({'used_percent': used, 'resets_at': reset, 'window_minutes': window.get('windowDurationMins')})
    if not any(window['window_minutes'] == 300 for window in windows):
        raise ValueError('Пятичасовой лимит недоступен')
    return {'observed_at': now, 'windows': windows, 'ordinary_usage_allowed': result.get('ordinaryUsageAllowed', True)}


def normalize_gemini(result, now):
    command = result.get('command')
    data = command.get('data') if isinstance(command, dict) else None
    groups = data.get('groups') if isinstance(data, dict) else None
    if not isinstance(groups, list):
        raise ValueError('В ответе Gemini отсутствуют группы квот')
    gemini_group = next((g for g in groups if isinstance(g, dict) and g.get('name') == 'Gemini Models'), None)
    if not gemini_group or not isinstance(gemini_group.get('buckets'), list):
        raise ValueError('Группа Gemini Models не найдена')
    windows = []
    for bucket in gemini_group['buckets']:
        if not isinstance(bucket, dict):
            continue
        win = bucket.get('window')
        if win == '5h':
            window_minutes = 300
        elif win == 'weekly':
            window_minutes = 10080
        else:
            continue
        remaining = bucket.get('remaining_fraction')
        if type(remaining) not in (int, float) or not math.isfinite(remaining) or not 0 <= remaining <= 1:
            raise ValueError('Некорректный остаток лимита Gemini')
        used = round((1.0 - remaining) * 100, 2)
        reset_str = bucket.get('reset_time')
        if not isinstance(reset_str, str) or not reset_str.strip():
            raise ValueError('Отсутствует время сброса лимита Gemini')
        try:
            parsed = datetime.fromisoformat(reset_str.replace('Z', '+00:00'))
        except Exception:
            raise ValueError('Некорректный формат времени сброса лимита Gemini')
        if parsed.tzinfo is None:
            raise ValueError('Время сброса лимита Gemini должно содержать часовой пояс')
        reset = parsed.timestamp()
        if reset <= now:
            raise ValueError('Нет свежего времени сброса лимита')
        windows.append({'used_percent': used, 'resets_at': reset, 'window_minutes': window_minutes})
    if not any(window['window_minutes'] == 300 for window in windows):
        raise ValueError('Пятичасовой лимит Gemini недоступен')
    if not any(window['window_minutes'] == 10080 for window in windows):
        raise ValueError('Недельный лимит Gemini недоступен')
    return {'observed_at': now, 'windows': windows, 'ordinary_usage_allowed': True}


def resolve_quota_driver(config, backend=None):
    if not isinstance(config, dict):
        raise RuntimeError('Некорректная конфигурация лимитов')
    selected = validate_backend(backend or config.get('backend', 'codex'))
    if selected == 'gemini':
        driver = config.get('agy') or config.get('gemini')
        if not isinstance(driver, str) or not driver.strip():
            raise RuntimeError('Не задана конфигурация Gemini (agy) для проверки лимитов')
        return selected, driver
    driver = config.get('codex')
    if not isinstance(driver, str) or not driver.strip():
        raise RuntimeError('Не задана конфигурация Codex для проверки лимитов')
    return selected, driver


def read(executable, timeout=15, backend='codex'):
    selected = validate_backend(backend)
    if not isinstance(executable, str) or not executable.strip():
        raise ValueError('Не задан исполняемый файл сервиса лимитов')
    if selected == 'gemini':
        command = [executable, '-p', '/quota', '--output-format', 'json']
        process = subprocess.run(command, capture_output=True, timeout=timeout, env=safe_env())
        if process.returncode != 0:
            raise RuntimeError(f'Сервис лимитов Gemini завершился с кодом {process.returncode}')
        try:
            payload = json.loads(process.stdout.decode())
        except Exception:
            raise ValueError('Некорректный JSON от сервиса лимитов Gemini')
        return normalize_gemini(payload, time.time())
    command = [executable, '--no-daemon', 'app-server', '--stdio', '-c', 'mcp_servers={}',
               '-c', 'features.apps=false', '-c', 'features.plugins=false']
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, env=safe_env())
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    buffer = b''
    total = 0
    def send(message):
        process.stdin.write(json.dumps(message).encode() + b'\n')
        process.stdin.flush()
    try:
        send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'harness-quota', 'version': '0.1.0'}}})
        while time.monotonic() < deadline:
            if not selector.select(max(0, deadline - time.monotonic())):
                break
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError('Сервис лимитов завершился без ответа')
            total += len(chunk)
            if total > 1048576:
                raise RuntimeError('Превышен размер ответа сервиса лимитов')
            buffer += chunk
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                message = json.loads(line)
                if message.get('id') in (1, 2) and 'error' in message:
                    raise RuntimeError('Сервис лимитов вернул ошибку')
                if message.get('id') == 1:
                    send({'method': 'initialized'})
                    send({'id': 2, 'method': 'account/rateLimits/read'})
                elif message.get('id') == 2:
                    return normalize(message['result'], time.time())
        raise TimeoutError('Не удалось получить свежий лимит за отведённое время')
    finally:
        selector.close()
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()


class Guard:
    def __init__(self, store, config):
        self.store, self.config = store, config
        self.snapshots = {}

    @property
    def snapshot(self):
        backend = self.config.get('backend', 'codex')
        return self.snapshots.get(backend)

    @snapshot.setter
    def snapshot(self, value):
        backend = self.config.get('backend', 'codex')
        if value is None:
            self.snapshots.pop(backend, None)
        else:
            self.snapshots[backend] = value

    @property
    def snapshot_backend(self):
        backend = self.config.get('backend', 'codex')
        return backend if backend in self.snapshots else None

    @snapshot_backend.setter
    def snapshot_backend(self, value):
        pass

    def check(self, starting=False, backend=None):
        if not self.config.get('quota_guard'):
            return
        selected_backend, driver = resolve_quota_driver(self.config, backend)
        now = time.time()
        ttl = 120
        try:
            policy = self.store.home / 'quota-policy.json'
            cap = None
            if policy.is_symlink():
                raise ValueError('Политика лимита заменена ссылкой')
            if policy.exists():
                settings = json.loads(policy.read_text())
                cap = settings['stop_percent']
                if type(cap) not in (int, float) or not math.isfinite(cap) or not 0 < cap <= 95:
                    raise ValueError('Некорректный порог лимита')
                activate_at = settings.get('activate_at', 0)
                if type(activate_at) not in (int, float) or not math.isfinite(activate_at) or activate_at < 0:
                    raise ValueError('Некорректное время контрольной точки')
                if now < activate_at:
                    cap = None
            cached = self.snapshots.get(selected_backend)
            needs_fetch = (starting or cached is None
                           or (now - cached['observed_at'] >= ttl)
                           or any(w['resets_at'] <= now for w in cached.get('windows', [])))
            if needs_fetch:
                current_snapshot = read(driver) if selected_backend == 'codex' else read(driver, backend='gemini')
                self.snapshots[selected_backend] = current_snapshot
                atomic_json(self.store.home / f'quota-{selected_backend}.json', current_snapshot)
                atomic_json(self.store.home / 'quota.json', current_snapshot)
            else:
                current_snapshot = cached
            for window in current_snapshot['windows']:
                threshold = 95.0
                if cap is not None and window['window_minutes'] == 300:
                    threshold = min(threshold, cap)
                if window['resets_at'] <= now:
                    self.snapshots.pop(selected_backend, None)
                    raise ValueError('Нужна свежая проверка после сброса')
                if window['used_percent'] >= threshold:
                    if cap is not None and window['window_minutes'] == 300 and window['used_percent'] >= cap:
                        raise QuotaPause(f"Пауза по запросу пользователя: использовано {window['used_percent']}%, порог {cap}%",
                                         None, manual=True)
                    raise QuotaPause(f"Защитная пауза: использовано {window['used_percent']}% лимита {selected_backend}; порог 95%",
                                     window['resets_at'] + 60)
            if not current_snapshot['ordinary_usage_allowed']:
                engine = 'Gemini' if selected_backend == 'gemini' else 'Codex'
                raise QuotaPause(f'{engine} временно не разрешает обычные запросы', now + 300)
        except QuotaPause:
            raise
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, TimeoutError, subprocess.SubprocessError):
            self.snapshots.pop(selected_backend, None)
            raise QuotaPause(f'Не удалось проверить лимит для {selected_backend}; новые вызовы запрещены', now + 60) from None
