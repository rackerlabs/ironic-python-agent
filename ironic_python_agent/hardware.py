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

import abc
import functools
import os
import shlex

import netifaces
from oslo_concurrency import processutils
from oslo_log import log
from oslo_utils import units
import psutil
import pyudev
import six
import stevedore

from ironic_python_agent import encoding
from ironic_python_agent import errors
from ironic_python_agent import utils

_global_managers = None
LOG = log.getLogger()


class HardwareSupport(object):
    """Example priorities for hardware managers.

    Priorities for HardwareManagers are integers, where largest means most
    specific and smallest means most generic. These values are guidelines
    that suggest values that might be returned by calls to
    `evaluate_hardware_support()`. No HardwareManager in mainline IPA will
    ever return a value greater than MAINLINE. Third party hardware managers
    should feel free to return values of SERVICE_PROVIDER or greater to
    distinguish between additional levels of hardware support.
    """
    NONE = 0
    GENERIC = 1
    MAINLINE = 2
    SERVICE_PROVIDER = 3


class HardwareType(object):
    MAC_ADDRESS = 'mac_address'


class BlockDevice(encoding.Serializable):
    serializable_fields = ('name', 'model', 'size', 'rotational')

    def __init__(self, name, model, size, rotational):
        self.name = name
        self.model = model
        self.size = size
        self.rotational = rotational


class NetworkInterface(encoding.Serializable):
    serializable_fields = ('name', 'mac_address', 'switch_port_descr',
                           'switch_chassis_descr')

    def __init__(self, name, mac_addr):
        self.name = name
        self.mac_address = mac_addr
        # TODO(russellhaering): Pull these from LLDP
        self.switch_port_descr = None
        self.switch_chassis_descr = None


class CPU(encoding.Serializable):
    serializable_fields = ('model_name', 'frequency', 'count')

    def __init__(self, model_name, frequency, count):
        self.model_name = model_name
        self.frequency = frequency
        self.count = count


class Memory(encoding.Serializable):
    serializable_fields = ('total', )

    def __init__(self, total):
        self.total = total


@six.add_metaclass(abc.ABCMeta)
class HardwareManager(object):
    @abc.abstractmethod
    def evaluate_hardware_support(self):
        pass

    def list_network_interfaces(self):
        raise errors.IncompatibleHardwareMethodError

    def get_cpus(self):
        raise errors.IncompatibleHardwareMethodError

    def list_block_devices(self):
        raise errors.IncompatibleHardwareMethodError

    def get_memory(self):
        raise errors.IncompatibleHardwareMethodError

    def get_os_install_device(self):
        raise errors.IncompatibleHardwareMethodError

    def erase_block_device(self, block_device):
        """Attempt to erase a block device.

        Implementations should detect the type of device and erase it in the
        most appropriate way possible.  Generic implementations should support
        common erase mechanisms such as ATA secure erase, or multi-pass random
        writes. Operators with more specific needs should override this method
        in order to detect and handle "interesting" cases, or delegate to the
        parent class to handle generic cases.

        For example: operators running ACME MagicStore (TM) cards alongside
        standard SSDs might check whether the device is a MagicStore and use a
        proprietary tool to erase that, otherwise call this method on their
        parent class. Upstream submissions of common functionality are
        encouraged.

        :param block_device: a BlockDevice indicating a device to be erased.
        :raises IncompatibleHardwareMethodError: when there is no known way to
                erase the block device
        :raises BlockDeviceEraseError: when there is an error erasing the
                block device
        """
        raise errors.IncompatibleHardwareMethodError

    def erase_devices(self, node, ports):
        """Erase any device that holds user data.

        By default this will attempt to erase block devices. This method can be
        overridden in an implementation-specific hardware manager in order to
        erase additional hardware, although backwards-compatible upstream
        submissions are encouraged.

        :param node: Ironic node object
        :param ports: list of Ironic port objects
        """
        block_devices = self.list_block_devices()
        for block_device in block_devices:
            self.erase_block_device(node, block_device)

    def list_hardware_info(self):
        hardware_info = {}
        hardware_info['interfaces'] = self.list_network_interfaces()
        hardware_info['cpu'] = self.get_cpus()
        hardware_info['disks'] = self.list_block_devices()
        hardware_info['memory'] = self.get_memory()
        return hardware_info

    def get_clean_steps(self, node, ports):
        """Get a list of clean steps with priority.

        Returns a list of steps. Each step is represented by a dict::

          {
           'step': the HardwareManager function to call.
           'priority': the order steps will be run in. Ironic will sort all
                       the clean steps from all the drivers, with the largest
                       priority step being run first. If priority is set to 0,
                       the step will not be run during cleaning, but may be
                       run during zapping.
           'reboot_requested': Whether the agent should request Ironic reboots
                               the node via the power driver after the
                               operation completes.
          }

        If multiple hardware managers return the same step name, the largest
        hardware support value, then largest priority will be used as the
        tie-breaker.

        The steps will be called using `hardware.dispatch_to_managers` and
        handled by the best suited hardware manager. If you need a step to be
        executed by only your hardware manager, ensure it has a unique step
        name.

        `node` and `ports` can be used by other hardware managers to further
        determine if a clean step is supported for the node.

        :param node: Ironic node object
        :param ports: list of Ironic port objects
        :return: a list of cleaning steps, where each step is described as a
                 dict as defined above

        """
        return [
            {
                'step': 'erase_devices',
                'priority': 10,
                'interface': 'deploy',
                'reboot_requested': False
            }
        ]

    def get_version(self):
        """Get a name and version for this hardware manager.

        In order to avoid errors and make agent upgrades painless, cleaning
        will check the version of all hardware managers during get_clean_steps
        at the beginning of cleaning and before executing each step in the
        agent.

        The agent isn't aware of the steps being taken before or after via
        out of band steps, so it can never know if a new step is safe to run.
        Therefore, we default to restarting the whole process.

        :returns: a dictionary with two keys: `name` and
            `version`, where `name` is a string identifying the hardware
            manager and `version` is an arbitrary version string. `name` will
            be a class variable called HARDWARE_MANAGER_NAME, or default to
            the class name and `version` will be a class variable called
            HARDWARE_MANAGER_VERSION or default to '1.0'.
        """
        return {
            'name': getattr(self, 'HARDWARE_MANAGER_NAME',
                            type(self).__name__),
            'version': getattr(self, 'HARDWARE_MANAGER_VERSION', '1.0')
        }


class GenericHardwareManager(HardwareManager):
    HARDWARE_MANAGER_NAME = 'generic_hardware_manager'
    HARDWARE_MANAGER_VERSION = '1.0'

    def __init__(self):
        self.sys_path = '/sys'

    def evaluate_hardware_support(self):
        return HardwareSupport.GENERIC

    def _get_interface_info(self, interface_name):
        addr_path = '{0}/class/net/{1}/address'.format(self.sys_path,
                                                     interface_name)
        with open(addr_path) as addr_file:
            mac_addr = addr_file.read().strip()

        return NetworkInterface(interface_name, mac_addr)

    def get_ipv4_addr(self, interface_id):
        try:
            addrs = netifaces.ifaddresses(interface_id)
            return addrs[netifaces.AF_INET][0]['addr']
        except (ValueError, IndexError, KeyError):
            # No default IPv4 address found
            return None

    def _is_device(self, interface_name):
        device_path = '{0}/class/net/{1}/device'.format(self.sys_path,
                                                      interface_name)
        return os.path.exists(device_path)

    def list_network_interfaces(self):
        iface_names = os.listdir('{0}/class/net'.format(self.sys_path))
        return [self._get_interface_info(name)
                for name in iface_names
                if self._is_device(name)]

    def _get_cpu_count(self):
        if psutil.version_info[0] == 1:
            return psutil.NUM_CPUS
        elif psutil.version_info[0] == 2:
            return psutil.cpu_count()
        else:
            raise AttributeError("Only psutil versions 1 and 2 supported")

    def get_cpus(self):
        model = None
        freq = None
        with open('/proc/cpuinfo') as f:
            lines = f.read()
            for line in lines.split('\n'):
                if model and freq:
                    break
                if not model and line.startswith('model name'):
                    model = line.split(':')[1].strip()
                if not freq and line.startswith('cpu MHz'):
                    freq = line.split(':')[1].strip()

        return CPU(model, freq, self._get_cpu_count())

    def get_memory(self):
        # psutil returns a long, so we force it to an int
        if psutil.version_info[0] == 1:
            return Memory(int(psutil.TOTAL_PHYMEM))
        elif psutil.version_info[0] == 2:
            return Memory(int(psutil.phymem_usage().total))

    def list_block_devices(self):
        """List all physical block devices

        The switches we use for lsblk: P for KEY="value" output,
        b for size output in bytes, d to exclude dependant devices
        (like md or dm devices), i to ensure ascii characters only,
        and  o to specify the fields we need

        :return: A list of BlockDevices
        """
        report = utils.execute('lsblk', '-PbdioKNAME,MODEL,SIZE,ROTA,TYPE',
                               check_exit_code=[0])[0]
        lines = report.split('\n')

        devices = []
        for line in lines:
            device = {}
            # Split into KEY=VAL pairs
            vals = shlex.split(line)
            for key, val in (v.split('=', 1) for v in vals):
                device[key] = val.strip()
            # Ignore non disk
            if device.get('TYPE') != 'disk':
                continue

            # Ensure all required keys are at least present, even if blank
            diff = set(['KNAME', 'MODEL', 'SIZE', 'ROTA']) - set(device.keys())
            if diff:
                raise errors.BlockDeviceError(
                    '%s must be returned by lsblk.' % diff)
            devices.append(BlockDevice(name='/dev/' + device['KNAME'],
                                       model=device['MODEL'],
                                       size=int(device['SIZE']),
                                       rotational=bool(int(device['ROTA']))))
        return devices

    def _get_device_vendor(self, dev):
        """Get the vendor name of a given device."""
        try:
            devname = os.path.basename(dev)
            with open('/sys/class/block/%s/device/vendor' % devname, 'r') as f:
                return f.read().strip()
        except IOError:
            LOG.warning("Can't find the device vendor for device %s", dev)

    def get_os_install_device(self):
        block_devices = self.list_block_devices()
        root_device_hints = utils.parse_root_device_hints()

        if not root_device_hints:
            # If no hints are passed find the first device larger than
            # 4GB, assume it is the OS disk
            # TODO(russellhaering): This isn't a valid assumption in
            # all cases, is there a more reasonable default behavior?
            block_devices.sort(key=lambda device: device.size)
            for device in block_devices:
                if device.size >= (4 * pow(1024, 3)):
                    return device.name
        else:

            def match(hint, current_value, device):
                hint_value = root_device_hints[hint]
                if hint_value != current_value:
                    LOG.debug("Root device hint %(hint)s=%(value)s does not "
                              "match the device %(device)s value of "
                              "%(current)s", {'hint': hint,
                              'value': hint_value, 'device': device,
                              'current': current_value})
                    return False
                return True

            context = pyudev.Context()
            for dev in block_devices:
                try:
                    udev = pyudev.Device.from_device_file(context, dev.name)
                except (ValueError, EnvironmentError) as e:
                    LOG.warning("Device %(dev)s is inaccessible, skipping... "
                    "Error: %(error)s", {'dev': dev, 'error': e})
                    continue

                # TODO(lucasagomes): Add support for operators <, >, =, etc...
                # to better deal with sizes.
                if 'size' in root_device_hints:
                    # Since we don't support units yet we expect the size
                    # in GiB for now
                    size = dev.size / units.Gi
                    if not match('size', size, dev.name):
                        continue

                if 'model' in root_device_hints:
                    model = udev.get('ID_MODEL', None)
                    if not model:
                        continue
                    model = utils.normalize(model)
                    if not match('model', model, dev.name):
                        continue

                if 'wwn' in root_device_hints:
                    wwn = udev.get('ID_WWN', None)
                    if not wwn:
                        continue
                    wwn = utils.normalize(wwn)
                    if not match('wwn', wwn, dev.name):
                        continue

                if 'serial' in root_device_hints:
                    # TODO(lucasagomes): Since lsblk only supports
                    # returning the short serial we are using
                    # ID_SERIAL_SHORT here to keep compatibility with the
                    # bash deploy ramdisk
                    serial = udev.get('ID_SERIAL_SHORT', None)
                    if not serial:
                        continue
                    serial = utils.normalize(serial)
                    if not match('serial', serial, dev.name):
                        continue

                if 'vendor' in root_device_hints:
                    vendor = self._get_device_vendor(dev.name)
                    if not vendor:
                        continue
                    vendor = utils.normalize(vendor)
                    if not match('vendor', vendor, dev.name):
                        continue

                return dev.name

            else:
                raise errors.DeviceNotFound("No suitable device was found for "
                    "deployment using these hints %s" % root_device_hints)

    def erase_block_device(self, node, block_device):

        # Check if the block device is virtual media and skip the device.
        if self._is_virtual_media_device(block_device):
            LOG.info("Skipping the erase of virtual media device %s",
                     block_device.name)
            return

        if self._ata_erase(block_device):
            return

        if self._shred_block_device(node, block_device):
            return

        msg = ('Unable to erase block device {0}: device is unsupported.'
              ).format(block_device.name)
        LOG.error(msg)
        raise errors.IncompatibleHardwareMethodError(msg)

    def _shred_block_device(self, node, block_device):
        """Erase a block device using shred.

        :param node: Ironic node info.
        :param block_device: a BlockDevice object to be erased
        :returns: True if the erase succeeds, False if it fails for any reason
        """
        info = node.get('driver_internal_info', {})
        npasses = info.get('agent_erase_devices_iterations', 1)
        try:
            utils.execute('shred', '--force', '--zero', '--verbose',
                          '--iterations', str(npasses), block_device.name)
        except (processutils.ProcessExecutionError, OSError) as e:
            msg = ("Erasing block device %(dev)s failed with error %(err)s ",
                  {'dev': block_device.name, 'err': e})
            LOG.error(msg)
            return False

        return True

    def _is_virtual_media_device(self, block_device):
        """Check if the block device corresponds to Virtual Media device.

        :param block_device: a BlockDevice object
        :returns: True if it's a virtual media device, else False
        """
        vm_device_label = '/dev/disk/by-label/ir-vfd-dev'
        if os.path.exists(vm_device_label):
            link = os.readlink(vm_device_label)
            device = os.path.normpath(os.path.join(os.path.dirname(
                                                  vm_device_label), link))
            if block_device.name == device:
                return True
        return False

    def _get_ata_security_lines(self, block_device):
        output = utils.execute('hdparm', '-I', block_device.name)[0]

        if '\nSecurity: ' not in output:
            return []

        # Get all lines after the 'Security: ' line
        security_and_beyond = output.split('\nSecurity: \n')[1]
        security_and_beyond_lines = security_and_beyond.split('\n')

        security_lines = []
        for line in security_and_beyond_lines:
            if line.startswith('\t'):
                security_lines.append(line.strip().replace('\t', ' '))
            else:
                break

        return security_lines

    def _ata_erase(self, block_device):
        security_lines = self._get_ata_security_lines(block_device)

        # If secure erase isn't supported return False so erase_block_device
        # can try another mechanism. Below here, if secure erase is supported
        # but fails in some way, error out (operators of hardware that supports
        # secure erase presumably expect this to work).
        if 'supported' not in security_lines:
            return False

        if 'enabled' in security_lines:
            raise errors.BlockDeviceEraseError(('Block device {0} already has '
                'a security password set').format(block_device.name))

        if 'not frozen' not in security_lines:
            raise errors.BlockDeviceEraseError(('Block device {0} is frozen '
                'and cannot be erased').format(block_device.name))

        utils.execute('hdparm', '--user-master', 'u', '--security-set-pass',
                      'NULL', block_device.name)

        # Use the 'enhanced' security erase option if it's supported.
        erase_option = '--security-erase'
        if 'not supported: enhanced erase' not in security_lines:
            erase_option += '-enhanced'

        utils.execute('hdparm', '--user-master', 'u', erase_option,
                      'NULL', block_device.name)

        # Verify that security is now 'not enabled'
        security_lines = self._get_ata_security_lines(block_device)
        if 'not enabled' not in security_lines:
            raise errors.BlockDeviceEraseError(('An unknown error occurred '
                'erasing block device {0}').format(block_device.name))

        return True


def _compare_extensions(ext1, ext2):
    mgr1 = ext1.obj
    mgr2 = ext2.obj
    return mgr2.evaluate_hardware_support() - mgr1.evaluate_hardware_support()


def _get_managers():
    """Get a list of hardware managers in priority order.

    Use stevedore to find all eligible hardware managers, sort them based on
    self-reported (via evaluate_hardware_support()) priorities, and return them
    in a list. The resulting list is cached in _global_managers.

    :returns: Priority-sorted list of hardware managers
    :raises HardwareManagerNotFound: if no valid hardware managers found
    """
    global _global_managers

    if not _global_managers:
        extension_manager = stevedore.ExtensionManager(
            namespace='ironic_python_agent.hardware_managers',
            invoke_on_load=True)

        # There will always be at least one extension available (the
        # GenericHardwareManager).
        if six.PY2:
            extensions = sorted(extension_manager, _compare_extensions)
        else:
            extensions = sorted(extension_manager,
                            key=functools.cmp_to_key(_compare_extensions))

        preferred_managers = []

        for extension in extensions:
            if extension.obj.evaluate_hardware_support() > 0:
                preferred_managers.append(extension.obj)
                LOG.info('Hardware manager found: {0}'.format(
                    extension.entry_point_target))

        if not preferred_managers:
            raise errors.HardwareManagerNotFound

        _global_managers = preferred_managers

    return _global_managers


def dispatch_to_all_managers(method, *args, **kwargs):
    """Dispatch a method to all hardware managers.

    Dispatches the given method in priority order as sorted by
    `_get_managers`. If the method doesn't exist or raises
    IncompatibleHardwareMethodError, it continues to the next hardware manager.
    All managers that have hardware support for this node will be called,
    and their responses will be added to a dictionary of the form
    {HardwareManagerClassName: response}.

    :param method: hardware manager method to dispatch
    :param *args: arguments to dispatched method
    :param **kwargs: keyword arguments to dispatched method
    :raises errors.HardwareManagerMethodNotFound: if all managers raise
        IncompatibleHardwareMethodError.
    :returns: a dictionary with keys for each hardware manager that returns
        a response and the value as a list of results from that hardware
        manager.
    """
    responses = {}
    managers = _get_managers()
    for manager in managers:
        if getattr(manager, method, None):
            try:
                response = getattr(manager, method)(*args, **kwargs)
            except errors.IncompatibleHardwareMethodError:
                LOG.debug('HardwareManager {0} does not support {1}'
                          .format(manager, method))
                continue
            except Exception as e:
                LOG.exception('Unexpected error dispatching %(method)s to '
                              'manager %(manager)s: %(e)s',
                              {'method': method, 'manager': manager, 'e': e})
                raise
            responses[manager.__class__.__name__] = response
        else:
            LOG.debug('HardwareManager {0} does not have method {1}'
                      .format(manager, method))

    if responses == {}:
        raise errors.HardwareManagerMethodNotFound(method)

    return responses


def dispatch_to_managers(method, *args, **kwargs):
    """Dispatch a method to best suited hardware manager.

    Dispatches the given method in priority order as sorted by
    `_get_managers`. If the method doesn't exist or raises
    IncompatibleHardwareMethodError, it is attempted again with a more generic
    hardware manager. This continues until a method executes that returns
    any result without raising an IncompatibleHardwareMethodError.

    :param method: hardware manager method to dispatch
    :param *args: arguments to dispatched method
    :param **kwargs: keyword arguments to dispatched method

    :returns: result of successful dispatch of method
    :raises HardwareManagerMethodNotFound: if all managers failed the method
    :raises HardwareManagerNotFound: if no valid hardware managers found
    """
    managers = _get_managers()
    for manager in managers:
        if getattr(manager, method, None):
            try:
                return getattr(manager, method)(*args, **kwargs)
            except(errors.IncompatibleHardwareMethodError):
                LOG.debug('HardwareManager {0} does not support {1}'
                        .format(manager, method))
            except Exception as e:
                LOG.exception('Unexpected error dispatching %(method)s to '
                              'manager %(manager)s: %(e)s',
                              {'method': method, 'manager': manager, 'e': e})
                raise
        else:
            LOG.debug('HardwareManager {0} does not have method {1}'
                      .format(manager, method))

    raise errors.HardwareManagerMethodNotFound(method)
