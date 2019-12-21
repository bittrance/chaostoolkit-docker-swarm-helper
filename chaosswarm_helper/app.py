# -*- coding: utf-8 -*-

import json
import subprocess

from bottle import Bottle, abort, HTTPResponse, request, run

app = Bottle()

@app.post('/execute')
def execute():
    cmd = request.json['action']
    if cmd[0] == 'pumba':
        cmd[0] = app.config.get('pumba', 'pumba')
    else:
        abort(400, 'known actions: pumba')
    container = request.json['container']
    cmd.append(container)
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)
    except FileNotFoundError:
        abort_json({'status': 'failure', 'error': '%s: command not found' % cmd[0]})
    if result.returncode != 0:
        abort_json({'status': 'failure', 'error': result.stderr})
    else:
        return {'status': 'success', 'output': result.stdout}

def abort_json(data):
    raise HTTPResponse(
        status=500,
        content_type='application/json',
        body=json.dumps(data),
    )
