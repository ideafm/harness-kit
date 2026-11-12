import copy


SOL = 'gpt-6.1-sol'
ASTRA = 'gpt-6-astra'
PROFILES = ('auto-balanced', 'thorough', 'manual')
LABELS = {'auto-balanced': 'Авто — сбалансированный', 'thorough': 'Усиленный план и ревью', 'manual': 'Один агент — настройки проекта'}


def validate(value):
    if value not in PROFILES:
        raise ValueError('Неизвестный профиль исполнения')
    return value


def snapshot(profile, executor, gemini_model=''):
    validate(profile)
    if profile == 'manual':
        return None
    if executor not in {'codex', 'gemini'} or not isinstance(gemini_model, str):
        raise ValueError('Некорректный исполнитель или модель Gemini')
    implementation = {'backend': executor, 'model': SOL if executor == 'codex' else gemini_model}
    planner = ASTRA if profile == 'thorough' else SOL
    return {'version': 1, 'profile': profile, 'stages': {
        'plan': {'backend': 'codex', 'model': planner},
        'implement': implementation,
        'check': {'backend': executor, 'model': ''},
        'review': {'backend': 'codex', 'model': planner}},
        'models': {'sol': SOL, 'astra': ASTRA}, 'implementation_origin': copy.deepcopy(implementation), 'implementation_level': 0, 'strong_plan': profile == 'thorough', 'history': []}


def route(task, stage):
    policy = task['data'].get('execution_policy')
    if not policy:
        return None
    if policy.get('version') != 1 or policy.get('profile') not in PROFILES or stage not in policy.get('stages', {}):
        raise ValueError('Политика исполнения не поддерживается')
    result = policy['stages'][stage]
    if result.get('backend') not in {'codex', 'gemini'} or not isinstance(result.get('model'), str):
        raise ValueError('Повреждён маршрут исполнения')
    return result


def strengthen_plan(task, result):
    policy = task['data'].get('execution_policy')
    if not policy or policy['strong_plan']:
        return False
    from .approval import requires_approval
    risky = requires_approval({'request': '', 'approval_mode': 'auto', **{key: result[key] for key in ('risk', 'scope', 'files')}})
    if not risky:
        return False
    policy['strong_plan'] = True
    policy['requires_plan_approval'] = True
    for stage in ('plan', 'review'):
        policy['stages'][stage] = {'backend': 'codex', 'model': policy['models']['astra']}
    reason = 'План выявил сложность, неопределённость или критические изменения; требуется Astra'
    policy['history'].append({'stage': 'plan', 'reason': reason, 'backend': 'codex', 'model': policy['models']['astra']})
    task['data']['routing_draft'] = {key: result[key] for key in ('specification', 'plan', 'criteria', 'files', 'risk', 'scope')}
    task['data']['plan_feedback'] = reason + '. Проверь и уточни предварительный план; не ослабляй исходные критерии.'
    return True


def escalate(task, max_attempts):
    policy = task['data'].get('execution_policy')
    stage = task['stage']
    if not policy or stage not in {'implement', 'review'}:
        return None
    attempts = task['data'].get('attempts', {}).get(stage, 0)
    if attempts < 2 or attempts >= max_attempts:
        return None
    if stage == 'review':
        target = {'backend': 'codex', 'model': policy['models']['astra']}
    else:
        origin = policy['implementation_origin']
        level = (1 if attempts == 2 else 2) if origin['backend'] == 'gemini' else 1
        if level <= policy['implementation_level']:
            return None
        target = {'backend': 'codex', 'model': policy['models']['sol'] if origin['backend'] == 'gemini' and level == 1 else policy['models']['astra']}
        policy['implementation_level'] = level
    if policy['stages'][stage] == target:
        return None
    policy['stages'][stage] = target
    reason = 'Повторные попытки без завершения этапа; повышаем модель без ослабления проверок'
    record = {'stage': stage, 'reason': reason, **target}
    policy['history'].append(record)
    return record
