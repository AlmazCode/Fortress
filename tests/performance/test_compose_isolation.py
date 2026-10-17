"""Static and optional actual CLI config checks; no container runtime claim."""
from pathlib import Path
import json
import os
import re
import subprocess
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[2]


class ComposeStaticTests(unittest.TestCase):
    def setUp(self):
        self.compose=yaml.safe_load((ROOT/'infra/compose.yaml').read_text())

    def test_only_nginx_publishes_ports_and_only_worker_gets_gpu(self):
        services=self.compose['services']
        self.assertEqual(set(services),{'nginx','api','worker','redis','postgres'})
        for name,service in services.items():
            if name!='nginx': self.assertNotIn('ports',service)
            if name!='worker': self.assertNotIn('devices',service.get('deploy',{}).get('resources',{}).get('reservations',{}))
        self.assertEqual(services['worker']['deploy']['resources']['reservations']['devices'][0]['count'],1)

    def test_worker_only_joins_internal_network_and_keeps_local_services(self):
        self.assertEqual(self.compose['services']['worker']['networks'],['backend'])
        self.assertIs(self.compose['networks']['backend']['internal'],True)
        for service in ('postgres','redis'):
            self.assertIn('backend',self.compose['services'][service]['networks'])
        self.assertEqual(self.compose['services']['api']['sysctls']['net.ipv4.ip_forward'],'0')

    def test_volumes_limits_and_thread_constraints_are_explicit(self):
        self.assertEqual(set(self.compose['volumes']),{'media','models','postgres','redis'})
        worker=self.compose['services']['worker']
        self.assertEqual(worker['command'],['python','-m','backend.app.main','worker'])
        self.assertEqual(worker['environment']['OMP_NUM_THREADS'],'2')
        self.assertTrue(worker['read_only'])
        self.assertIn('models:/var/lib/fortress/models:ro',worker['volumes'])
        for service in self.compose['services'].values():
            self.assertIn('mem_limit',service)
            self.assertIn('healthcheck',service)
            self.assertEqual(service['restart'],'unless-stopped')

    def test_images_have_real_sha256_pins_and_no_runtime_download_command(self):
        for name in ('postgres','redis'):
            self.assertRegex(self.compose['services'][name]['image'],r'@sha256:[a-f0-9]{64}$')
        for name in ('api','worker','frontend'):
            text=(ROOT/f'infra/{name}.Dockerfile').read_text()
            for line in text.splitlines():
                if line.startswith('FROM '): self.assertRegex(line,r'@sha256:[a-f0-9]{64}|FROM (base|dependencies|harness) AS')
        worker=self.compose['services']['worker']
        self.assertNotIn('pip', ' '.join(worker['command']))
        self.assertEqual(worker['environment']['PIP_NO_INDEX'],'1')
        # A's CLI Settings requires the shared operator key for worker as well.
        self.assertEqual(worker['environment']['FORTRESS_API_KEY'],self.compose['services']['api']['environment']['FORTRESS_API_KEY'])

    def test_test_overlay_is_explicit_and_removes_gpu_without_changing_production(self):
        class Loader(yaml.SafeLoader): pass
        Loader.add_constructor('!reset',lambda loader,node:loader.construct_sequence(node))
        overlay=yaml.load((ROOT/'infra/compose.test.yaml').read_text(),Loader=Loader)
        self.assertEqual(overlay['services']['worker']['deploy']['resources']['reservations']['devices'],[])
        self.assertEqual(overlay['services']['api']['environment']['FORTRESS_INFRA_SMOKE'],'1')
        self.assertEqual(overlay['services']['nginx']['build']['target'],'harness')
        self.assertEqual(self.compose['services']['api']['build']['target'],'production')

    def test_nginx_does_not_publish_media_files_or_log_keys(self):
        text=(ROOT/'infra/nginx.conf').read_text()
        self.assertIn('listen 443 ssl',text)
        self.assertIn('proxy_set_header X-API-Key $http_x_api_key',text)
        self.assertIn('access_log off',text)
        self.assertNotIn('alias ',text)
        self.assertIn('client_max_body_size 201m',text)
        self.assertIn('proxy_read_timeout 300s',text)

    def test_worker_pool_matches_backend_hard_deadline_and_remote_control_policy(self):
        from backend.app.celery_app import create_celery
        app=create_celery('redis://redis:6379/0')
        worker=self.compose['services']['worker']
        self.assertFalse(app.conf.worker_enable_remote_control)
        self.assertEqual(app.conf.worker_pool,'prefork')
        self.assertNotIn('inspect',' '.join(worker['healthcheck']['test']))
        self.assertEqual((app.conf.worker_concurrency,app.conf.worker_prefetch_multiplier),(1,1))
        self.assertEqual((app.conf.task_soft_time_limit,app.conf.task_time_limit),(239,240))
        self.assertEqual(worker['command'],['python','-m','backend.app.main','worker'])
        self.assertIn('/proc/1/cmdline',' '.join(worker['healthcheck']['test']))


class ComposeCliTests(unittest.TestCase):
    """Actual config resolution, with dummy values and no daemon/start/network."""
    @classmethod
    def setUpClass(cls):
        cls.executable=os.environ.get('FORTRESS_COMPOSE_CLI')
        if not cls.executable:
            raise unittest.SkipTest('Set FORTRESS_COMPOSE_CLI for actual Compose config checks')

    def resolve(self, *, overlay=False, missing=None):
        env={key:value for key,value in os.environ.items() if not key.startswith('FORTRESS_')}
        env.update(FORTRESS_API_KEY='synthetic-config-only',POSTGRES_PASSWORD='synthetic-config-only',
                   DATABASE_URL='postgresql+psycopg://fortress:synthetic-config-only@postgres/fortress',
                   FORTRESS_TLS_DIR=str(ROOT/'infra'),FORTRESS_BIND_IP='127.0.0.1',FORTRESS_HTTPS_PORT='8443')
        if missing: env.pop(missing)
        command=[self.executable,'--env-file',os.devnull,'-f',str(ROOT/'infra/compose.yaml')]
        if overlay: command+=['-f',str(ROOT/'infra/compose.test.yaml')]
        return subprocess.run(command+['config','--format','json'],cwd=ROOT,env=env,
                              capture_output=True,text=True,timeout=20)

    def test_resolved_production_keeps_worker_isolated_and_matches_accepted_cli(self):
        process=self.resolve()
        self.assertEqual(process.returncode,0,process.stderr)
        value=json.loads(process.stdout)
        services=value['services']
        self.assertEqual(set(services['worker']['networks']),{'backend'})
        self.assertTrue(value['networks']['backend']['internal'])
        self.assertEqual(services['api']['command'],['python','-m','backend.app.main','api','--host','0.0.0.0','--port','8000'])
        self.assertEqual(services['worker']['command'],['python','-m','backend.app.main','worker'])
        self.assertEqual(services['worker']['environment']['FORTRESS_API_KEY'],services['api']['environment']['FORTRESS_API_KEY'])
        self.assertEqual(services['worker']['deploy']['resources']['reservations']['devices'][0]['count'],1)
        self.assertEqual(services['nginx']['ports'][0]['host_ip'],'127.0.0.1')
        self.assertTrue(all(not service.get('ports') for name,service in services.items() if name!='nginx'))

    def test_resolved_overlay_replaces_both_commands_and_removes_gpu(self):
        process=self.resolve(overlay=True)
        self.assertEqual(process.returncode,0,process.stderr)
        value=json.loads(process.stdout)
        for name in ('api','worker','nginx'):
            self.assertEqual(value['services'][name]['build']['target'],'harness')
        for name in ('api','worker'):
            self.assertEqual(value['services'][name]['command'][:2],['python','/opt/fortress-smoke.py'])
        self.assertFalse(value['services']['worker']['deploy']['resources'].get('reservations',{}).get('devices'))

    def test_missing_required_application_settings_fail_before_a_container_can_start(self):
        for name in ('FORTRESS_API_KEY','DATABASE_URL'):
            with self.subTest(name=name):
                process=self.resolve(missing=name)
                self.assertNotEqual(process.returncode,0)
                self.assertIn(name,process.stderr)


if __name__=='__main__': unittest.main()
