import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile

ROOT = Path(__file__).resolve().parent.parent
STAGES = ['IDEATION', 'LITERATURE_SEARCH', 'NOVELTY_AUDIT', 'HYPOTHESIS',
          'METHODOLOGY', 'RESEARCH_EXECUTION', 'STATISTICAL_VALIDATION',
          'MANUSCRIPT_WRITING', 'CITATION_AUDIT', 'INDEPENDENT_REVIEW', 'FINAL_PACKAGE']

class PipelineError(Exception):
    pass

class Gate(PipelineError):
    def __init__(self, reason, details=None):
        super().__init__(reason)
        self.details = details or {}

class Pending(Gate):
    pass

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.atomic-')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def text_write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(value, encoding='utf-8')

def require(test, message):
    if not test:
        raise PipelineError(message)

def inside(base, relative):
    p = (Path(base) / relative).resolve()
    require(p.is_relative_to(Path(base).resolve()), 'Path escapes run directory')
    return p

def event(run, kind, **fields):
    with (Path(run) / 'events.jsonl').open('a') as f:
        f.write(canonical({'at': now(), 'kind': kind, **fields}) + '\n')
        f.flush()
        os.fsync(f.fileno())

@contextlib.contextmanager
def locked(run):
    with (Path(run) / '.lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise PipelineError('This run is already locked by another process')
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

@contextlib.contextmanager
def deadline(seconds):
    def expired(*_):
        raise PipelineError('Stage wall-clock budget exhausted')
    old = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)

def tree_manifest(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(Path(root).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}

def code_fingerprint():
    return digest({d: tree_manifest(ROOT / d) for d in ['arp', 'config', 'templates']})
