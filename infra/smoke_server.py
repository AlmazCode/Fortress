"""Explicit synthetic infrastructure harness/client, never a model or real API."""
from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener
import uuid

PAYLOAD = b'FORTRESS_SYNTHETIC_ONLY\nnot-a-real-video\n'
LIMIT = 4096


class HarnessServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, key):
        if not key or len(key.encode('utf-8')) > 1024:
            raise ValueError('A bounded nonempty test API key is required')
        self.api_key = key
        self.jobs = {}
        self.jobs_lock = threading.Lock()
        super().__init__(address, HarnessHandler)

    def handle_error(self, request, client_address):
        # Default HTTPServer traceback includes local paths and client addresses.
        print('Synthetic harness request failed',file=sys.stderr)


class HarnessHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # No headers, URLs, keys, request bodies or local paths in logs.

    def setup(self):
        super().setup()
        self.connection.settimeout(6)

    def reply(self, status, payload):
        data=json.dumps({'synthetic':True,'harness':'infrastructure_only',**payload}).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('Connection','close')
        self.end_headers()
        self.wfile.write(data)
        self.close_connection=True

    def authorized(self):
        supplied=self.headers.get('X-API-Key','')
        if not hmac.compare_digest(supplied.encode('utf-8'),self.server.api_key.encode('utf-8')):
            self.reply(401,{'code':'invalid_key'}); return False
        return True

    def do_GET(self):
        if self.path=='/healthz':
            self.reply(200,{'status':'ok','model_ready':False}); return
        if not self.authorized(): return
        prefix='/api/v1/jobs/'
        if self.path.startswith(prefix):
            key=self.path[len(prefix):]
            if key in self.server.jobs:
                self.reply(200,self.server.jobs[key]); return
        self.reply(404,{'code':'not_found'})

    def do_POST(self):
        if not self.authorized(): return
        if self.path!='/api/v1/analyze':
            self.reply(404,{'code':'not_found'}); return
        if self.headers.get('X-Fortress-Synthetic')!='1' or self.headers.get('Content-Type')!='application/octet-stream':
            self.reply(400,{'code':'synthetic_only'}); return
        if self.headers.get('Transfer-Encoding'):
            self.reply(400,{'code':'content_length_required'}); return
        try: length=int(self.headers.get('Content-Length','-1'))
        except ValueError: length=-1
        if not 0 < length <= LIMIT:
            self.reply(413,{'code':'synthetic_limit'}); return
        try: body=self.rfile.read(length)
        except (TimeoutError,OSError):
            self.reply(400,{'code':'incomplete_upload'}); return
        if len(body)!=length or not body.startswith(b'FORTRESS_SYNTHETIC_ONLY\n'):
            self.reply(400,{'code':'synthetic_only'}); return
        with self.server.jobs_lock:
            if len(self.server.jobs)>=128:
                self.reply(429,{'code':'synthetic_capacity'}); return
            job=str(uuid.uuid4())
            self.server.jobs[job]={'job_id':job,'status':'smoke_complete','bytes_received':length,'result_kind':'no_model_inference'}
        self.reply(202,{'job_id':job})


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise HTTPError(request.full_url,code,'Redirect refused',headers,fp)


def checked_url(url, allow_local_http=False):
    parsed=urlsplit(url)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise ValueError('Use an origin URL without credentials, path, query or fragment')
    if parsed.scheme=='http' and allow_local_http:
        try: local=ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError: local=parsed.hostname=='localhost'
        if not local: raise ValueError('Plain HTTP is allowed only for a loopback harness')
    elif parsed.scheme!='https':
        raise ValueError('HTTPS with normal certificate verification is required')
    return parsed


def client_smoke(url, key, *, allow_local_http=False, ca_file=None, timeout=10):
    parsed=checked_url(url,allow_local_http)
    context=ssl.create_default_context(cafile=ca_file)
    opener=build_opener(NoRedirect(),HTTPSHandler(context=context))
    origin=url.rstrip('/')

    def request(path, *, auth=True, data=None):
        headers={'X-API-Key':key} if auth else {}
        if data is not None: headers.update({'Content-Type':'application/octet-stream','X-Fortress-Synthetic':'1'})
        with opener.open(Request(origin+path,data=data,headers=headers),timeout=timeout) as response:
            body=response.read(32769)
            if len(body)>32768: raise ValueError('Oversized smoke response')
            value=json.loads(body)
            if not isinstance(value,dict): raise ValueError('Invalid smoke response')
            return response.status,value

    started=time.monotonic()
    try:
        request('/api/v1/jobs/unauthorized-check',auth=False)
        raise ValueError('Unauthenticated access was not rejected')
    except HTTPError as error:
        if error.code!=401: raise
    status, accepted=request('/api/v1/analyze',data=PAYLOAD)
    if status!=202 or accepted.get('synthetic') is not True or accepted.get('harness')!='infrastructure_only':
        raise ValueError('Endpoint is not the explicit infrastructure harness')
    job=accepted.get('job_id')
    if not isinstance(job,str): raise ValueError('Missing smoke job ID')
    uuid.UUID(job)
    status,result=request('/api/v1/jobs/'+job)
    if status!=200 or result.get('synthetic') is not True or result.get('status')!='smoke_complete' or result.get('bytes_received')!=len(PAYLOAD):
        raise ValueError('Synthetic status mismatch')
    return {'synthetic':True,'harness':'infrastructure_only','current_host_smoke_passed':True,
            'tls_verified':parsed.scheme=='https','local_only':parsed.scheme=='http',
            'external_access_verified':False,'independent_external_observer_required':True,
            'unauthenticated_status':401,'upload_status':202,'poll_status':200,
            'elapsed_sec':round(time.monotonic()-started,6),
            'limitations':['No model, real media, full application, database durability or independent incoming route tested']}


def probe_worker():
    local={}
    for name,port in [('postgres',5432),('redis',6379)]:
        try:
            with socket.create_connection((name,port),timeout=2): local[name]=True
        except OSError: local[name]=False
    egress_blocked=True
    for host in ('1.1.1.1','8.8.8.8'):
        try:
            with socket.create_connection((host,443),timeout=2): egress_blocked=False
        except OSError: pass
    report={'synthetic':True,'local_service_tcp':local,'egress_probes_blocked':egress_blocked,
            'limitations':['TCP probes alone do not prove every protocol blocked or database persistence']}
    print(json.dumps(report))
    return 0 if all(local.values()) and egress_blocked else 2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['serve','client','worker','probe-worker'])
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--url')
    parser.add_argument('--key-file',type=Path)
    parser.add_argument('--allow-local-http',action='store_true')
    parser.add_argument('--ca-file')
    args=parser.parse_args()
    if args.mode in ('serve','worker','probe-worker') and os.environ.get('FORTRESS_INFRA_SMOKE')!='1':
        parser.error('Explicit FORTRESS_INFRA_SMOKE=1 is required; this is not the application')
    if args.mode=='serve':
        HarnessServer((args.host,args.port),os.environ.get('FORTRESS_API_KEY','')).serve_forever()
    elif args.mode=='worker':
        # A quiet idle test container; real Celery/model readiness is not claimed.
        while True: time.sleep(30)
    elif args.mode=='probe-worker':
        return probe_worker()
    else:
        if not args.url or not args.key_file: parser.error('--url and --key-file are required')
        raw=args.key_file.read_bytes()
        if not 0 < len(raw) <= 1024: parser.error('Use a bounded nonempty private key file')
        key=raw.decode('utf-8').strip()
        if not key or '\n' in key or '\r' in key: parser.error('Invalid key file')
        report=client_smoke(args.url,key,allow_local_http=args.allow_local_http,ca_file=args.ca_file)
        print(json.dumps(report,indent=2))
    return 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except (OSError,ValueError,HTTPError) as error:
        # Exception messages can contain URLs/paths: return a fixed safe diagnostic.
        print(json.dumps({'status':'failed','synthetic':True,'external_access_verified':False,'reason':type(error).__name__}),file=sys.stderr)
        raise SystemExit(2)
