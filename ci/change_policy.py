"""Classify the complete change range; never trust a commit message to skip CI."""
import re
import subprocess
import sys

MANIFEST = 'kubernetes/dev/demo-app/deployment.yaml'
BUILD_PATHS = ('app/', 'ci/', 'tests/')


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def classify(base, head='HEAD'):
    # Even without Jenkins history, a pure image update must not create a loop.
    # This exception is based on the complete diff, not a trusted-looking message.
    if not base or subprocess.run(['git', 'merge-base', '--is-ancestor', base, head],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        try:
            parent = git('rev-parse', head + '^')
            paths = git('diff', '--name-only', parent, head).splitlines()
            if paths == [MANIFEST] and classify(parent, head) == 'skip':
                return 'skip'
        except subprocess.CalledProcessError:
            pass
        return 'build'
    paths = git('diff', '--name-only', base, head).splitlines()
    if any(p.startswith(BUILD_PATHS) or p == 'Jenkinsfile' for p in paths):
        return 'build'
    manifests = [p for p in paths if p.startswith(('kubernetes/', 'argocd/', 'helm/'))]
    if not manifests:
        return 'skip'
    if manifests != [MANIFEST]:
        return 'validate'
    diff = git('diff', '--unified=0', base, head, '--', MANIFEST)
    changes = [line for line in diff.splitlines()
               if line[:1] in ('+', '-') and not line.startswith(('+++', '---'))]
    # Only the precise image substitution made by promote.py is ignored.
    if (len(changes) == 2 and changes[0].startswith('-') and changes[1].startswith('+')
            and all(re.fullmatch(r'[+-]          image: \S+', line) for line in changes)):
        return 'skip'
    return 'validate'


if __name__ == '__main__':
    print(classify(sys.argv[1] if len(sys.argv) > 1 else ''))
