# Copyright 2013 Rackspace, Inc.
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

import os
import random
import select
import threading
import time

import pkg_resources
from stevedore import extension
from wsgiref import simple_server

from ironic_python_agent.api import app
from ironic_python_agent.common import metrics
from ironic_python_agent import encoding
from ironic_python_agent import errors
from ironic_python_agent.extensions import base
from ironic_python_agent import hardware
from ironic_python_agent import ironic_api_client
from ironic_python_agent.openstack.common import log


def _time():
    """Wraps time.time() for simpler testing."""
    return time.time()


class IronicPythonAgentStatus(encoding.Serializable):
    """Represents the status of an agent."""

    serializable_fields = ('started_at', 'version')

    def __init__(self, started_at, version):
        self.started_at = started_at
        self.version = version


class IronicPythonAgentHeartbeater(threading.Thread):
    """Thread that periodically heartbeats to Ironic."""

    # If we could wait at most N seconds between heartbeats (or in case of an
    # error) we will instead wait r x N seconds, where r is a random value
    # between these multipliers.
    min_jitter_multiplier = 0.3
    max_jitter_multiplier = 0.6

    # Exponential backoff values used in case of an error. In reality we will
    # only wait a portion of either of these delays based on the jitter
    # multipliers.
    initial_delay = 1.0
    max_delay = 300.0
    backoff_factor = 2.7

    def __init__(self, agent):
        """Initialize the heartbeat thread.

        :param agent: an :class:`ironic_python_agent.agent.IronicPythonAgent`
                      instance.
        """
        super(IronicPythonAgentHeartbeater, self).__init__()
        self.agent = agent
        self.hardware = hardware.get_manager()
        self.api = ironic_api_client.APIClient(agent.api_url,
                                               agent.driver_name)
        self.log = log.getLogger(__name__)
        self.error_delay = self.initial_delay
        self.reader = None
        self.writer = None

    def run(self):
        """Start the heartbeat thread."""
        # The first heartbeat happens immediately
        self.log.info('starting heartbeater')
        interval = 0
        self.agent.set_agent_advertise_addr()

        self.reader, self.writer = os.pipe()
        p = select.poll()
        p.register(self.reader, select.POLLIN)
        try:
            while True:
                if p.poll(interval * 1000):
                    if os.read(self.reader, 1) == 'a':
                        break

                self.do_heartbeat()
                interval_multiplier = random.uniform(
                    self.min_jitter_multiplier,
                    self.max_jitter_multiplier)
                interval = self.agent.heartbeat_timeout * interval_multiplier
                log_msg = 'sleeping before next heartbeat, interval: {0}'
                self.log.info(log_msg.format(interval))
        finally:
            os.close(self.reader)
            os.close(self.writer)
            self.reader = None
            self.writer = None

    def do_heartbeat(self):
        """Send a heartbeat to Ironic."""
        try:
            self.api.heartbeat(
                uuid=self.agent.get_node_uuid(),
                advertise_address=self.agent.advertise_address
            )
            self.error_delay = self.initial_delay
            self.log.info('heartbeat successful')
        except Exception:
            self.log.exception('error sending heartbeat')
            self.error_delay = min(self.error_delay * self.backoff_factor,
                                   self.max_delay)

    def force_heartbeat(self):
        os.write(self.writer, 'b')

    def stop(self):
        """Stop the heartbeat thread."""
        if self.writer is not None:
            self.log.info('stopping heartbeater')
            os.write(self.writer, 'a')
            return self.join()


class IronicPythonAgent(base.ExecuteCommandMixin):
    """Class for base agent functionality."""

    def __init__(self, api_url, advertise_address, listen_address,
                 ip_lookup_attempts, ip_lookup_sleep, network_interface,
                 lookup_timeout, lookup_interval, driver_name):
        super(IronicPythonAgent, self).__init__()
        self.ext_mgr = extension.ExtensionManager(
            namespace='ironic_python_agent.extensions',
            invoke_on_load=True,
            propagate_map_exceptions=True,
            invoke_kwds={'agent': self},
        )
        self.api_url = api_url
        self.driver_name = driver_name
        self.api_client = ironic_api_client.APIClient(self.api_url,
                                                      self.driver_name)
        self.listen_address = listen_address
        self.advertise_address = advertise_address
        self.version = pkg_resources.get_distribution('ironic-python-agent')\
            .version
        self.api = app.VersionSelectorApplication(self)
        self.heartbeater = IronicPythonAgentHeartbeater(self)
        self.heartbeat_timeout = None
        self.hardware = hardware.get_manager()
        self.log = log.getLogger(__name__)
        self.started_at = None
        self.node = None
        # lookup timeout in seconds
        self.lookup_timeout = lookup_timeout
        self.lookup_interval = lookup_interval
        self.ip_lookup_attempts = ip_lookup_attempts
        self.ip_lookup_sleep = ip_lookup_sleep
        self.network_interface = network_interface

    def get_status(self):
        """Retrieve a serializable status.

        :returns: a :class:`ironic_python_agent.agent.IronicPythonAgent`
                  instance describing the agent's status.
        """
        return IronicPythonAgentStatus(
            started_at=self.started_at,
            version=self.version
        )

    def set_agent_advertise_addr(self):
        """Set advertised IP address for the agent, if not already set.

        If agent's advertised IP address is still default (None), try to
        find a better one.  If the agent's network interface is None, replace
        that as well.

        :raises: LookupAgentInterfaceError if a valid network interface cannot
                 be found.
        :raises: LookupAgentIPError if an IP address could not be found
        """
        if self.advertise_address[0] is not None:
            return

        if self.network_interface is None:
            ifaces = self.get_agent_network_interfaces()
        else:
            ifaces = [self.network_interface]

        attempts = 0
        while (attempts < self.ip_lookup_attempts):
            for iface in ifaces:
                found_ip = self.hardware.get_ipv4_addr(iface)
                if found_ip is not None:
                    self.advertise_address = (found_ip,
                                              self.advertise_address[1])
                    self.network_interface = iface
                    return
            attempts += 1
            time.sleep(self.ip_lookup_sleep)

        raise errors.LookupAgentIPError('Agent could not find a valid IP '
                                        'address.')

    def get_agent_network_interfaces(self):
        """Get a list of all network interfaces available.

        Excludes loopback connections.

        :returns: list of network interfaces available.
        :raises: LookupAgentInterfaceError if a valid interface could not
                 be found.
        """
        iface_list = [iface.serialize()['name'] for iface in
                self.hardware.list_network_interfaces()]
        iface_list = [name for name in iface_list if 'lo' not in name]

        if len(iface_list) == 0:
            raise errors.LookupAgentInterfaceError('Agent could not find a '
                                                   'valid network interface.')
        else:
            return iface_list

    def get_node_uuid(self):
        """Get UUID for Ironic node.

        If the agent has not yet heartbeated to Ironic, it will not have
        the UUID and this will raise an exception.

        :returns: A string containing the UUID for the Ironic node.
        :raises: UnknownNodeError if UUID is unknown.
        """
        if self.node is None or 'uuid' not in self.node:
            raise errors.UnknownNodeError()
        return self.node['uuid']

    def list_command_results(self):
        """Get a list of command results.

        :returns: list of :class:`ironic_python_agent.extensions.base.
                  BaseCommandResult` objects.
        """
        return list(self.command_results.values())

    def get_command_result(self, result_id):
        """Get a specific command result by ID.

        :returns: a :class:`ironic_python_agent.extensions.base.
                  BaseCommandResult` object.
        :raises: RequestedObjectNotFoundError if command with the given ID
                 is not found.
        """
        try:
            return self.command_results[result_id]
        except KeyError:
            raise errors.RequestedObjectNotFoundError('Command Result',
                                                      result_id)

    def force_heartbeat(self):
        self.heartbeater.force_heartbeat()

    def run(self):
        """Run the Ironic Python Agent."""
        # Get the UUID so we can heartbeat to Ironic. Raises LookupNodeError
        # if there is an issue (uncaught, restart agent)
        self.started_at = _time()
        content = self.api_client.lookup_node(
                hardware_info=self.hardware.list_hardware_info(),
                timeout=self.lookup_timeout,
                starting_interval=self.lookup_interval)

        self.node = content['node']
        self.heartbeat_timeout = content['heartbeat_timeout']

        config = content.get('config', {})
        if config.get('metrics'):
            metrics.set_config(config['metrics'])

        wsgi = simple_server.make_server(
            self.listen_address[0],
            self.listen_address[1],
            self.api,
            server_class=simple_server.WSGIServer)

        # Don't start heartbeating until the server is listening
        self.heartbeater.start()

        try:
            wsgi.serve_forever()
        except BaseException:
            self.log.exception('shutting down')

        self.heartbeater.stop()
