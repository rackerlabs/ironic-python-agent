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
        LOG.debug('Getting clean steps, called with node: %(node)s, '
                  'ports: %(ports)s', {'node': node, 'ports': ports})
        # Results should be a dict, not a list
        candidate_steps = hardware.dispatch_to_all_managers('get_clean_steps',
                                                            node, ports)
        clean_steps = _deduplicate_steps(candidate_steps)

        LOG.debug('Returning clean steps: %s', steps)
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
        LOG.info('Executing clean step %s', step)
        _check_clean_version(clean_version)

        if 'step' not in step:
            msg = 'Malformed clean_step, no "step" key: %s' % step
            LOG.error(msg)
            raise ValueError(msg)
        try:
            result = hardware.dispatch_to_managers(step['step'], node, ports)
        except Exception as e:
            msg = ('Error performing clean_step %(step)s: %(err)s' %
                   {'step': step['step'], 'err': e})
            LOG.exception(msg)
            raise errors.CleaningError(msg)

        LOG.info('Clean step completed: %(step)s, result: %(result)s',
                 {'step': step, 'result': result})
        # Return the step that was executed so we can dispatch
        # to the appropriate Ironic interface
        return {
            'clean_result': result,
            'clean_step': step
        }


def _deduplicate_steps(candidate_steps):
    """Remove duplicated clean steps

    Decides priority of duplicated steps by choosing the step from the
    hardware manager with the highest hardware support level, with
    the larger priority being the tie breaker

    :param candidate_steps: The dict return from dispatch_to_all_managers
        for 'get_clean_steps'
    :returns: A deduplicated dictionary of {hardware_manager:
        [clean-steps]}
    """
    support = hardware.dispatch_to_all_managers(
        'evaluate_hardware_support')

    deduped_steps = {}
    for manager, manager_steps in candidate_steps.items():
        # We cannot deduplicate steps with unknown hardware support
        if manager not in support:
            LOG.warning('Unknown hardware support for %(manager)s, '
                        'dropping clean steps: %(steps)',
                        {'manager': manager, 'steps': manager_steps})
            continue
        for step in manager_steps:
            deduped_step = deduped_steps.get(step['step'])
            if not deduped_step:
                # No other manager has this step, add it.
                deduped_steps[step['step']] = {
                    'manager': manager, 'step': step}
                continue

            # Duplicated step, compare hardware support and priority
            deduped_support = support[deduped_step['manager']]
            if support[manager] > deduped_support:
                # Higher hardware support, use this new step
                LOG.debug('Dropping lower support level, duplicated clean '
                          'step: %s', deduped_steps[step['step']])
                deduped_steps[step['step']] = {
                    'manager': manager, 'step': step}
            elif (support[manager] == deduped_support and
                     step['priority'] > deduped_step['step']['priority']):
                # Equal hardware support, use the higher priority
                LOG.debug('Dropping lower priority, duplicated clean '
                          'step: %s', deduped_step)
                deduped_steps[step['step']] = {
                    'manager': manager, 'step': step}
            elif deduped_step is not None:
                LOG.debug('Not adding duplicated clean step: %s',
                          deduped_step)

    # Build the deduplicated clean_steps dictionary in the format
    # {manager_name: [step1, step2..]}
    clean_steps = {}
    for step in deduped_steps.values():
        clean_steps.setdefault(step['manager'], []).append(step['step'])

    return clean_steps


def _check_clean_version(clean_version=None):
    """Ensure the clean version hasn't changed."""
    # If the version is None, assume this is the first run
    if clean_version is None:
        return
    agent_version = _get_current_clean_version()
    if clean_version != agent_version:
        LOG.warning('Mismatched clean versions. Agent version: %(agent), '
                    'node version: %(node)', {'agent': agent_version,
                                              'node': clean_version})
        raise errors.CleanVersionMismatch(agent_version=agent_version,
                                          node_version=clean_version)


def _get_current_clean_version():
    return {version.get('name'): version.get('version')
            for version in hardware.dispatch_to_all_managers(
                'get_version').values()}
