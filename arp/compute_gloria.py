"""Prespecified two-group comparison. Never executes model-generated code."""
import csv
import math
import random
import statistics
from pathlib import Path
from .core import require, sha

def analyze(path, plan):
    if plan['method'] == 'cluster_mean_bias':
        return _cluster_mean_bias(path, plan)
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


def _cluster_mean_bias(path, plan):
    """Descriptive paired bias; resample whole independent clusters, not rows."""
    require(plan.get('independent_clusters') is True, 'Independent clusters must be declared')
    require(bool(plan.get('assumption_rationale')), 'Cluster assumption rationale is required')
    require(plan.get('missing') in ('reject', 'complete_case'), 'Missing-data plan required')
    require(199 <= plan['resamples'] <= 10000, 'Resample count must be 199..10000')
    columns = [plan['id_column'], plan['cluster_column'], plan['satellite_column'], plan['field_column']]
    clusters, seen, excluded = {}, set(), []
    with Path(path).open(newline='') as f:
        reader = csv.DictReader(f)
        require(set(columns) <= set(reader.fieldnames or []), 'Missing paired-bias CSV columns')
        for n, row in enumerate(reader, 2):
            require(n <= 10002, 'MVP limit: 10000 rows')
            uid, cluster = row[plan['id_column']], row[plan['cluster_column']]
            require(uid and uid not in seen, 'Missing/duplicate pair IDs')
            require(cluster, 'Missing cluster ID')
            seen.add(uid)
            sat, field = row[plan['satellite_column']], row[plan['field_column']]
            if (sat == '' or field == '') and plan['missing'] == 'complete_case':
                excluded.append({'row': n, 'reason': 'prespecified complete-case exclusion'})
                continue
            try:
                sat, field = float(sat), float(field)
            except ValueError:
                raise ValueError(f'Invalid numeric value at row {n}')
            require(math.isfinite(sat) and math.isfinite(field), 'Non-finite paired data')
            clusters.setdefault(cluster, []).append(sat - field)
    require(len(clusters) >= 5, 'At least five clusters required for this descriptive summary')
    cluster_biases = [statistics.mean(values) for values in clusters.values()]
    estimate = statistics.mean(cluster_biases)
    rng = random.Random(plan['seed'])
    boot = sorted(statistics.mean(rng.choices(cluster_biases, k=len(cluster_biases)))
                  for _ in range(plan['resamples']))
    size = len(boot)
    numbers = {'n_pairs': sum(map(len, clusters.values())), 'n_clusters': len(clusters),
               'mean_cluster_signed_bias': estimate, 'median_cluster_signed_bias': statistics.median(cluster_biases),
               'ci95_low': boot[int(.025 * (size - 1))], 'ci95_high': boot[int(.975 * (size - 1))],
               'excluded': len(excluded)}
    return {'id': 'R001', 'kind': 'computed_observational_result', 'numbers': numbers,
            'unit': plan['unit'], 'method': plan['method'], 'data_sha256': sha(path),
            'code_sha256': sha(__file__), 'parameters': plan, 'exclusions': excluded,
            'limitations': [
                'One locally fixed descriptive outcome; earlier AquaCorr outcomes were already seen.',
                'The interval resamples named waterbodies as if independent and representative; this is not guaranteed.',
                'The interval is conditional on a selected archive subset and does not establish population-wide bias.',
                'Pairing does not remove time, geometry, atmospheric-correction or field-measurement error.'
            ]}
