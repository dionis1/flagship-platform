"""Exercise the actual strict validator, including a deliberately broken manifest."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('kubeconform'), 'kubeconform is installed by CI tool bootstrap')
class SchemaTests(unittest.TestCase):
    def test_invalid_port_type_is_rejected(self):
        source = (ROOT / 'kubernetes/dev/demo-app/deployment.yaml').read_text()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'deployment.yaml'
            path.write_text(source.replace('containerPort: 80', 'containerPort: invalid'))
            result = subprocess.run(['kubeconform', '-strict', '-kubernetes-version', '1.31.0', str(path)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('containerPort', result.stdout)

    def test_unknown_deployment_field_is_rejected(self):
        source = (ROOT / 'kubernetes/dev/demo-app/deployment.yaml').read_text()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'deployment.yaml'
            path.write_text(source.replace('  replicas: 1', '  replicas: 1\n  typoField: true'))
            result = subprocess.run(['kubeconform', '-strict', '-kubernetes-version', '1.31.0', str(path)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('typoField', result.stdout)
