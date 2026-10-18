"""Optimistic GitOps update: preserve remote edits and reject stale builds."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

from change_policy import MANIFEST, classify


def git(*args, cwd=None):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()


def image_in(text):
    images = re.findall(r'^          image: (\S+)$', text, flags=re.M)
    if len(images) != 1:
        raise RuntimeError('Expected exactly one application image field')
    return images[0]


def promote(source, image, remote, report='reports/deployment-revision.txt'):
    if not re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}', image):
        raise ValueError('Promotion requires an immutable image digest')
    source = git('rev-parse', source)
    original_image = image_in(git('show', f'{source}:{MANIFEST}'))
    output = Path(report).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # A separate checkout never overwrites the tested workspace or its scripts.
    with tempfile.TemporaryDirectory(prefix='gitops-') as directory:
        git('init', '-q', directory)
        git('remote', 'add', 'origin', remote, cwd=directory)
        git('config', 'user.name', 'Jenkins CI', cwd=directory)
        git('config', 'user.email', 'jenkins@localhost', cwd=directory)
        for attempt in range(3):
            git('fetch', '--quiet', 'origin', 'main', cwd=directory)
            tip = git('rev-parse', 'FETCH_HEAD', cwd=directory)
            git('checkout', '--quiet', '--detach', tip, cwd=directory)
            if subprocess.run(['git', '-C', directory, 'merge-base', '--is-ancestor', source, tip],
                              capture_output=True).returncode:
                raise RuntimeError('Source is no longer an ancestor of main; rebuild required')
            # Classifier operates on this checkout's Git object database.
            previous = os.getcwd()
            try:
                os.chdir(directory)
                action = classify(source, tip)
            finally:
                os.chdir(previous)
            if action != 'skip':
                raise RuntimeError('Application, CI or manifests changed since the build; refusing stale promotion')
            manifest = Path(directory) / MANIFEST
            text = manifest.read_text()
            if image_in(text) != original_image:
                raise RuntimeError('Another deployment changed the image; refusing to overwrite it')
            if original_image == image:
                # A CI-only change can rebuild byte-identical application content.
                # Verify the current Git revision rather than create an empty commit.
                output.write_text(tip + '\n')
                return tip
            manifest.write_text(re.sub(r'^          image: \S+$',
                                       '          image: ' + image, text, flags=re.M))
            git('add', MANIFEST, cwd=directory)
            git('commit', '-q', '-m', f'Deploy {image} via Jenkins\n\nCI-Deployment: true\nSource-Revision: {source}',
                cwd=directory)
            result = subprocess.run(['git', '-C', directory, 'push', 'origin', 'HEAD:main'],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                revision = git('rev-parse', 'HEAD', cwd=directory)
                output.write_text(revision + '\n')
                return revision
            if not any(word in result.stderr for word in ('fetch first', 'non-fast-forward', 'remote contains work')):
                raise RuntimeError('Git push failed; check credentials and branch protection')
        raise RuntimeError('Concurrent main updates prevented promotion after three attempts')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--remote', default='https://github.com/dionis1/flagship-platform.git')
    args = parser.parse_args()
    print(promote(args.source, args.image, args.remote))
