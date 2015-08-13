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

import logging
import multiprocessing
import time

from oslotest import base as test_base
import requests

from ironic_python_agent import agent


class TestHWMFunctionality(test_base.BaseTestCase):
    def setUp(self):
        super(TestHWMFunctionality, self).setUp()
        mpl = multiprocessing.log_to_stderr()
        mpl.setLevel(logging.INFO)
        agentpy = agent.IronicPythonAgent(
            'http://127.0.0.1:6835', 'localhost', ('0.0.0.0', 9999), 3, 10,
            None, 300, 1, 'agent_ipmitool', True)
        self.process = multiprocessing.Process(
            target=agentpy.run)
        self.process.start()

        # Wait for process to start, otherwise we have a race for tests
        tries = 0
        while tries < 20:
            try:
                return requests.get('http://localhost:9999/v1/commands')
            except requests.ConnectionError:
                time.sleep(.1)
                tries += 1

        raise IOError('Agent did not start after 2 seconds.')
        # print(self.process.join())

    def test_empty_commands(self):
        commands = requests.get('http://localhost:9999/v1/commands')
        self.assertEqual(200, commands.status_code)
        self.assertEqual({'commands': []}, commands.json())

    def tearDown(self):
        super(TestHWMFunctionality, self).tearDown()
        self.process.terminate()
