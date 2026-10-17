"""Static configuration checks. A pass is not a Docker/network/volume test."""
from pathlib import Path
import re
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
        self.assertIn('--concurrency=1',worker['command'])
        self.assertIn('--prefetch-multiplier=1',worker['command'])
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
        self.assertNotIn('FORTRESS_API_KEY',worker['environment'])

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


if __name__=='__main__': unittest.main()
