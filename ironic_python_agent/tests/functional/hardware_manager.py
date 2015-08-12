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

from oslotest import base as test_base

class TestHWMFunctionality(test_base.BaseTestCase):

    def setUp(self):
        super(TestHardwareManagerFunctionality, self).setUp()
        # TODO Actually spin up the agent here, with one hardware manager, as a
        # subprocess. Wait until it starts.

    def tearDown(self):
        # TODO Kill agent process

# Overwrite base class to run same test suite with multiple managers, plus some
# additional ones
class TestHWMFunctionalityMultipleManagers(TestHardwareManagerFunctionality):

    def setUp(self):
        # TODO Actually spin up the agent here, with multiple hardware managers, as
        # a subprocess. Wait until it starts.

    def tearDown(self):
        # TODO Kill agent process

