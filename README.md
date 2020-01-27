# Chaos Toolkit Docker Swarm extension helper

This project builds a Docker image that enables [chaostoolkit-docker-swarm][] to execute commands against individual Docker containers in order to inject faults. This is a small Python Bottle REST API with two endpoints:

**/submit**: post a request to execute a Pumba command against some selection of tasks in a service. This endpoint resolves the request into specific containers and invokes /execute on the node which hosts that container.

**/execute**: execute a Pumba command against a specific container on the local node.

The REST API has no security and is not meant to be exposed. Rather, the Chaos Toolkit extension uses `docker exec` to invoke /submit inside the helper container on the node pointed to by the Docker environment setup (by default /var/run/docker.sock). This image contains `wget` for this purpose.

[chaostoolkit-docker-swarm-helper]: https://github.com/bittrance/chaostoolkit-docker-swarm/

## Develop

Getting started.

```bash
virtualenv -p /usr/bin/python3.8 swarmenv
. ./swarmenv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Running tests. The tests assume there is a local Docker Swarm cluster.

```bash
env PYTHONPATH=. pytest tests/
```

## Contribute

If you wish to contribute more functions to this package, you are more than welcome to do so. Please, fork this project, make your changes following the usual [PEP 8][pep8] code style, sprinkling with tests and submit a PR for review.

[pep8]: https://pycodestyle.readthedocs.io/en/latest/
