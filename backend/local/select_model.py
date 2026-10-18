"""Validate a private prototype package and atomically select it while stopped."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import socket
import tempfile

from .app import PrototypeRelease


def private_path(path):
    path=Path(path).resolve(strict=True)
    if any((p/'.git').exists() for p in [path,*path.parents]):
        raise ValueError('Model/configuration must be outside Git')
    return path


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=.5):return True
    except OSError:return False


def select(config_path,bundle):
    config_path,bundle=private_path(config_path),private_path(bundle)
    original=config_path.read_bytes();config=json.loads(original.decode('utf-8-sig'))
    if port_open(config['port']):raise ValueError('Stop the local service before selecting a model')
    release=PrototypeRelease({'bundle_root':str(bundle),'device':'cpu'})
    readiness=release.readiness()
    if readiness['status']!='prototype' or not readiness['trained'] or readiness['validated']:
        raise ValueError('A verified prototype package is required')
    backup=config_path.with_name(config_path.stem+'.before-model-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    with backup.open('xb') as out:out.write(original)
    config['bundle_root']=str(bundle)
    fd,name=tempfile.mkstemp(prefix='.model-',suffix='.json',dir=config_path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump(config,out,ensure_ascii=False,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
        os.replace(name,config_path)
    finally:
        Path(name).unlink(missing_ok=True)
    return readiness,backup


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True)
    a=p.parse_args();readiness,backup=select(a.config,a.bundle)
    print(json.dumps({'release_version':readiness['release_version'],'limitations':readiness['limitations'],
                      'configuration_backup':str(backup)},ensure_ascii=False))
