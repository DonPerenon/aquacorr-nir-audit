"""Prespecified two-group comparison. Never executes model-generated code."""
import csv
import math
import random
import statistics
from pathlib import Path
from .core import require, sha

def analyze(path, plan):
    require(plan['method'] == 'independent_mean_difference', 'Unsupported method; specialist implementation required')
    require(plan.get('independent_units') is True, 'Independent experimental units must be declared')
    require(plan.get('exchangeable_under_null') is True, 'Permutation exchangeability must be justified')
    require(bool(plan.get('assumption_rationale')), 'Assumption rationale is required')
    require(plan.get('missing') in ('reject', 'complete_case'), 'Missing-data plan required')
    require(199 <= plan['resamples'] <= 10000, 'Resample count must be 199..10000')
    require(plan['group_a'] != plan['group_b'], 'Groups must differ')
    groups = {plan['group_a']: [], plan['group_b']: []}
    seen, excluded = set(), []
    with Path(path).open(newline='') as f:
        reader = csv.DictReader(f)
        require(set([plan['id_column'], plan['group_column'], plan['value_column']]) <= set(reader.fieldnames or []), 'Missing CSV columns')
        for n, row in enumerate(reader, 2):
            require(n <= 10002, 'MVP limit: 10000 rows')
            uid = row[plan['id_column']]
            require(uid and uid not in seen, 'Missing/duplicate unit IDs: possible pseudoreplication')
            seen.add(uid)
            group, value = row[plan['group_column']], row[plan['value_column']]
            require(group in groups, 'Unexpected group; silently dropping groups is prohibited')
            if value == '' and plan['missing'] == 'complete_case':
                excluded.append({'row': n, 'reason': 'prespecified complete-case exclusion'})
                continue
            try:
                value = float(value)
            except ValueError:
                raise ValueError(f'Invalid numeric value at row {n}')
            require(math.isfinite(value), 'Non-finite numeric data')
            groups[group].append(value)
    a, b = groups[plan['group_a']], groups[plan['group_b']]
    require(min(len(a), len(b)) >= 2, 'Each group needs at least two units; adequacy still needs scientific assessment')
    rng = random.Random(plan['seed'])
    effect = statistics.mean(b) - statistics.mean(a)
    boots, extreme = [], 0
    pooled = a + b
    for _ in range(plan['resamples']):
        boots.append(statistics.mean(rng.choices(b, k=len(b))) - statistics.mean(rng.choices(a, k=len(a))))
        shuffled = rng.sample(pooled, len(pooled))
        delta = statistics.mean(shuffled[len(a):]) - statistics.mean(shuffled[:len(a)])
        extreme += abs(delta) >= abs(effect) - 1e-12
    boots.sort()
    n = len(boots)
    numbers = {'n_a': len(a), 'n_b': len(b), 'mean_a': statistics.mean(a), 'mean_b': statistics.mean(b),
               'sd_a': statistics.stdev(a), 'sd_b': statistics.stdev(b), 'difference_b_minus_a': effect,
               'ci95_low': boots[int(.025 * (n - 1))], 'ci95_high': boots[int(.975 * (n - 1))],
               'p_two_sided': (extreme + 1) / (plan['resamples'] + 1), 'excluded': len(excluded)}
    return {'id': 'R001', 'kind': 'computed_observational_result', 'numbers': numbers, 'unit': plan['unit'],
            'method': plan['method'], 'data_sha256': sha(path), 'code_sha256': sha(__file__), 'parameters': plan,
            'exclusions': excluded, 'limitations': ['Single prespecified outcome; no family of tests.',
            'Percentile bootstrap CI can have poor coverage for small/skewed samples.',
            'Permutation inference assumes exchangeability; this is declared, not proven by software.',
            'Association is not causation. Existing-data analysis is exploratory unless independently preregistered.']}
