# Copyright 2015 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from multiprocessing import Process

from oslotest import base as test_base
import requests

from ironic_python_agent import agent


class TestHWMFunctionality(test_base.BaseTestCase):

    def setUp(self):
        super(TestHWMFunctionality, self).setUp()
        self.process = Process(target=agent.IronicPythonAgent, kwargs={
            'api_url': 'localhost',
            'advertise_address': 'localhost',
            'listen_address': ('localhost', 9999),
            'ip_lookup_attempts': 1,
            'ip_lookup_sleep': 1,
            'network_interface': 'eth0',
            'lookup_timeout': '60',
            'lookup_interval': '15',
            'driver_name': 'agent',
            'standalone': True
        })
        self.process.start()

    def test_empty_commands(self):
        commands = requests.get('http://localhost:9999/v1/commands')
        self.assertEqual(200, commands.status_code)
        self.assertEqual({'commands': []}, commands.json())

    def tearDown(self):
        super(TestHWMFunctionality, self).tearDown()
        self.process.terminate()
