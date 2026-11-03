#!/usr/bin/env python3
"""Checks for the repository: links, hygiene, script syntax and help, JSON, the delivery contract, and both
example episodes (social and cinematic) run through the plan, prompt, pace and estimate checks. Nothing here
calls fal.

Usage:
  python3 tests/check_repo.py
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'skills', 'minisode', 'scripts')
errors = []


def files(exts):
    for d, dirs, fs in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in ('.git', 'node_modules', '__pycache__')]
        for f in fs:
            if f.endswith(exts):
                yield os.path.join(d, f)


def rel(p):
    return os.path.relpath(p, ROOT)


def run(args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=300)


# links in markdown
for p in files(('.md',)):
    for link in re.findall(r'\]\(([^)#\s]+)\)', open(p, encoding='utf-8').read()):
        if not link.startswith(('http://', 'https://', 'mailto:')) and \
                not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(p), link))):
            errors.append(f'{rel(p)}: broken link {link}')

# every reference routed by SKILL.md exists, and every reference file is routed
skill = open(os.path.join(ROOT, 'skills', 'minisode', 'SKILL.md'), encoding='utf-8').read()
routed = set(re.findall(r'`(references/[\w-]+\.md)`', skill))
for r in routed:
    if not os.path.exists(os.path.join(ROOT, 'skills', 'minisode', r)):
        errors.append(f'SKILL.md routes to missing {r}')
for f in os.listdir(os.path.join(ROOT, 'skills', 'minisode', 'references')):
    if f'references/{f}' not in routed:
        errors.append(f'references/{f} is not routed from SKILL.md')

# syntax, docstrings, --help
for p in files(('.py',)):
    src = open(p, encoding='utf-8').read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        errors.append(f'{rel(p)}: {e}')
        continue
    if not ast.get_docstring(tree) or 'Usage' not in ast.get_docstring(tree):
        errors.append(f'{rel(p)}: needs a docstring with usage lines')
for p in files(('.mjs',)):
    if run(['node', '--check', p]).returncode:
        errors.append(f'{rel(p)}: node --check failed')
for f in sorted(os.listdir(SCRIPTS)):
    if f.endswith('.py') and run([sys.executable, os.path.join(SCRIPTS, f), '--help']).returncode:
        errors.append(f'scripts/{f}: --help failed')
for p in files(('.py',)):
    if p != os.path.abspath(__file__) and 'import fal_client' in open(p, encoding='utf-8').read() \
            and not p.endswith('fal_run.py'):
        errors.append(f'{rel(p)}: imports fal_client directly; go through fal_run.py so the ledger sees the call')

# hygiene and size
secret = re.compile(r'(/Users/[a-z]|/home/[a-z]|/root/|FAL_KEY\s*=\s*["\'][0-9a-f-]{8}|sk-[A-Za-z0-9]{20}|eyJhbGciOi)')
for p in files(('.md', '.py', '.mjs', '.js', '.json', '.txt')):
    if p == os.path.abspath(__file__):
        continue
    if secret.search(open(p, encoding='utf-8', errors='ignore').read()):
        errors.append(f'{rel(p)}: home path or secret')
total = sum(os.path.getsize(p) for p in files(('',)))
if total > 10_000_000:
    errors.append(f'repository is {total // 1_000_000} MB (keep it under 10)')

# JSON
for p in files(('.json',)):
    try:
        json.load(open(p, encoding='utf-8'))
    except ValueError as e:
        errors.append(f'{rel(p)}: {e}')

# the delivery contract matches the brief given to the app
brief = open(os.path.join(ROOT, 'prompts', 'shotforge-minisodes-tab.md'), encoding='utf-8').read()
deliver = open(os.path.join(SCRIPTS, 'shotforge_deliver.py'), encoding='utf-8').read()
stages = re.search(r"STAGES = \(([^)]*)\)", deliver).group(1)
kinds = re.search(r"KINDS = \(([^)]*)\)", deliver).group(1)
for word in re.findall(r"'(\w+)'", stages):
    if word not in re.search(r'build_stage text,\s+-- ([^\n]*)', brief).group(1):
        errors.append(f'stage {word} is not in the app brief')
for word in re.findall(r"'(\w+)'", kinds):
    if word not in re.search(r'`kind` in ([^;]*);', brief).group(1):
        errors.append(f'preview kind {word} is not in the app brief')
for action in ('note', 'upload-urls', 'preview', 'deliver', 'fail', 'checkpoint', 'episodeId'):
    if action not in deliver or action not in brief:
        errors.append(f'delivery action or field {action} missing on one side of the contract')

# prices
sys.path.insert(0, SCRIPTS)
import fal_run  # noqa: E402
est = fal_run.estimate('minimax/h3-max/reference-to-video', {'duration': 13, 'resolution': '768P'})
if abs(est - 1.08) > 1e-6:
    errors.append(f'H3 768P 13 s should estimate 1.08 USD, got {est}')

# both examples pass their own checks
for name in ('plus-one', 'handover'):
    ex = os.path.join(ROOT, 'examples', name)
    for args in (['plan_check.py', 'episode.json'], ['prompt.py', 'episode.json'],
                 ['make.py', 'episode.json', '--estimate']):
        r = run([sys.executable, os.path.join(SCRIPTS, args[0]), *args[1:]], cwd=ex)
        if r.returncode:
            errors.append(f'{name}: {args[0]} failed:\n{(r.stdout + r.stderr)[-1500:]}')
    r = run([sys.executable, os.path.join(SCRIPTS, 'plan_check.py'), 'episode.json'], cwd=ex)
    if ' 0 warnings' not in r.stdout:
        errors.append(f'{name}: plan_check.py warns:\n{r.stdout[-1500:]}')
    with tempfile.TemporaryDirectory() as tmp:
        for args in (['--plan', 'episode.json'], ['edit.json']):
            if not os.path.exists(os.path.join(ex, args[-1])):
                continue
            r = run([sys.executable, os.path.join(SCRIPTS, 'pace.py'), *args, '-o', tmp], cwd=ex)
            if r.returncode:
                errors.append(f'{name}: pace.py {" ".join(args)} failed:\n{r.stdout[-1500:]}')
    r = run([sys.executable, os.path.join(SCRIPTS, 'shoot.py'), 'episode.json', 's01', '--dry-run'], cwd=ex)
    if r.returncode or 'No music.' not in r.stdout or '@Image 1' not in r.stdout:
        errors.append(f'{name}: shoot.py --dry-run failed or has no @ tags:\n{(r.stdout + r.stderr)[-1500:]}')

# the cinematic example: the tone lock in every prompt, the look frame in every sequence and image recipe
ex = os.path.join(ROOT, 'examples', 'handover')
import prompt as P  # noqa: E402
import make  # noqa: E402
ep, base = P.load(os.path.join(ex, 'episode.json'))
lock = ep['look']['lock']
for s in ep['sequences']:
    b = P.build(ep, s['id'], base)
    if lock not in b['prompt'] or 'CINEMATOGRAPHY' not in b['prompt'] or 'CAMERA A (center)' not in b['prompt'] \
            and s['id'] == 's01':
        errors.append(f'handover {s["id"]}: prompt lacks the tone lock, the cinematography block or camera A')
    tag = b['tags'].get(ep['look']['reference'])
    if not tag or f'Grade every shot against {tag}' not in b['prompt']:
        errors.append(f'handover {s["id"]}: the look frame is not attached and tagged')
for aid, x in ep['assets'].items():
    if x['type'] == 'image' and aid != ep['look']['reference']:
        mk = make.with_look(ep, aid, x)
        if '@' + ep['look']['reference'] not in mk['files']['image_urls'] or not mk['endpoint'].endswith('/edit'):
            errors.append(f'handover {aid}: the look frame is not attached to the image recipe')

print('\n'.join(errors) or f'ok ({total / 1_000_000:.1f} MB)')
sys.exit(1 if errors else 0)
