"""Prepare official Argo CD manifests with resource caps for the local lab."""
from pathlib import Path
import urllib.request
import yaml

root = Path(__file__).resolve().parents[1]
url = 'https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.5/manifests/install.yaml'
with urllib.request.urlopen(url, timeout=60) as response:
    documents = list(yaml.safe_load_all(response.read()))
for resource in documents:
    if not resource:
        continue
    name = resource['metadata']['name']
    if resource.get('kind') in ('Deployment', 'StatefulSet'):
        if name in ('argocd-dex-server', 'argocd-applicationset-controller', 'argocd-notifications-controller'):
            resource['spec']['replicas'] = 0
        for container in resource['spec']['template']['spec']['containers']:
            memory = '512Mi' if name in ('argocd-application-controller', 'argocd-repo-server') else '256Mi'
            container['resources'] = {'requests': {'cpu': '50m', 'memory': '64Mi'},
                                      'limits': {'cpu': '500m', 'memory': memory}}
    if resource.get('kind') == 'ConfigMap' and name == 'argocd-cmd-params-cm':
        resource.setdefault('data', {})['server.insecure'] = 'true'
    if resource.get('kind') == 'Service' and name == 'argocd-server':
        resource['spec']['type'] = 'NodePort'
        resource['spec']['ports'] = [{'name': 'http', 'port': 80, 'targetPort': 8080, 'nodePort': 30081}]
(root / '.local/argocd-install.yaml').write_text(yaml.safe_dump_all(documents, sort_keys=False))
