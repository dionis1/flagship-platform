"""Run interactively on the PC; never paste tokens into chat or command arguments."""
import base64
import getpass
import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
os.environ['KUBECONFIG'] = str(ROOT / '.local/kubeconfig')


def secret(namespace, name):
    value = subprocess.check_output(['kubectl', '-n', namespace, 'get', 'secret', name,
                                     '-o', 'json'], text=True)
    return {key: base64.b64decode(data).decode() for key, data in json.loads(value)['data'].items()}


def main():
    print('Configure credentials for the LOCAL flagship Jenkins instance (http://localhost:8080).')
    creds = secret('jenkins', 'jenkins')
    username = creds['jenkins-admin-user']
    password = creds['jenkins-admin-password']
    session = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    auth = 'Basic ' + base64.b64encode((username + ':' + password).encode()).decode()
    with session.open(urllib.request.Request('http://127.0.0.1:8080/crumbIssuer/api/json',
                                            headers={'Authorization': auth})) as response:
        crumb = json.load(response)
    for credential_id, description in [('ghcr-creds', 'GHCR package publish/read'),
                                        ('github-push', 'GitHub repository Contents read/write')]:
        user = input(f'{description} username [dionis1]: ').strip() or 'dionis1'
        token = getpass.getpass(f'{credential_id} token (hidden): ')
        if not token:
            print(f'Skipped {credential_id}')
            continue
        body = {'': '0', 'credentials': {'scope': 'GLOBAL', 'id': credential_id,
                'username': user, 'password': token, 'description': description,
                '$class': 'com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl'}}
        request = urllib.request.Request('http://127.0.0.1:8080/credentials/store/system/domain/_/createCredentials',
            data=urllib.parse.urlencode({'json': json.dumps(body)}).encode(),
            headers={'Authorization': auth, crumb['crumbRequestField']: crumb['crumb']})
        with session.open(request) as response:
            response.read()
        print(f'Stored {credential_id} in local Jenkins. Existing IDs must be updated through the UI.')
    key = getpass.getpass('Datadog EU API key (hidden; Enter to skip): ')
    if key:
        data = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'datadog-secret', 'namespace': 'datadog'},
                'type': 'Opaque', 'stringData': {'api-key': key}}
        subprocess.run(['kubectl', 'create', 'namespace', 'datadog'], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        subprocess.run(['kubectl', 'apply', '-f', '-'], input=json.dumps(data), text=True, check=True,
                       stdout=subprocess.DEVNULL)
        print('Stored Datadog API key in the local cluster. Install Datadog using local/README.md.')
    print('Done. No tokens were written to repository files.')


if __name__ == '__main__':
    main()
