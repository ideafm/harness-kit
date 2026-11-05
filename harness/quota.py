import json
import math
import os
import selectors
import subprocess
import time

from .security import safe_env
from .state import atomic_json


class QuotaPause(Exception):
    def __init__(self, reason, retry_at, manual=False):
        super().__init__(reason)
        self.retry_at = retry_at
        self.manual = manual


def normalize(result, now):
    buckets = result.get('rateLimitsByLimitId') or {'codex': result.get('rateLimits')}
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


def read(codex, timeout=15):
    command = [codex, '--no-daemon', 'app-server', '--stdio', '-c', 'mcp_servers={}',
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
        self.snapshot = None

    def check(self, starting=False):
        if not self.config.get('quota_guard'):
            return
        now = time.time()
        try:
            policy = self.store.home / 'quota-policy.json'
            cap = None
            if policy.is_symlink():
                raise ValueError('Политика лимита заменена ссылкой')
            if policy.exists():
                settings = json.loads(policy.read_text())
                cap = settings['stop_percent']
                if type(cap) not in (int, float) or not math.isfinite(cap) or not 0 < cap <= 94:
                    raise ValueError('Некорректный порог лимита')
                activate_at = settings.get('activate_at', 0)
                if type(activate_at) not in (int, float) or not math.isfinite(activate_at) or activate_at < 0:
                    raise ValueError('Некорректное время контрольной точки')
                if now < activate_at:
                    cap = None
            if starting or self.snapshot is None or now - self.snapshot['observed_at'] >= 15:
                self.snapshot = read(self.config['codex'])
                atomic_json(self.store.home / 'quota.json', self.snapshot)
            for window in self.snapshot['windows']:
                threshold = (90 if starting else 94) if window['window_minutes'] == 300 else 96
                if cap is not None and window['window_minutes'] == 300:
                    threshold = min(threshold, cap)
                if window['resets_at'] <= now:
                    self.snapshot = None
                    raise ValueError('Нужна свежая проверка после сброса')
                if window['used_percent'] >= threshold:
                    if cap is not None and window['window_minutes'] == 300 and window['used_percent'] >= cap:
                        raise QuotaPause(f"Пауза по запросу пользователя: использовано {window['used_percent']}%, порог {cap}%",
                                         None, manual=True)
                    raise QuotaPause(f"Защитная пауза: использовано {window['used_percent']}% лимита; порог пользователя 96%",
                                     window['resets_at'] + 60)
            if not self.snapshot['ordinary_usage_allowed']:
                raise QuotaPause('Codex временно не разрешает обычные запросы', now + 300)
        except QuotaPause:
            raise
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, TimeoutError, subprocess.SubprocessError):
            self.snapshot = None
            raise QuotaPause('Не удалось проверить лимит; новые вызовы запрещены', now + 60) from None
