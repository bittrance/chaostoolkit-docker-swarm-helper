# -*- coding: utf-8 -*-

import bottle
import chaosswarm_helper.app
import pytest
import webtest

bottle.debug(True)

@pytest.fixture()
def test_app():
    app = chaosswarm_helper.app.app
    app.config['pumba'] = '/bin/echo'
    yield webtest.TestApp(app)

def test_execute_pumba_kill(test_app):
    response = test_app.post_json('/execute', {
        'action': ['pumba', 'kill', 'container'],
        'container': 'ze-container'
    })
    assert response.status_code == 200
    assert response.json['status'] == 'success'
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
    assert response.json['error'] == ''

def test_execute_no_such_command():
    app = chaosswarm_helper.app.app
    app.config['pumba'] = '/no/such/path'
    response = webtest.TestApp(app).post_json('/execute', {
        'action': ['pumba', 'kill', 'container'],
        'container': 'ze-container'
    }, expect_errors=True)
    assert response.status_code == 500
    print(response.text)
    assert response.json['status'] == 'failure'
    assert response.json['error'] == '/no/such/path: command not found'
