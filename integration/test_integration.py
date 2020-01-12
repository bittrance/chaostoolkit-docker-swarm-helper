import os
import time

import docker
import pytest
import requests

from hamcrest import *

def build_helper_image(client):
    basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    client.images.build(
        tag='chaos-swarm-helper-test',
        path=basedir,
        rm=True,
    )

def create_helper_service(client):
    return client.services.create(
        image='chaos-swarm-helper-test',
        mounts=['/var/run/docker.sock:/var/run/docker.sock:rw'],
        labels={'chaos-swarm-helper': 'v1'},
        endpoint_spec=docker.types.EndpointSpec(mode='dnsrr', ports={8080: (8080, 'tcp', 'host')}),
        mode=docker.types.ServiceMode('global')
    )

def await_helpers_healthy():
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            response = requests.get('http://localhost:8080/health', timeout=0.25)
            if response.status_code == 200:
                break
        except requests.exceptions.ConnectionError:
            pass
        except requests.exceptions.ReadTimeout:
            pass
    else:
        raise RuntimeError('Timeout waiting for helper service')

def await_container_status(client, id, status, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        container = client.containers.get(id)
        if container is not None and container.status == status:
            return
    raise AssertionError(
        'Timeout awaiting status %s on %s: %s' % (status, id, container.attrs)
    )

def print_log_tail(service):
    for line in service.logs(stdout=True, stderr=True):
        print(line.decode().rstrip())

@pytest.fixture(scope='module')
def client():
    return docker.from_env()

@pytest.fixture(scope='module', autouse=True)
def ensure_helpers(client):
    filters = {
      'label': 'chaos-swarm-helper=v1'
    }
    installed = client.services.list(filters=filters)
    if len(installed) == 1:
        installed[0].remove()
    elif len(installed) > 1:
        raise RuntimeError('more than one helper service')

    build_helper_image(client)
    helpers = create_helper_service(client)
    await_helpers_healthy()
    yield helpers
    print_log_tail(helpers)
    helpers.remove()

@pytest.fixture()
def test_service(client):
    service = client.services.create(image='redis')
    time.sleep(10)
    yield service
    service.remove()

def test_kill_one_task(client, test_service):
    first_container_id = test_service.tasks()[0]['Status']['ContainerStatus']['ContainerID']
    response = requests.post(
        'http://localhost:8080/submit',
        json={
            'selector': {'services': {'id': test_service.id}},
            'targets': 1,
            'action': ['pumba', 'kill', 'container'],
        }
    )
    assert response.status_code == 200
    assert response.json()['executions'][0]['target'] == first_container_id
    await_container_status(client, first_container_id, 'exited')

def test_submit_finds_no_targets():
    response = requests.post(
        'http://localhost:8080/submit',
        json={
            'selector': {'services': {'name': 'no-such-service'}},
            'targets': 1,
            'action': ['pumba'],
        }
    )
    assert response.status_code == 400
    assert response.json()['status'] == 'failure'
    assert response.json()['message'].startswith('no targets found')

def test_submit_encounters_error(test_service):
    response = requests.post(
        'http://localhost:8080/submit',
        json={
            'selector': {'services': {'id': test_service.id}},
            'targets': 1,
            'action': ['no-such-command'],
        }
    )
    assert response.status_code == 500 # TODO: 400
    assert response.json()['status'] == 'failure'
    assert response.json()['message'].startswith('known actions')
