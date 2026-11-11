from .project_view import ProjectView


def publish(store, ident):
    path = store.home / 'runtime-profile.json'
    if not path.exists() and not path.is_symlink():
        return
    task = store.get(ident)
    if task['state'] != 'review' or task['stage'] != 'done' or task['data'].get('check_receipt', {}).get('exit_code') != 0:
        return
    try:
        view = ProjectView(store.root)
        with view.lock('control.lock', True):
            if view.lifecycle()['manually_stopped']:
                return
            view.select(ident, 'checked')
            view.start(automatic=True)
        task = store.get(ident)
        task['data'].pop('preview_error', None)
        store.save(task, 'preview_start_requested', {'mode': 'checked'},
                   expected='review', expected_updated=task['updated'])
    except (OSError, ValueError, RuntimeError) as error:
        task = store.get(ident)
        if task['state'] != 'review':
            return
        task['data']['preview_error'] = str(error)
        store.save(task, 'preview_start_failed', {'reason': str(error)},
                   expected='review', expected_updated=task['updated'])
