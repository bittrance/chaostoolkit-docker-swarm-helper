# -*- coding: utf-8 -*-

import bottle
import chaosswarm_helper.app
import pytest
import webtest

from hamcrest import *
from unittest.mock import Mock

bottle.debug(True)

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
    app = chaosswarm_helper.app.app
    app.config['pumba'] = '/bin/echo'
    yield webtest.TestApp(app)

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

def test_execute_pumba_kill(test_app):
    response = test_app.post_json('/execute', {
        'action': ['pumba', 'kill', 'container'],
        'container': 'ze-container'
    })
    assert response.status_code == 200
    assert response.json['status'] == 'success'
    assert response.json['target'] == 'ze-container'
    assert response.json['output'] == 'kill container ze-container\n'

def test_execute_command_fails():
    app = chaosswarm_helper.app.app
    app.config['pumba'] = '/bin/false'
    response = webtest.TestApp(app).post_json('/execute', {
        'action': ['pumba', 'kill', 'container'],
        'container': 'ze-container'
    }, expect_errors=True)
    assert response.status_code == 500
    assert response.json['status'] == 'failure'
    assert response.json['message'] == ''

def test_execute_no_such_command():
    app = chaosswarm_helper.app.app
    app.config['pumba'] = '/no/such/path'
    response = webtest.TestApp(app).post_json('/execute', {
        'action': ['pumba', 'kill', 'container'],
        'container': 'ze-container'
    }, expect_errors=True)
    assert response.status_code == 500
    assert response.json['status'] == 'failure'
    assert response.json['message'] == '/no/such/path: command not found'
