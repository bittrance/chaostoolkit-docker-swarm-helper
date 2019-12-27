# -*- coding: utf-8 -*-
# pylint: disable=unsubscriptable-object

"""
This is the Docker Swarm helper service. When installed into a Docker swarm
cluster, it enables the Chaos Toolkit Docker Swarm extension to send commands
to individual Docker containers ("tasks") in services on that cluster.
"""

import json
import random
import subprocess

import docker
import requests

from bottle import Bottle, abort, debug, HTTPResponse, request, run

app = Bottle()
debug(True)
@app.post('/submit')
def submit():
    """
    Submit an action to be applied to selected service(s). Depending on the
    action, it will either be applied directly (e.g. scaling a service) or
    will be posted to helpers on relevant target nodes via the /execute
    endpoint.
    """
    payload = request.json
    client = docker.from_env()
    candidates = resolve_targets(client, payload['selector'])
    targets = select_target_containers(candidates, payload['targets'])
    helpers = node_to_helper_table(client)

    reply = []
    for (node, container) in targets:
        try:
            helper = helpers[node]
        except KeyError:
            abort(500, 'no helper active on Swarm node %s' % node)
        response = requests.post(
            'http://%s:8080/execute' % helper,
            json={
                'container': container,
                'action': payload['action']
            }
        )
        reply.append(response.json)
    return reply

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

@app.post('/execute')
def execute():
    """
    Execute a command on a container on the local node. This is an internal API;
    you probably want to use the /submit endpoint.
    """
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
