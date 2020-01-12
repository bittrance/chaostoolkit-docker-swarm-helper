# -*- coding: utf-8 -*-

import bottle
import chaosswarm_helper.app
import pytest
import threading
import webtest

from hamcrest import *
from types import SimpleNamespace
from unittest.mock import Mock
from wsgiref.simple_server import make_server

bottle.debug(True)

def free_port_number():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

@pytest.fixture()
def running_task():
    return {
        'Spec': {'ContainerSpec': {'Image': 'redis'}},
        'NodeID': 'ze-node',
        'Status': {'ContainerStatus': {'ContainerID': 'ze-container'}},
    }

@pytest.fixture()
def client_with_running_task(running_task):
    client = Mock()
    service = Mock()
    service.tasks = Mock(return_value=[running_task])
    client.services.list = Mock(return_value=[service])
    return client

@pytest.fixture()
def test_app():
    mock_client = Mock()
    mock_client.containers.get = Mock(return_value=SimpleNamespace(name='ze-container-name'))
    app = chaosswarm_helper.app.app
    app.config['docker_client'] = mock_client
    app.config['pumba'] = '/bin/echo'
    yield webtest.TestApp(app)

@pytest.fixture()
def mock_node():
    node = bottle.Bottle()
    @node.post('/execute')
    def execute():
        return {
            'status': 'success',
            'output': bottle.request.json['container'],
        }
    port = free_port_number()
    node.config['node_port'] = port
    server = make_server('localhost', port, node)
    t = threading.Thread(target=server.serve_forever)
    t.start()
    yield node
    server.shutdown()
    t.join()

def test_resolve_targets_returns_tasks(client_with_running_task):
    res = chaosswarm_helper.app.resolve_targets(client_with_running_task, {'services': {'name': 'ze-service'}})
    assert res == [('ze-node', 'ze-container')]

def test_resolve_targets_returns_empty_for_unknown_service():
    client = Mock()
    client.services.list = Mock(return_value=[])
    res = chaosswarm_helper.app.resolve_targets(client, {'services': {'name': 'no-such'}})
    assert res == []

def test_node_to_helper_table_returns_table(client_with_running_task):
    res = chaosswarm_helper.app.node_to_helper_table(client_with_running_task)
    assert res == {'ze-node': 'ze-container'}

def test_node_to_helper_table_aborts_when_not_finding_self():
    client = Mock()
    client.services.list = Mock(return_value=[])
    assert_that(
        calling(chaosswarm_helper.app.node_to_helper_table).with_args(client),
        raises(bottle.HTTPError)
    )

@pytest.mark.parametrize('selector', [1, '1'])
def test_select_one_target(selector):
    candidates = [('node-1', 'container-1'), ('node-2', 'container-2')]
    target = chaosswarm_helper.app.select_target_containers(candidates, selector)
    assert len(target) == 1
    assert target[0] in candidates

def test_select_target_containers_fails_invalid_selector():
    assert_that(
        calling(chaosswarm_helper.app.select_target_containers).with_args([], 'foo'),
        raises(RuntimeError)
    )

def test_delegate_to_helpers(mock_node):
    helpers = {'node1': 'localhost', 'node2': 'localhost'}
    targets = [('node1', 'container1'), ('node2', 'container2')]
    results = chaosswarm_helper.app.delegate_to_helpers(helpers, targets, ['action'], mock_node.config)
    assert_that(results, contains_inanyorder(has_entry('output', 'container1'), has_entry('output', 'container2')))

def test_delegate_to_helpers_with_missing_helper(mock_node):
    helpers = {'node1': 'localhost'}
    targets = [('node1', 'container1'), ('node2', 'container2')]
    results = chaosswarm_helper.app.delegate_to_helpers(helpers, targets, ['action'], mock_node.config)
    assert_that(
        results,
        contains_inanyorder(
            has_entry('status', 'success'),
            has_entry('status', 'failure')
        )
    )

def test_delegate_to_helpers_tries_all_targets(mock_node):
    helpers = {'node1': 'no.such.helper'}
    targets = [('node1', 'container1'), ('node1', 'container2')]
    results = chaosswarm_helper.app.delegate_to_helpers(helpers, targets, ['action'], mock_node.config)
    assert_that(
        results,
        contains(
            has_entry('status', 'failure'),
            has_entry('status', 'failure')
        )
    )

def test_abort_on_failure():
    results = [
        {'status': 'failure', 'message': 'badness'},
        {'status': 'success', 'output': 'ok!'}
    ]
    try:
        chaosswarm_helper.app.abort_on_failure(results)
        assert False, 'Expected HTTPError'
    except bottle.HTTPError as err:
        assert err.status_code == 500
        assert_that(err.body, contains_string('badness'))

def test_execute_pumba_kill(test_app):
    response = test_app.post_json('/execute', {
        'action': ['pumba', 'kill', 'container'],
        'container': 'ze-container'
    })
    assert response.status_code == 200
    assert response.json['status'] == 'success'
    assert response.json['target'] == 'ze-container'
    assert response.json['output'] == 'kill container ze-container-name\n'

def test_execute_command_fails(test_app):
    test_app.app.config['pumba'] = '/bin/false'
    response = test_app.post_json('/execute', {
        'action': ['pumba', 'kill', 'container'],
        'container': 'ze-container'
    }, expect_errors=True)
    assert response.status_code == 500
    assert response.json['status'] == 'failure'
    assert response.json['message'] == ''

def test_execute_no_such_command(test_app):
    test_app.app.config['pumba'] = '/no/such/path'
    response = test_app.post_json('/execute', {
        'action': ['pumba', 'kill', 'container'],
        'container': 'ze-container'
    }, expect_errors=True)
    assert response.status_code == 500
    assert response.json['status'] == 'failure'
    assert response.json['message'] == '/no/such/path: command not found'
