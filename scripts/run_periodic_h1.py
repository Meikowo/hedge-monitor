#!/usr/bin/env python3
"""2026H1 固定首轮公司池：每日发现与六小时队列分开执行。"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ['--sample', 'config/annual_formal_2025.csv',
         '--fiscal-year', '2026', '--report-type', 'semiannual']


def run_pipeline(stage: str, locate_limit: int = 48, extract_limit: int = 36,
                 confirm_llm: bool = False) -> None:
    if stage not in {'metadata', 'queue'}:
        raise ValueError('stage must be metadata or queue')
    if not 1 <= locate_limit <= 48 or not 1 <= extract_limit <= 36:
        raise ValueError('locate_limit must be 1..48; extract_limit must be 1..36')
    if stage == 'queue' and not confirm_llm:
        raise ValueError('queue requires --confirm-llm')

    def run(script: str, *extra: str) -> None:
        subprocess.run([sys.executable, f'scripts/{script}.py', *SCOPE, *extra],
                       cwd=ROOT, check=True)

    run('periodic_progress')
    try:
        if stage == 'metadata':
            run('fetch_periodic_reports', '--strategy', 'full', '--write')
        else:
            run('locate_periodic_pages', '--limit', str(locate_limit), '--write')
            run('extract_periodic_reports', '--limit', str(extract_limit), '--confirm-llm')
    finally:
        # Even a circuit-breaker failure leaves a before/after queue snapshot.
        run('periodic_progress')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['metadata', 'queue'], required=True)
    parser.add_argument('--locate-limit', type=int, default=48)
    parser.add_argument('--extract-limit', type=int, default=36)
    parser.add_argument('--confirm-llm', action='store_true')
    args = parser.parse_args()
    run_pipeline(args.stage, args.locate_limit, args.extract_limit, args.confirm_llm)


if __name__ == '__main__':
    main()
