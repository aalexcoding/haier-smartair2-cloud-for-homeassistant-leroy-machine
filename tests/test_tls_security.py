"""Static guard: cloud traffic must keep TLS certificate verification enabled."""
from pathlib import Path
import re

PACKAGE = Path(__file__).resolve().parents[1] / 'custom_components' / 'haier_smartair2'

INSECURE_PATTERNS = (
    r'ssl\s*=\s*False',
    r'verify\s*=\s*False',
    r'CERT_NONE',
    r'check_hostname\s*=\s*False',
    r'tls_insecure_set\(\s*True',
    r'_create_unverified_context',
    r'disable_warnings',
)


def test_no_disabled_tls_verification():
    offenders = []
    for path in sorted(PACKAGE.glob('*.py')):
        for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if any(re.search(pattern, line) for pattern in INSECURE_PATTERNS):
                offenders.append(f'{path.name}:{lineno}: {line.strip()}')
    assert not offenders, 'TLS verification disabled:\n' + '\n'.join(offenders)


def test_cloud_uses_home_assistant_verified_context():
    source = (PACKAGE / 'cloud.py').read_text(encoding='utf-8')
    assert 'from homeassistant.util.ssl import get_default_context' in source
    assert 'tls_set_context(_tls_ctx())' in source
