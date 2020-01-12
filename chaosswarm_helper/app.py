# -*- coding: utf-8 -*-
# pylint: disable=unsubscriptable-object

"""
This is the Docker Swarm helper service. When installed into a Docker swarm
cluster, it enables the Chaos Toolkit Docker Swarm extension to send commands
to individual Docker containers ("tasks") in services on that cluster.
"""

import json
import logging
import random
import subprocess

import docker
import requests

from bottle import Bottle, abort, HTTPError, HTTPResponse, request, run

app = Bottle()
logging.basicConfig(level='INFO')

@app.error(400)
@app.error(500)
def format_and_log_errors(error):
    if error.status_code >= 500:
        logging.error(error.traceback)
    return HTTPResponse(
        status=error.status,
        body=json.dumps({
            'status': 'failure',
            'message': error.body,
            'traceback': error.traceback
        }),
        content_type='application/json'
    )

@app.get('/health')
def health():
    return 'ok'

@app.post('/submit')
def submit():
    """
    Submit an action to be applied to selected service(s). Depending on the
    action, it will either be applied directly (e.g. scaling a service) or
    will be posted to helpers on relevant target nodes via the /execute
    endpoint.
    """
    payload = request.json
    selector = payload['selector']
    client = app.config.get('docker_client', docker.from_env())
    candidates = resolve_targets(client, selector)
    if len(candidates) == 0:
        raise HTTPError(status=400, body='no targets found for %s' % selector)
    targets = select_target_containers(candidates, payload['targets'])
    helpers = node_to_helper_table(client)
    results = delegate_to_helpers(helpers, targets, payload['action'], app.config)
    abort_on_failure(results)
    return {'status': 'success', 'executions': results}

def resolve_targets(client, selectors):
    service_filters = selectors['services']
    task_filters = selectors.get('tasks', None)
    services = client.services.list(filters=service_filters)
    candidates = []
    for service in services:
        for task in service.tasks(filters=task_filters):
            container_id = task['Status']['ContainerStatus']['ContainerID']
            candidates.append((task['NodeID'], container_id))
    return candidates

def select_target_containers(candidates, selector):
    if selector not in [1, '1']:
        raise RuntimeError('Invalid selector %s' % selector)
    return random.sample(candidates, 1)

def node_to_helper_table(client):
    self = client.services.list(filters={'label': 'chaos-swarm-helper=v1'})
    if len(self) != 1:
        abort(500, 'Expected one helper service [label chaos-swarm-helper=v1], found %s' % self)
    table = {}
    for task in self[0].tasks():
        table[task['NodeID']] = task['Status']['ContainerStatus']['ContainerID']
    return table

def delegate_to_helpers(helpers, targets, action, config):
    port = config.get('node_port', 8080)
    results = []
    for (node, container) in targets:
        try:
            helper = helpers[node]
            response = requests.post(
                'http://%s:%d/execute' % (helper[:12], port),
                json={'container': container, 'action': action},
                timeout=3
            )
            results.append(response.json())
        except KeyError:
            results.append({
                'status': 'failure',
                'target': container,
                'message': 'no helper active on Swarm node %s' % node
            })
        except Exception as err:
            results.append({
                'status': 'failure',
                'target': container,
                'message': str(err),
            })
    return results

def abort_on_failure(results):
    for result in results:
        if result['status'] == 'failure':
            raise HTTPError(status_code=500, body=result['message'])

@app.post('/execute')
def execute():
    """
    Execute a command on a container on the local node. This is an internal API;
    you probably want to use the /submit endpoint.
    """
    client = app.config.get('docker_client', docker.from_env())
    cmd = request.json['action']
    if cmd[0] == 'pumba':
        cmd[0] = app.config.get('pumba', 'pumba')
    else:
        abort(400, 'known actions: pumba')
    container = request.json['container']
    cmd.append(client.containers.get(container).name)
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=2, text=True)
    except FileNotFoundError as err:
        raise HTTPError(status=500, body='%s: command not found' % cmd[0])
    if result.returncode != 0:
        raise HTTPError(status=500, body=result.stderr)
    else:
        logging.info('Executed %s: out=%s, err=%s' % (cmd, result.stdout, result.stderr))
        return {'status': 'success', 'target': container, 'output': result.stdout}
