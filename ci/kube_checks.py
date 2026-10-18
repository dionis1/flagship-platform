"""Temporary image execution and read-only GitOps deployment verification."""
import argparse
import contextlib
import json
from pathlib import Path
import socket
import subprocess
import time
import uuid

from http_smoke import check


def kube(*args, data=None):
    try:
        return subprocess.check_output(['kubectl', '--request-timeout=10s', *args],
                                       input=data, text=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        Path('reports').mkdir(exist_ok=True)
        Path('reports/kubectl-last-error.txt').write_text(str(exc.output or exc))
        raise


def get(kind, name, namespace):
    return json.loads(kube('-n', namespace, 'get', kind, name, '-o', 'json'))


@contextlib.contextmanager
def forward(resource, namespace):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with open('reports/port-forward.log', 'w') as log:
        process = subprocess.Popen(['kubectl', '-n', namespace, 'port-forward',
                                    '--address=127.0.0.1', resource, f'{port}:80'],
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            yield f'http://127.0.0.1:{port}/'
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def diagnostics(namespace, app=None, pod=None):
    queries = [('get', 'pods', '-o', 'wide'), ('get', 'events', '--sort-by=.lastTimestamp')]
    if app:
        queries += [('get', 'deployment', app, '-o', 'yaml')]
    if pod:
        queries += [('describe', 'pod', pod), ('logs', pod, '--tail=100')]
    for index, query in enumerate(queries):
        result = subprocess.run(['kubectl', '--request-timeout=10s', '-n', namespace, *query],
                                capture_output=True, text=True)
        Path(f'reports/diagnostic-{namespace}-{index}.txt').write_text(result.stdout + result.stderr)


def smoke_image(image, namespace):
    name = 'image-smoke-' + uuid.uuid4().hex[:10]
    pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': name, 'namespace': namespace},
           'spec': {'restartPolicy': 'Never', 'activeDeadlineSeconds': 150,
                    'automountServiceAccountToken': False,
                    'containers': [{'name': 'app', 'image': image,
                                    'resources': {'requests': {'cpu': '25m', 'memory': '16Mi'},
                                                  'limits': {'cpu': '200m', 'memory': '128Mi'}},
                                    'securityContext': {'allowPrivilegeEscalation': False,
                                                        'seccompProfile': {'type': 'RuntimeDefault'}},
                                    'ports': [{'containerPort': 80}]}]}}
    try:
        kube('create', '-f', '-', data=json.dumps(pod))
        kube('-n', namespace, 'wait', '--for=condition=Ready', f'pod/{name}', '--timeout=90s')
        with forward('pod/' + name, namespace) as url:
            check(url)
        Path('reports/image-smoke.json').write_text(json.dumps(
            {'image': image, 'http': 'passed', 'namespace': namespace}, indent=2))
    except Exception:
        diagnostics(namespace, pod=name)
        raise
    finally:
        subprocess.run(['kubectl', '--request-timeout=10s', '-n', namespace, 'delete', 'pod', name,
                        '--ignore-not-found', '--wait=false'], check=False)


def deployed(application, deployment, pods, revision, image):
    status = application.get('status', {})
    sync = status.get('sync', {})
    if (sync.get('revision') != revision or sync.get('status') != 'Synced'
            or status.get('health', {}).get('status') != 'Healthy'):
        return False
    spec = deployment['spec']
    state = deployment.get('status', {})
    replicas = spec.get('replicas', 1)
    containers = spec['template']['spec']['containers']
    if next((c['image'] for c in containers if c['name'] == 'demo-app'), None) != image:
        return False
    if (state.get('observedGeneration', 0) < deployment['metadata']['generation']
            or replicas < 1 or any(state.get(k, 0) != replicas
                                   for k in ('replicas', 'updatedReplicas', 'availableReplicas', 'readyReplicas'))):
        return False
    active = [p for p in pods.get('items', []) if not p['metadata'].get('deletionTimestamp')]
    return len(active) == replicas and all(
        next((c['image'] for c in p['spec']['containers'] if c['name'] == 'demo-app'), None) == image
        and any(c.get('type') == 'Ready' and c.get('status') == 'True'
                for c in p.get('status', {}).get('conditions', [])) for p in active)


def verify(revision, image, timeout):
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            try:
                app = get('application', 'demo-app-dev', 'argocd')
                deployment = get('deployment', 'demo-app', 'dev')
                pods = json.loads(kube('-n', 'dev', 'get', 'pods', '-l', 'app=demo-app', '-o', 'json'))
            except subprocess.CalledProcessError as exc:
                # The first sync may not have created the Deployment yet.
                Path('reports/verification-last-error.txt').write_text(str(exc.output or exc))
                time.sleep(min(5, max(0, deadline-time.monotonic())))
                continue
            Path('reports/argocd-application.json').write_text(json.dumps(app, indent=2))
            if deployed(app, deployment, pods, revision, image):
                kube('-n', 'dev', 'rollout', 'status', 'deployment/demo-app', '--timeout=30s')
                with forward('service/demo-app', 'dev') as url:
                    check(url)
                # Catch a newer deployment racing the HTTP check.
                if deployed(get('application', 'demo-app-dev', 'argocd'),
                            get('deployment', 'demo-app', 'dev'),
                            json.loads(kube('-n', 'dev', 'get', 'pods', '-l', 'app=demo-app', '-o', 'json')),
                            revision, image):
                    Path('reports/deployment.json').write_text(json.dumps(
                        {'revision': revision, 'image': image, 'http': 'passed'}, indent=2))
                    return
            time.sleep(min(5, max(0, deadline-time.monotonic())))
        raise RuntimeError('Timed out waiting for the exact GitOps revision, image and healthy rollout')
    except Exception:
        diagnostics('dev', app='demo-app')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['image', 'deployment'])
    parser.add_argument('--image', required=True)
    parser.add_argument('--revision')
    parser.add_argument('--namespace', default='ci-tests')
    parser.add_argument('--timeout', type=int, default=360)
    args = parser.parse_args()
    Path('reports').mkdir(exist_ok=True)
    if args.mode == 'image':
        Path('reports/image-smoke.json').unlink(missing_ok=True)
        smoke_image(args.image, args.namespace)
    else:
        if not args.revision:
            parser.error('--revision is required for deployment verification')
        Path('reports/deployment.json').unlink(missing_ok=True)
        verify(args.revision, args.image, args.timeout)
