"""Exact CSV-pair cache; no credentials, no public file routes, atomic commit marker."""
import hashlib
import json
import os
from pathlib import Path
import uuid

ROOT=Path(os.getenv('SESSION_CSV_CACHE',str(Path(__file__).parent/'session-cache')))


def save_pair(origin, session_id, run_id, summary_bytes, series_bytes, metadata):
    tag=hashlib.sha256((origin+'\0'+session_id).encode()).hexdigest()
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(ROOT,0o700)
    directory=ROOT/tag/run_id
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(directory,0o700)
    values={'summary.csv':summary_bytes,'series.csv':series_bytes,
            'metadata.json':json.dumps(metadata,sort_keys=True,allow_nan=False).encode()}
    marker=directory/'metadata.json'
    if marker.exists():
        if any((directory/name).read_bytes()!=value for name,value in values.items()):
            raise ValueError('Committed run bytes or metadata changed; immutable run identity was not replaced')
        return
    for name,value in values.items():
        temporary=directory/(name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with os.fdopen(os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:
                stream.write(value)
            os.replace(temporary,directory/name)
        finally:
            temporary.unlink(missing_ok=True)


def session_directory(origin, session_id):
    return ROOT/hashlib.sha256((origin+'\0'+session_id).encode()).hexdigest()


def committed_entries(origin, session_id):
    directory=session_directory(origin,session_id)
    entries=[]
    if directory.exists():
        for marker in directory.glob('*/metadata.json'):
            entry=json.loads(marker.read_text())
            if marker.parent.name!=entry['run_id'] or not all((marker.parent/n).is_file() for n in ('series.csv','summary.csv')):
                raise ValueError('A committed CSV pair is incomplete')
            entries.append(entry)
    entries.sort(key=lambda e:e['sequence'])
    if len({e['sequence'] for e in entries})!=len(entries): raise ValueError('Duplicate committed sequence')
    return entries


def read_pair(origin,session_id,run_id):
    directory=session_directory(origin,session_id)/run_id
    if not (directory/'metadata.json').is_file(): raise ValueError('Uncommitted CSV pair')
    return (directory/'summary.csv').read_bytes(),(directory/'series.csv').read_bytes()
