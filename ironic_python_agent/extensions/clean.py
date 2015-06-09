# Copyright 2015 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo_log import log

from ironic_python_agent import errors
from ironic_python_agent.extensions import base
from ironic_python_agent import hardware


LOG = log.getLogger()


class CleanExtension(base.BaseAgentExtension):
    @base.sync_command('get_clean_steps')
    def get_clean_steps(self, node, ports):
        """Get the list of clean steps supported for the node and ports

        :param node: A dict representation of a node
        :param ports: A dict representation of ports attached to node

        :returns: A list of clean steps with keys step, priority, and
            reboot_requested
        """
        # Results should be a dict, not a list
        candidate_steps = hardware.dispatch_to_all_managers('get_clean_steps',
                                                            node, ports)

        # Remove duplicates. Highest priority step wins, others are removed
        deduped_steps = {}
        for manager, manager_steps in candidate_steps.items():
            for step in manager_steps:
                # Check if step is already in deduped steps or if this
                # step has a high priority
                deduped_step = deduped_steps.get(step['step'])
                if (deduped_step is None or
                        step['priority'] > deduped_step['step']['priority']):
                    # Save the step and which manager it belongs to
                    deduped_steps[step['step']] = {
                        'manager': manager, 'step': step}
                elif deduped_step is not None:
                    LOG.debug('Dropping lower priority, duplicated clean '
                              'step: %s', deduped_step)

        # Initialize the clean_steps dictionary to return with the list of
        # manager names and empty array for steps
        clean_steps = {manager: [] for manager in candidate_steps.keys()}

        # Build the deduplicated clean_steps dictionary in the format
        # {manager_name: [step1, step2..]}
        for step in deduped_steps.values():
            clean_steps[step['manager']].append(step['step'])

        return {
            'clean_steps': clean_steps,
            'hardware_manager_version': _get_current_clean_version()
        }

    @base.async_command('execute_clean_step')
    def execute_clean_step(self, step, node, ports, clean_version=None,
                           **kwargs):
        """Execute a clean step.

        :param step: A clean step with 'step', 'priority' and 'interface' keys
        :param node: A dict representation of a node
        :param ports: A dict representation of ports attached to node
        :param clean_version: The clean version as returned by
                              _get_current_clean_version() at the beginning
                              of cleaning/zapping
        :returns: a CommandResult object with command_result set to whatever
            the step returns.
        """
        # Ensure the agent is still the same version, or raise an exception
        _check_clean_version(clean_version)

        if 'step' not in step:
            raise ValueError('Malformed clean_step, no "step" key: %s'.format(
                step))
        try:
            result = hardware.dispatch_to_managers(step['step'], node, ports)
        except Exception as e:
            raise errors.CleaningError(
                'Error performing clean_step %(step)s: %(err)s' %
                {'step': step['step'], 'err': e})
        # Return the step that was executed so we can dispatch
        # to the appropriate Ironic interface
        return {
            'clean_result': result,
            'clean_step': step
        }


def _check_clean_version(clean_version=None):
    """Ensure the clean version hasn't changed."""
    # If the version is None, assume this is the first run
    if clean_version is None:
        return
    agent_version = _get_current_clean_version()
    if clean_version != agent_version:
        raise errors.CleanVersionMismatch(agent_version=agent_version,
                                          node_version=clean_version)


def _get_current_clean_version():
    return {version.get('name'): version.get('version')
            for version in hardware.dispatch_to_all_managers(
                'get_version').values()}
