import contextlib
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci'))
from change_policy import classify, MANIFEST
from http_smoke import check, EXPECTED
from kube_checks import deployed, verify, smoke_image, configure_context
from promote import promote

IMAGE = 'ghcr.io/dionis1/flagship-demo-app@sha256:' + 'a' * 64
ROOT = Path(__file__).resolve().parents[1]


def git(*args, cwd=None):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()


@contextlib.contextmanager
def cd(path):
    original = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        git('init', '-q', '-b', 'main', str(self.repo))
        git('config', 'user.name', 'Test', cwd=self.repo)
        git('config', 'user.email', 'test@example.invalid', cwd=self.repo)
        p = self.repo / MANIFEST
        p.parent.mkdir(parents=True)
        p.write_text((ROOT / MANIFEST).read_text())
        self.commit('initial')
        self.base = git('rev-parse', 'HEAD', cwd=self.repo)
        self.remote = self.root / 'remote.git'
        git('clone', '-q', '--bare', str(self.repo), str(self.remote))
        git('remote', 'add', 'origin', str(self.remote), cwd=self.repo)

    def commit(self, message):
        git('add', '.', cwd=self.repo)
        git('commit', '-q', '-m', message, cwd=self.repo)

    def change(self, path, value):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value)
        self.commit('change')

    def action(self, base=None):
        with cd(self.repo):
            return classify(self.base if base is None else base)

    def promote(self):
        with cd(self.repo):
            return promote(self.base, IMAGE, str(self.remote))

    def test_application_change_builds(self):
        self.change('app/index.html', 'hello')
        self.assertEqual(self.action(), 'build')

    def test_docs_skip(self):
        self.change('README.md', 'documentation')
        self.assertEqual(self.action(), 'skip')

    def test_ci_changes_build(self):
        self.change('ci/check.py', 'print(1)')
        self.assertEqual(self.action(), 'build')

    def test_manifest_only_validates(self):
        p = self.repo / MANIFEST
        self.change(MANIFEST, p.read_text().replace('replicas: 1', 'replicas: 2'))
        self.assertEqual(self.action(), 'validate')

    def test_generated_image_update_skips(self):
        p = self.repo / MANIFEST
        self.change(MANIFEST, p.read_text().replace('          image: ', '          image: updated-'))
        self.assertEqual(self.action(), 'skip')
        self.assertEqual(self.action(''), 'skip')
        self.assertEqual(self.action('missing-history'), 'skip')

    def test_mixed_changes_build(self):
        self.change('app/index.html', 'new page')
        p = self.repo / MANIFEST
        self.change(MANIFEST, p.read_text().replace('          image: ', '          image: updated-'))
        self.assertEqual(self.action(), 'build')

    def test_full_range_not_just_last_commit(self):
        self.change('app/index.html', 'new page')
        self.change('README.md', 'documentation')
        self.assertEqual(self.action(), 'build')

    def test_missing_base_builds(self):
        self.assertEqual(self.action('does-not-exist'), 'build')
        self.assertEqual(self.action(''), 'build')

    def test_commit_message_cannot_bypass(self):
        p = self.repo / 'app/index.html'
        p.parent.mkdir()
        p.write_text('bad page')
        self.commit('Deploy via Jenkins [skip ci]\n\nCI-Deployment: true')
        self.assertEqual(self.action(), 'build')

    def test_promotion_writes_digest_and_revision(self):
        revision = self.promote()
        text = git('--git-dir=' + str(self.remote), 'show', 'main:' + MANIFEST)
        self.assertIn(IMAGE, text)
        self.assertEqual(revision, git('--git-dir=' + str(self.remote), 'rev-parse', 'main'))
        self.assertEqual((self.repo / 'reports/deployment-revision.txt').read_text().strip(), revision)

    def test_identical_image_reuses_revision_without_empty_commit(self):
        first = self.promote()
        git('fetch', 'origin', 'main', cwd=self.repo)
        git('checkout', '--detach', 'FETCH_HEAD', cwd=self.repo)
        with cd(self.repo):
            second = promote(first, IMAGE, str(self.remote))
        self.assertEqual(first, second)
        self.assertEqual(git('--git-dir=' + str(self.remote), 'rev-parse', 'main'), first)

    def test_promotion_preserves_new_remote_docs(self):
        self.change('README.md', 'new remote docs')
        git('push', 'origin', 'main', cwd=self.repo)
        self.promote()
        self.assertEqual(git('--git-dir=' + str(self.remote), 'show', 'main:README.md'), 'new remote docs')

    def test_stale_application_rejected(self):
        self.change('app/index.html', 'newer app')
        git('push', 'origin', 'main', cwd=self.repo)
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            self.promote()

    def test_new_manifest_changes_require_revalidation(self):
        p = self.repo / MANIFEST
        self.change(MANIFEST, p.read_text().replace('replicas: 1', 'replicas: 2'))
        git('push', 'origin', 'main', cwd=self.repo)
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            self.promote()

    def test_competing_deployment_rejected(self):
        self.promote()
        with self.assertRaisesRegex(RuntimeError, 'Another deployment'):
            self.promote()

    def test_tags_rejected_for_promotion(self):
        with cd(self.repo), self.assertRaises(ValueError):
            promote(self.base, 'nginx:latest', str(self.remote))

    def test_push_race_retries_and_preserves_edit(self):
        real_run = subprocess.run
        raced = False

        def run(args, *a, **kw):
            nonlocal raced
            if len(args) > 3 and args[0] == 'git' and args[1] == '-C' and 'push' in args and not raced:
                raced = True
                self.change('README.md', 'concurrent documentation')
                real_run(['git', '-C', str(self.repo), 'push', 'origin', 'main'], check=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return real_run(args, *a, **kw)

        with patch('subprocess.run', side_effect=run):
            self.promote()
        self.assertTrue(raced)
        self.assertEqual(git('--git-dir=' + str(self.remote), 'show', 'main:README.md'),
                         'concurrent documentation')


class HTTPTests(unittest.TestCase):
    def server(self, code, body):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(code)
                self.end_headers()
                self.wfile.write(body.encode())
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return 'http://127.0.0.1:' + str(server.server_port)

    def test_valid_application_passes(self):
        check(self.server(200, EXPECTED), timeout=1)

    def test_wrong_content_fails(self):
        with self.assertRaises(RuntimeError):
            check(self.server(200, 'wrong application'), timeout=.15)

    def test_missing_page_fails(self):
        with self.assertRaises(RuntimeError):
            check(self.server(404, EXPECTED), timeout=.15)

    def test_server_error_fails(self):
        with self.assertRaises(RuntimeError):
            check(self.server(500, EXPECTED), timeout=.15)


class ContextTests(unittest.TestCase):
    def test_projected_token_is_referenced_not_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'token').write_text('never-copy-this-token')
            (root / 'ca.crt').write_text('certificate')
            with patch.dict(os.environ, {'KUBERNETES_SERVICE_HOST': '10.43.0.1'}, clear=True), \
                 patch('kube_checks.Path.home', return_value=root / 'home'):
                configure_context(root)
                config = Path(os.environ['KUBECONFIG'])
                try:
                    text = config.read_text()
                    self.assertIn('tokenFile', text)
                    self.assertNotIn('never-copy-this-token', text)
                    self.assertEqual(config.stat().st_mode & 0o777, 0o600)
                    self.assertIn('https://kubernetes.default.svc', text)
                finally:
                    config.unlink()

    def test_explicit_local_context_is_preserved(self):
        with patch.dict(os.environ, {'KUBECONFIG': '/private/config'}, clear=True):
            configure_context(Path('/missing'))
            self.assertEqual(os.environ['KUBECONFIG'], '/private/config')

    def test_missing_projected_token_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'KUBERNETES_SERVICE_HOST': '10.43.0.1'}, clear=True), \
             patch('kube_checks.Path.home', return_value=Path(directory)):
            with self.assertRaisesRegex(RuntimeError, 'projected'):
                configure_context(Path(directory))

    def test_missing_local_context_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
             patch('kube_checks.Path.home', return_value=Path(directory)):
            with self.assertRaisesRegex(RuntimeError, 'KUBECONFIG'):
                configure_context(Path(directory))


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.app = {'status': {'sync': {'revision': 'commit', 'status': 'Synced'},
                               'health': {'status': 'Healthy'}}}
        self.deployment = {'metadata': {'generation': 3},
                           'spec': {'replicas': 1, 'template': {'spec': {'containers': [
                               {'name': 'demo-app', 'image': IMAGE}]}}},
                           'status': {'observedGeneration': 3, 'replicas': 1,
                                      'updatedReplicas': 1, 'readyReplicas': 1, 'availableReplicas': 1}}
        self.pods = {'items': [{'metadata': {}, 'spec': {'containers': [
            {'name': 'demo-app', 'image': IMAGE}]}, 'status': {'conditions': [
                {'type': 'Ready', 'status': 'True'}]}}]}

    def valid(self):
        return deployed(self.app, self.deployment, self.pods, 'commit', IMAGE)

    def test_exact_revision_and_image_pass(self):
        self.assertTrue(self.valid())

    def test_old_healthy_revision_fails(self):
        self.app['status']['sync']['revision'] = 'old'
        self.assertFalse(self.valid())

    def test_out_of_sync_fails(self):
        self.app['status']['sync']['status'] = 'OutOfSync'
        self.assertFalse(self.valid())

    def test_unhealthy_fails(self):
        self.app['status']['health']['status'] = 'Degraded'
        self.assertFalse(self.valid())

    def test_wrong_deployed_image_fails(self):
        self.deployment['spec']['template']['spec']['containers'][0]['image'] = 'old'
        self.assertFalse(self.valid())

    def test_incomplete_rollout_fails(self):
        self.deployment['status']['updatedReplicas'] = 0
        self.assertFalse(self.valid())

    def test_unobserved_generation_fails(self):
        self.deployment['status']['observedGeneration'] = 2
        self.assertFalse(self.valid())

    def test_old_pod_fails(self):
        self.pods['items'][0]['spec']['containers'][0]['image'] = 'old'
        self.assertFalse(self.valid())

    def test_unready_pod_fails(self):
        self.pods['items'][0]['status']['conditions'][0]['status'] = 'False'
        self.assertFalse(self.valid())

    def test_zero_replicas_fails(self):
        self.deployment['spec']['replicas'] = 0
        self.assertFalse(self.valid())

    def test_missing_image_cleans_up(self):
        with tempfile.TemporaryDirectory() as temp, cd(temp):
            Path('reports').mkdir()
            with patch('kube_checks.kube', side_effect=[None, RuntimeError('ImagePullBackOff')]), \
                 patch('kube_checks.diagnostics') as diag, patch('kube_checks.subprocess.run') as run:
                with self.assertRaises(RuntimeError):
                    smoke_image(IMAGE, 'ci-tests')
                diag.assert_called_once()
                self.assertIn('delete', run.call_args.args[0])

    def test_verification_records_success_after_service_http(self):
        with tempfile.TemporaryDirectory() as temp, cd(temp):
            Path('reports').mkdir()
            def resource(kind, name, namespace):
                return self.app if kind == 'application' else self.deployment
            with patch('kube_checks.get', side_effect=resource), \
                 patch('kube_checks.kube', return_value=__import__('json').dumps(self.pods)), \
                 patch('kube_checks.forward', return_value=contextlib.nullcontext('http://service/')), \
                 patch('kube_checks.check') as http:
                verify('commit', IMAGE, timeout=1)
                http.assert_called_once_with('http://service/')
                self.assertTrue(Path('reports/deployment.json').is_file())

    def test_service_http_failure_blocks_verification(self):
        with tempfile.TemporaryDirectory() as temp, cd(temp):
            Path('reports').mkdir()
            with patch('kube_checks.get', side_effect=[self.app, self.deployment]), \
                 patch('kube_checks.kube', return_value=__import__('json').dumps(self.pods)), \
                 patch('kube_checks.forward', return_value=contextlib.nullcontext('http://service/')), \
                 patch('kube_checks.check', side_effect=RuntimeError('HTTP failed')), \
                 patch('kube_checks.diagnostics') as diag:
                with self.assertRaisesRegex(RuntimeError, 'HTTP failed'):
                    verify('commit', IMAGE, timeout=1)
                diag.assert_called_once()
                self.assertFalse(Path('reports/deployment.json').exists())

    def test_new_revision_during_http_does_not_pass(self):
        with tempfile.TemporaryDirectory() as temp, cd(temp):
            Path('reports').mkdir()
            def resource(kind, name, namespace):
                return copy.deepcopy(self.app if kind == 'application' else self.deployment)
            def supersede(url):
                self.app['status']['sync']['revision'] = 'newer-deployment'
            with patch('kube_checks.get', side_effect=resource), \
                 patch('kube_checks.kube', return_value=__import__('json').dumps(self.pods)), \
                 patch('kube_checks.forward', return_value=contextlib.nullcontext('http://service/')), \
                 patch('kube_checks.check', side_effect=supersede), \
                 patch('kube_checks.diagnostics'):
                with self.assertRaisesRegex(RuntimeError, 'Timed out'):
                    verify('commit', IMAGE, timeout=.01)
                self.assertFalse(Path('reports/deployment.json').exists())

    def test_first_sync_missing_deployment_is_retried(self):
        with tempfile.TemporaryDirectory() as temp, cd(temp):
            Path('reports').mkdir()
            calls = 0
            def resource(kind, name, namespace):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise subprocess.CalledProcessError(1, 'kubectl', output='NotFound')
                return self.app if kind == 'application' else self.deployment
            with patch('kube_checks.get', side_effect=resource), \
                 patch('kube_checks.kube', return_value=__import__('json').dumps(self.pods)), \
                 patch('kube_checks.forward', return_value=contextlib.nullcontext('http://service/')), \
                 patch('kube_checks.check'), patch('kube_checks.time.sleep'):
                verify('commit', IMAGE, timeout=1)
                self.assertTrue(Path('reports/deployment.json').is_file())

    def test_verification_timeout_collects_diagnostics(self):
        with patch('kube_checks.diagnostics') as diag:
            with self.assertRaisesRegex(RuntimeError, 'Timed out'):
                verify('commit', IMAGE, timeout=0)
            diag.assert_called_once_with('dev', app='demo-app')


if __name__ == '__main__':
    unittest.main()
