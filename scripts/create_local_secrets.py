"""Create one environment's Compose secrets once; never print them."""
import argparse
from pathlib import Path
from secrets import token_urlsafe

parser = argparse.ArgumentParser()
parser.add_argument('--environment', choices=('local', 'test'), default='local')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1] / f'deploy/{args.environment}/secrets'
root.mkdir(parents=True, exist_ok=True)
for name in ('root_password', 'app_password'):
    path = root / name
    if not path.exists():
        path.write_text(token_urlsafe(36) + '\n')
        path.chmod(0o600)
print(f'{args.environment} 数据库凭证已准备')
