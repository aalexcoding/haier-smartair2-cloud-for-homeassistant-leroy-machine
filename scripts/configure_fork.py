#!/usr/bin/env python3
"""Replace repository link placeholders with the fork owner's GitHub username."""
import argparse
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parents[1]
PLACEHOLDER = 'YOUR_GITHUB_USERNAME'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--github-user', required=True)
    args = parser.parse_args()
    user = args.github_user.strip()
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?', user):
        parser.error('Invalid GitHub username')
    manifest = BASE/'custom_components/haier_smartair2/manifest.json'
    m = json.loads(manifest.read_text(encoding='utf-8'))
    repo = f'https://github.com/{user}/haier-smartair2-cloud-for-homeassistant'
    m.update(documentation=repo, issue_tracker=f'{repo}/issues', codeowners=[f'@{user}'])
    manifest.write_text(json.dumps(m, indent=2)+'\n',encoding='utf-8')
    readme = BASE/'README.md'
    readme.write_text(readme.read_text(encoding='utf-8').replace(PLACEHOLDER,user), encoding='utf-8')
    print('Fork URLs configured. Retain upstream LICENSE and Git ancestry.')


if __name__ == '__main__':
    main()
