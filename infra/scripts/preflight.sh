#!/bin/sh
# The Python recorder is shared with the native PowerShell entry point.
set -u
recorder=''
for candidate in "${FORTRESS_PYTHON:-}" python3 python; do
  if [ -n "$candidate" ] && command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import json,sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' >/dev/null 2>&1; then
    recorder=$candidate
    break
  fi
done
if [ -z "$recorder" ]; then
  printf '%s\n' '{"schema_version":1,"report_status":"bootstrap_blocked","readiness":{"service_ready":false,"gpu_ready":false,"external_access_verified":false},"blockers":["No Python recorder found; install Python 3.11 before collecting the full report."],"checks":{}}'
  exit 2
fi
"$recorder" - "$@" <<'FORTRESS_PREFLIGHT_PY'
# BEGIN_FORTRESS_PREFLIGHT_PY
"""Read-only inventory. No package/image downloads, training or deployment."""
import argparse
import datetime
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

EXPECTED_ORIGIN = 'https://github.com/AlmazCode/Fortress'
EXPECTED_BASE = '46b7bc941e64fec5649242b8290607c8f7339819'


def decode_output(value):
    if not isinstance(value, bytes):
        return value or ''
    if b'\x00' in value[:160]:
        return value.decode('utf-16-le', errors='replace').strip('\ufeff')
    return value.decode('utf-8', errors='replace')


def run(command, timeout=8, cwd=None):
    """Record missing, failed and timed-out programs without shell interpolation."""
    try:
        result = subprocess.run(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, shell=False)
        return {'command':command, 'status':'ok' if result.returncode == 0 else 'failed', 'exit_code':result.returncode,
                'stdout':decode_output(result.stdout).strip()[:16000], 'stderr':decode_output(result.stderr).strip()[:4000]}
    except FileNotFoundError:
        return {'command':command, 'status':'missing', 'exit_code':None, 'stdout':'', 'stderr':'Executable not found in PATH'}
    except subprocess.TimeoutExpired as exc:
        return {'command':command, 'status':'timeout', 'exit_code':None, 'stdout':decode_output(exc.stdout)[:4000], 'stderr':'Probe timed out'}
    except OSError as exc:
        return {'command':command, 'status':'failed', 'exit_code':None, 'stdout':'', 'stderr':str(exc)[:1000]}


def parsed_json(probe):
    if probe.get('status') != 'ok':
        return None
    try:
        return json.loads(probe['stdout'])
    except (ValueError, KeyError):
        return None


def verify_repository(cwd, probe):
    root = probe(['git', 'rev-parse', '--show-toplevel'])
    origin = probe(['git', 'remote', 'get-url', 'origin'])
    base = probe(['git', 'cat-file', '-t', EXPECTED_BASE])
    branch = probe(['git', 'branch', '--show-current'])
    head = probe(['git', 'rev-parse', 'HEAD'])
    origin_main = probe(['git', 'rev-parse', 'refs/remotes/origin/main'])
    ancestor = probe(['git', 'merge-base', '--is-ancestor', EXPECTED_BASE, 'HEAD'])
    actual_origin = origin.get('stdout', '').rstrip('/')
    ready = (root['status'] == 'ok' and Path(root['stdout']).resolve() == Path(cwd).resolve()
             and actual_origin.removesuffix('.git') == EXPECTED_ORIGIN and base['stdout'] == 'commit'
             and ancestor['status'] == 'ok' and origin_main['status'] == 'ok')
    # Do not echo credential-bearing origins even if the binding is wrong.
    if '@' in actual_origin or '?' in actual_origin:
        origin['stdout'] = '[redacted unexpected origin]'
    return {'ready':ready, 'root_path':'', 'expected_origin':EXPECTED_ORIGIN, 'expected_base':EXPECTED_BASE,
            'root':root, 'origin':origin, 'base':base, 'branch':branch, 'head':head, 'origin_main':origin_main, 'base_in_head':ancestor}


def network_inventory(url=None, probe_external=False, wan_ip=None, public_ip=None, timeout=8):
    result = {'configured_url':None, 'domain_configured':False, 'tls_probe':{'status':'not_run', 'reason':'No explicit HTTPS probe requested'},
              'transport_configured':bool(url), 'probe_vantage':'current_host', 'independent_external_client_verified':False,
              'external_access_verified':False, 'cgnat':{'state':'unknown', 'reason':'No router WAN and independently observed public address supplied'},
              'blockers':['No independent external synthetic upload/status observation; O3 is still required']}
    if wan_ip:
        try:
            wan = ipaddress.ip_address(wan_ip)
            shared = wan.version == 4 and wan in ipaddress.ip_network('100.64.0.0/10')
            private = not wan.is_global
            different = public_ip is not None and wan != ipaddress.ip_address(public_ip)
            result['cgnat'] = {'state':'suspected' if shared else 'possible_upstream_nat' if private or different else 'not_established',
                               'shared_address_range':shared, 'wan_is_global':wan.is_global, 'wan_public_mismatch':different,
                               'reason':'Address comparison is not proof of an allowed incoming route'}
        except ValueError:
            result['cgnat'] = {'state':'invalid_input', 'reason':'WAN/public address is not a valid IP address'}
    if not url:
        result['blockers'].append('No hostname, trusted certificate or incoming transport has been provided')
        return result
    try:
        parsed = urlsplit(url)
    except ValueError:
        result['tls_probe'] = {'status':'invalid_input', 'reason':'Malformed HTTPS URL'}
        result['blockers'].append('Invalid external URL')
        return result
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        result['tls_probe'] = {'status':'invalid_input', 'reason':'Expected HTTPS URL without credentials, query or fragment'}
        result['blockers'].append('Invalid external URL')
        return result
    try:
        port = parsed.port or 443
    except ValueError:
        result['tls_probe'] = {'status':'invalid_input', 'reason':'Invalid TCP port'}
        return result
    result['configured_url'] = url
    result['domain_configured'] = True
    if not probe_external:
        return result
    try:
        context = ssl.create_default_context()
        with socket.create_connection((parsed.hostname, port), timeout=timeout) as connection:
            with context.wrap_socket(connection, server_hostname=parsed.hostname) as secured:
                certificate = secured.getpeercert()
                result['tls_probe'] = {'status':'ok', 'hostname':parsed.hostname, 'chain_hostname_validated':True,
                                       'not_before':certificate.get('notBefore'), 'not_after':certificate.get('notAfter'),
                                       'tls_version':secured.version(), 'note':'TLS connection from current host only; no upload/status tested'}
    except (OSError, ssl.SSLError) as exc:
        result['tls_probe'] = {'status':'failed', 'reason':str(exc)[:1000]}
        result['blockers'].append('Trusted TLS connection failed')
    return result


def collect(cwd, timeout=8, external_url=None, probe_external=False, wan_ip=None, public_ip=None,
            gpu_image=None, container_smoke=False, runner=run):
    probe = lambda args: runner(args, timeout=timeout, cwd=cwd)
    repo = verify_repository(cwd, probe)
    report = {'schema_version':1, 'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'report_status':'collected', 'repository':repo, 'recorder_python':sys.version.split()[0],
              'platform':{'system':platform.system(), 'release':platform.release(), 'machine':platform.machine()},
              'checks':{}, 'hardware':{}, 'network':network_inventory(),
              'readiness':{'service_ready':False, 'gpu_ready':False, 'external_access_verified':False}, 'blockers':[],
              'scope':'Inventory only. No training, model inference, package download or deployment.'}
    if not repo['ready']:
        report['report_status'] = 'repository_mismatch'
        report['blockers'].append('Repository origin/root/base binding did not pass; runtime probes were not run')
        return report
    report['network'] = network_inventory(external_url, probe_external, wan_ip, public_ip, timeout)
    checks = report['checks']
    if platform.system() == 'Windows':
        checks['os'] = probe(['powershell.exe','-NoProfile','-NonInteractive','-Command', "Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,TotalVisibleMemorySize | ConvertTo-Json -Compress"])
        checks['cpu'] = probe(['powershell.exe','-NoProfile','-NonInteractive','-Command', "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name"])
        checks['wsl_status'] = probe(['wsl.exe','--status'])
        checks['wsl_distributions'] = probe(['wsl.exe','--list','--verbose'])
        os_data = parsed_json(checks['os'])
        if isinstance(os_data, dict) and isinstance(os_data.get('TotalVisibleMemorySize'), (int, float)):
            report['hardware']['ram_bytes'] = int(os_data['TotalVisibleMemorySize']) * 1024
        report['hardware']['cpu'] = checks['cpu']['stdout']
        # A functioning host WSL CLI is not proof that the selected Linux environment is ready.
        linux_runtime = False
    else:
        checks['os'] = probe(['cat','/etc/os-release'])
        checks['cpu'] = probe(['lscpu'])
        checks['memory'] = probe(['cat','/proc/meminfo'])
        match = re.search(r'^MemTotal:\s+(\d+)\s+kB', checks['memory']['stdout'], re.M)
        if match:
            report['hardware']['ram_bytes'] = int(match.group(1)) * 1024
        report['hardware']['cpu'] = checks['cpu']['stdout']
        linux_runtime = platform.system() == 'Linux' and bool(re.search(r'^ID=(?:"?ubuntu"?)$', checks['os']['stdout'], re.M))
    checks['python311'] = probe(['python3.11','-c','import sys,json; print(json.dumps({"version":list(sys.version_info[:3])}))'])
    # Windows may expose Python 3.11 only through its standard launcher.
    if checks['python311']['status'] == 'missing' and platform.system() == 'Windows':
        installed = probe(['py','--list-paths'])
        checks['python_launcher_inventory'] = installed
        candidates = re.findall(r'^.*3\.11[^\r\n]*?([A-Za-z]:\\[^\r\n]*python(?:\.exe)?)\s*$', installed['stdout'], re.M | re.I)
        if candidates:
            checks['python311'] = probe([candidates[0].strip(),'-c','import sys,json; print(json.dumps({"version":list(sys.version_info[:3])}))'])
    python_data = parsed_json(checks['python311'])
    python_ready = isinstance(python_data, dict) and python_data.get('version', [])[:2] == [3, 11]
    checks['ffmpeg'] = probe(['ffmpeg','-version'])
    checks['ffprobe'] = probe(['ffprobe','-version'])
    checks['docker_cli'] = probe(['docker','--version'])
    checks['docker_engine'] = probe(['docker','info','--format','{"server_version":{{json .ServerVersion}},"os_type":{{json .OSType}},"runtimes":{{json .Runtimes}}}'])
    checks['compose'] = probe(['docker','compose','version','--short'])
    checks['gpu_driver'] = probe(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader,nounits'])
    checks['driver_cuda_ceiling'] = probe(['nvidia-smi'])
    # Keep the driver/CUDA header, not unrelated process names or desktop PIDs.
    checks['driver_cuda_ceiling']['stdout'] = checks['driver_cuda_ceiling']['stdout'].split('| Processes:')[0].rstrip()
    checks['cuda_toolkit'] = probe(['nvcc','--version'])
    checks['nvidia_container_toolkit'] = probe(['nvidia-ctk','--version'])
    checks['gpu_container'] = {'status':'not_run', 'exit_code':None, 'command':[], 'stdout':'', 'stderr':'Provide --container-smoke --gpu-image with an already prepared trusted local image'}
    gpu_rows = []
    if checks['gpu_driver']['status'] == 'ok':
        for row in checks['gpu_driver']['stdout'].splitlines():
            columns = [value.strip() for value in row.split(',')]
            if len(columns) == 3:
                try:
                    gpu_rows.append({'name':columns[0], 'driver_version':columns[1], 'memory_mib':int(columns[2])})
                except ValueError:
                    pass
    report['hardware']['gpus'] = gpu_rows
    if container_smoke and gpu_image:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:@-]{0,250}', gpu_image):
            checks['gpu_container']['stderr'] = 'Invalid local image reference'
        elif checks['docker_engine']['status'] == 'ok':
            image = probe(['docker','image','inspect',gpu_image,'--format','{{.Id}}'])
            checks['gpu_local_image'] = image
            if image['status'] == 'ok':
                checks['gpu_container'] = probe(['docker','run','--rm','--pull','never','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--gpus','all','--entrypoint','nvidia-smi',image['stdout']])
    engine = parsed_json(checks['docker_engine'])
    docker_ready = isinstance(engine, dict) and engine.get('os_type') == 'linux' and bool(engine.get('server_version'))
    compose_ready = docker_ready and checks['compose']['status'] == 'ok' and bool(re.match(r'^v?2\.', checks['compose']['stdout']))
    ffmpeg_ready = checks['ffmpeg']['status'] == 'ok' and checks['ffprobe']['status'] == 'ok'
    gpu_ready = bool(gpu_rows) and docker_ready and checks['gpu_container']['status'] == 'ok'
    report['readiness'].update({'os_ready':linux_runtime, 'python311_ready':python_ready, 'docker_ready':docker_ready,
                                'compose_ready':compose_ready, 'ffmpeg_ready':ffmpeg_ready, 'gpu_ready':gpu_ready,
                                'toolchain_ready':linux_runtime and python_ready and compose_ready and ffmpeg_ready})
    # Full service compatibility is not known until agreed locks, application and real runtime checks exist.
    requirements = {'os_ready':'Run the Linux preflight inside the intended Ubuntu/WSL2 environment',
                    'python311_ready':'A working Python 3.11 interpreter was not verified',
                    'docker_ready':'A working Linux Docker daemon was not verified',
                    'compose_ready':'Docker Compose v2 with working Docker daemon was not verified',
                    'ffmpeg_ready':'Working FFmpeg and ffprobe were not verified',
                    'gpu_ready':'NVIDIA container runtime was not verified with an actual local container'}
    report['blockers'].extend(message for flag, message in requirements.items() if not report['readiness'][flag])
    report['blockers'].extend(['Application/dependency-lock compatibility and model readiness are not tested by inventory',
                               'Training PC hardware is not verified by inspecting this host'])
    report['blockers'].extend(report['network']['blockers'])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--strict', action='store_true', help='Exit 2 when service readiness is not proven')
    parser.add_argument('--timeout', type=int, default=8)
    parser.add_argument('--external-url')
    parser.add_argument('--probe-external', action='store_true', help='Explicitly open a TLS connection to the configured host')
    parser.add_argument('--wan-ip')
    parser.add_argument('--public-ip')
    parser.add_argument('--network-only', action='store_true')
    parser.add_argument('--container-smoke', action='store_true')
    parser.add_argument('--gpu-image')
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 60:
        parser.error('--timeout must be between 1 and 60 seconds')
    report = collect(Path.cwd(), args.timeout, args.external_url, args.probe_external, args.wan_ip, args.public_ip, args.gpu_image, args.container_smoke)
    if args.network_only:
        report = {'schema_version':1, 'report_status':report['report_status'], 'repository_ready':report['repository']['ready'],
                  'network':report['network'], 'readiness':{'external_access_verified':False}, 'blockers':report['blockers']}
    text = json.dumps(report, ensure_ascii=True, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf-8')
    sys.stdout.write(text)
    return 3 if report['report_status'] == 'repository_mismatch' else 2 if args.strict and not report['readiness'].get('service_ready', False) else 0


if __name__ == '__main__':
    raise SystemExit(main())
# END_FORTRESS_PREFLIGHT_PY
FORTRESS_PREFLIGHT_PY
