"""Bounded HTTP check shared by image and deployment verification."""
import argparse
import time
import urllib.error
import urllib.request

EXPECTED = '<h1>DevOps Flagship Platform</h1>'


def check(url, timeout=30, expected=EXPECTED):
    deadline = time.monotonic() + timeout
    last_error = 'No response'
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=min(3, max(.1, deadline-time.monotonic()))) as response:
                body = response.read(1024 * 1024).decode('utf-8')
                if response.status == 200 and expected in body:
                    return
                last_error = f'Unexpected status/content: HTTP {response.status}'
        except (OSError, UnicodeError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(min(.5, max(0, deadline-time.monotonic())))
    raise RuntimeError(f'HTTP smoke test failed for {url}: {last_error}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    check(args.url, args.timeout)
    print('HTTP 200 and expected application content verified.')
