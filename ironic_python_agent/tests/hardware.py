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

import mock
from oslotest import base as test_base
import six
from stevedore import extension

from ironic_python_agent import errors
from ironic_python_agent import hardware
from ironic_python_agent import utils

if six.PY2:
    OPEN_FUNCTION_NAME = '__builtin__.open'
else:
    OPEN_FUNCTION_NAME = 'builtins.open'

HDPARM_INFO_TEMPLATE = (
    '/dev/sda:\n'
    '\n'
    'ATA device, with non-removable media\n'
    '\tModel Number:       7 PIN  SATA FDM\n'
    '\tSerial Number:      20131210000000000023\n'
    '\tFirmware Revision:  SVN406\n'
    '\tTransport:          Serial, ATA8-AST, SATA 1.0a, SATA II Extensions, '
        'SATA Rev 2.5, SATA Rev 2.6, SATA Rev 3.0\n'
    'Standards: \n'
    '\tSupported: 9 8 7 6 5\n'
    '\tLikely used: 9\n'
    'Configuration: \n'
    '\tLogical\t\tmax\tcurrent\n'
    '\tcylinders\t16383\t16383\n'
    '\theads\t\t16\t16\n'
    '\tsectors/track\t63\t63\n'
    '\t--\n'
    '\tCHS current addressable sectors:   16514064\n'
    '\tLBA    user addressable sectors:   60579792\n'
    '\tLBA48  user addressable sectors:   60579792\n'
    '\tLogical  Sector size:                   512 bytes\n'
    '\tPhysical Sector size:                   512 bytes\n'
    '\tLogical Sector-0 offset:                  0 bytes\n'
    '\tdevice size with M = 1024*1024:       29579 MBytes\n'
    '\tdevice size with M = 1000*1000:       31016 MBytes (31 GB)\n'
    '\tcache/buffer size  = unknown\n'
    '\tForm Factor: 2.5 inch\n'
    '\tNominal Media Rotation Rate: Solid State Device\n'
    'Capabilities: \n'
    '\tLBA, IORDY(can be disabled)\n'
    '\tQueue depth: 32\n'
    '\tStandby timer values: spec\'d by Standard, no device specific '
        'minimum\n'
    '\tR/W multiple sector transfer: Max = 1\tCurrent = 1\n'
    '\tDMA: mdma0 mdma1 mdma2 udma0 udma1 udma2 udma3 udma4 *udma5\n'
    '\t     Cycle time: min=120ns recommended=120ns\n'
    '\tPIO: pio0 pio1 pio2 pio3 pio4\n'
    '\t     Cycle time: no flow control=120ns  IORDY flow '
        'control=120ns\n'
    'Commands/features: \n'
    '\tEnabled\tSupported:\n'
    '\t   *\tSMART feature set\n'
    '\t    \tSecurity Mode feature set\n'
    '\t   *\tPower Management feature set\n'
    '\t   *\tWrite cache\n'
    '\t   *\tLook-ahead\n'
    '\t   *\tHost Protected Area feature set\n'
    '\t   *\tWRITE_BUFFER command\n'
    '\t   *\tREAD_BUFFER command\n'
    '\t   *\tNOP cmd\n'
    '\t    \tSET_MAX security extension\n'
    '\t   *\t48-bit Address feature set\n'
    '\t   *\tDevice Configuration Overlay feature set\n'
    '\t   *\tMandatory FLUSH_CACHE\n'
    '\t   *\tFLUSH_CACHE_EXT\n'
    '\t   *\tWRITE_{DMA|MULTIPLE}_FUA_EXT\n'
    '\t   *\tWRITE_UNCORRECTABLE_EXT command\n'
    '\t   *\tGen1 signaling speed (1.5Gb/s)\n'
    '\t   *\tGen2 signaling speed (3.0Gb/s)\n'
    '\t   *\tGen3 signaling speed (6.0Gb/s)\n'
    '\t   *\tNative Command Queueing (NCQ)\n'
    '\t   *\tHost-initiated interface power management\n'
    '\t   *\tPhy event counters\n'
    '\t   *\tDMA Setup Auto-Activate optimization\n'
    '\t    \tDevice-initiated interface power management\n'
    '\t   *\tSoftware settings preservation\n'
    '\t    \tunknown 78[8]\n'
    '\t   *\tSMART Command Transport (SCT) feature set\n'
    '\t   *\tSCT Error Recovery Control (AC3)\n'
    '\t   *\tSCT Features Control (AC4)\n'
    '\t   *\tSCT Data Tables (AC5)\n'
    '\t   *\tData Set Management TRIM supported (limit 2 blocks)\n'
    'Security: \n'
    '\tMaster password revision code = 65534\n'
    '\t%(supported)s\n'
    '\t%(enabled)s\n'
    '\tnot\tlocked\n'
    '\t%(frozen)s\n'
    '\tnot\texpired: security count\n'
    '\t\tsupported: enhanced erase\n'
    '\t24min for SECURITY ERASE UNIT. 24min for ENHANCED SECURITY '
        'ERASE UNIT.\n'
    'Checksum: correct\n'
)

BLK_DEVICE_TEMPLATE = (
    'KNAME="sda" MODEL="TinyUSB Drive" SIZE="3116853504" '
    'ROTA="0" TYPE="disk"\n'
    'KNAME="sdb" MODEL="Fastable SD131 7" SIZE="31016853504" '
    'ROTA="0" TYPE="disk"\n'
    'KNAME="sdc" MODEL="NWD-BLP4-1600   " SIZE="1765517033472" '
    ' ROTA="0" TYPE="disk"\n'
    'KNAME="sdd" MODEL="NWD-BLP4-1600   " SIZE="1765517033472" '
    ' ROTA="0" TYPE="disk"\n'
    'KNAME="loop0" MODEL="" SIZE="109109248" ROTA="1" TYPE="loop"'
)


class FakeHardwareManager(hardware.GenericHardwareManager):
    def __init__(self, hardware_support):
        self._hardware_support = hardware_support

    def evaluate_hardware_support(self):
        return self._hardware_support


class TestHardwareManagerLoading(test_base.BaseTestCase):
    def setUp(self):
        super(TestHardwareManagerLoading, self).setUp()
        # In order to use ExtensionManager.make_test_instance() without
        # creating a new only-for-test codepath, we instantiate the test
        # instance outside of the test case in setUp, where we can access
        # make_test_instance() before it gets mocked. Inside of the test case
        # we set this as the return value of the mocked constructor, so we can
        # verify that the constructor is called correctly while still using a
        # more realistic ExtensionManager
        fake_ep = mock.Mock()
        fake_ep.module_name = 'fake'
        fake_ep.attrs = ['fake attrs']
        ext1 = extension.Extension('fake_generic0', fake_ep, None,
            FakeHardwareManager(hardware.HardwareSupport.GENERIC))
        ext2 = extension.Extension('fake_mainline0', fake_ep, None,
            FakeHardwareManager(hardware.HardwareSupport.MAINLINE))
        ext3 = extension.Extension('fake_generic1', fake_ep, None,
            FakeHardwareManager(hardware.HardwareSupport.GENERIC))
        self.correct_hw_manager = ext2.obj
        self.fake_ext_mgr = extension.ExtensionManager.make_test_instance([
            ext1, ext2, ext3
        ])

    @mock.patch('stevedore.ExtensionManager')
    def test_hardware_manager_loading(self, mocked_extension_mgr_constructor):
        hardware._global_manager = None
        mocked_extension_mgr_constructor.return_value = self.fake_ext_mgr

        preferred_hw_manager = hardware.get_manager()
        mocked_extension_mgr_constructor.assert_called_once_with(
            namespace='ironic_python_agent.hardware_managers',
            invoke_on_load=True)
        self.assertEqual(self.correct_hw_manager, preferred_hw_manager)


class TestGenericHardwareManager(test_base.BaseTestCase):
    def setUp(self):
        super(TestGenericHardwareManager, self).setUp()
        self.hardware = hardware.GenericHardwareManager()

    @mock.patch('os.listdir')
    @mock.patch('os.path.exists')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test_list_network_interfaces(self,
                                     mocked_open,
                                     mocked_exists,
                                     mocked_listdir):
        mocked_listdir.return_value = ['lo', 'eth0']
        mocked_exists.side_effect = [False, True]
        mocked_open.return_value.__enter__ = lambda s: s
        mocked_open.return_value.__exit__ = mock.Mock()
        read_mock = mocked_open.return_value.read
        read_mock.return_value = '00:0c:29:8c:11:b1\n'
        interfaces = self.hardware.list_network_interfaces()
        self.assertEqual(len(interfaces), 1)
        self.assertEqual(interfaces[0].name, 'eth0')
        self.assertEqual(interfaces[0].mac_address, '00:0c:29:8c:11:b1')

    @mock.patch.object(utils, 'execute')
    def test_get_os_install_device(self, mocked_execute):
        mocked_execute.return_value = (BLK_DEVICE_TEMPLATE, '')
        self.assertEqual(self.hardware.get_os_install_device(), '/dev/sdb')
        mocked_execute.assert_called_once_with(
            'lsblk', '-PbdioKNAME,MODEL,SIZE,ROTA,TYPE', check_exit_code=[0])

    @mock.patch('ironic_python_agent.hardware.GenericHardwareManager.'
                '_get_cpu_count')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test_get_cpus(self, mocked_open, mocked_cpucount):
        mocked_open.return_value.__enter__ = lambda s: s
        mocked_open.return_value.__exit__ = mock.Mock()
        read_mock = mocked_open.return_value.read
        read_mock.return_value = (
            'processor       : 0\n'
            'vendor_id       : GenuineIntel\n'
            'cpu family      : 6\n'
            'model           : 58\n'
            'model name      : Intel(R) Core(TM) i7-3720QM CPU @ 2.60GHz\n'
            'stepping        : 9\n'
            'microcode       : 0x15\n'
            'cpu MHz         : 2594.685\n'
            'cache size      : 6144 KB\n'
            'fpu             : yes\n'
            'fpu_exception   : yes\n'
            'cpuid level     : 13\n'
            'wp              : yes\n'
            'flags           : fpu vme de pse tsc msr pae mce cx8 apic sep '
            'mtrr pge mca cmov pat pse36 clflush dts mmx fxsr sse sse2 ss '
            'syscall nx rdtscp lm constant_tsc arch_perfmon pebs bts nopl '
            'xtopology tsc_reliable nonstop_tsc aperfmperf eagerfpu pni '
            'pclmulqdq ssse3 cx16 pcid sse4_1 sse4_2 x2apic popcnt aes xsave '
            'avx f16c rdrand hypervisor lahf_lm ida arat epb xsaveopt pln pts '
            'dtherm fsgsbase smep\n'
            'bogomips        : 5189.37\n'
            'clflush size    : 64\n'
            'cache_alignment : 64\n'
            'address sizes   : 40 bits physical, 48 bits virtual\n'
            'power management:\n'
            '\n'
            'processor       : 1\n'
            'vendor_id       : GenuineIntel\n'
            'cpu family      : 6\n'
            'model           : 58\n'
            'model name      : Intel(R) Core(TM) i7-3720QM CPU @ 2.60GHz\n'
            'stepping        : 9\n'
            'microcode       : 0x15\n'
            'cpu MHz         : 2594.685\n'
            'cache size      : 6144 KB\n'
            'fpu             : yes\n'
            'fpu_exception   : yes\n'
            'cpuid level     : 13\n'
            'wp              : yes\n'
            'flags           : fpu vme de pse tsc msr pae mce cx8 apic sep '
            'mtrr pge mca cmov pat pse36 clflush dts mmx fxsr sse sse2 ss '
            'syscall nx rdtscp lm constant_tsc arch_perfmon pebs bts nopl '
            'xtopology tsc_reliable nonstop_tsc aperfmperf eagerfpu pni '
            'pclmulqdq ssse3 cx16 pcid sse4_1 sse4_2 x2apic popcnt aes xsave '
            'avx f16c rdrand hypervisor lahf_lm ida arat epb xsaveopt pln pts '
            'dtherm fsgsbase smep\n'
            'bogomips        : 5189.37\n'
            'clflush size    : 64\n'
            'cache_alignment : 64\n'
            'address sizes   : 40 bits physical, 48 bits virtual\n'
            'power management:\n'
        )

        mocked_cpucount.return_value = 2

        cpus = self.hardware.get_cpus()
        self.assertEqual(cpus.model_name,
                         'Intel(R) Core(TM) i7-3720QM CPU @ 2.60GHz')
        self.assertEqual(cpus.frequency, '2594.685')
        self.assertEqual(cpus.count, 2)

    def test_list_hardware_info(self):
        self.hardware.list_network_interfaces = mock.Mock()
        self.hardware.list_network_interfaces.return_value = [
            hardware.NetworkInterface('eth0', '00:0c:29:8c:11:b1'),
            hardware.NetworkInterface('eth1', '00:0c:29:8c:11:b2'),
        ]

        self.hardware.get_cpus = mock.Mock()
        self.hardware.get_cpus.return_value = hardware.CPU(
            'Awesome CPU x14 9001',
            9001,
            14)

        self.hardware.get_memory = mock.Mock()
        self.hardware.get_memory.return_value = hardware.Memory(1017012)

        self.hardware.list_block_devices = mock.Mock()
        self.hardware.list_block_devices.return_value = [
            hardware.BlockDevice('/dev/sdj', 'big', 1073741824, True),
            hardware.BlockDevice('/dev/hdaa', 'small', 65535, False),
        ]

        hardware_info = self.hardware.list_hardware_info()
        self.assertEqual(hardware_info['memory'], self.hardware.get_memory())
        self.assertEqual(hardware_info['cpu'], self.hardware.get_cpus())
        self.assertEqual(hardware_info['disks'],
                         self.hardware.list_block_devices())
        self.assertEqual(hardware_info['interfaces'],
                         self.hardware.list_network_interfaces())

    @mock.patch.object(utils, 'execute')
    def test_list_block_device(self, mocked_execute):
        mocked_execute.return_value = (BLK_DEVICE_TEMPLATE, '')
        devices = self.hardware.list_block_devices()
        expected_devices = [
            hardware.BlockDevice(name='/dev/sda',
                                 model='TinyUSB Drive',
                                 size=3116853504,
                                 rotational=False),
            hardware.BlockDevice(name='/dev/sdb',
                                 model='Fastable SD131 7',
                                 size=31016853504,
                                 rotational=False),
            hardware.BlockDevice(name='/dev/sdc',
                                 model='NWD-BLP4-1600',
                                 size=1765517033472,
                                 rotational=False),
            hardware.BlockDevice(name='/dev/sdd',
                                 model='NWD-BLP4-1600',
                                 size=1765517033472,
                                 rotational=False)
        ]

        self.assertEqual(4, len(expected_devices))
        for expected, device in zip(expected_devices, devices):
            # Compare all attrs of the objects
            for attr in ['name', 'model', 'size', 'rotational']:
                self.assertEqual(getattr(expected, attr),
                                 getattr(device, attr))

    @mock.patch.object(utils, 'execute')
    def test_erase_block_device_ata_success(self, mocked_execute):
        hdparm_info_fields = {
            'supported': '\tsupported',
            'enabled': 'not\tenabled',
            'frozen': 'not\tfrozen',
        }
        mocked_execute.side_effect = [
            (HDPARM_INFO_TEMPLATE % hdparm_info_fields, ''),
            ('', ''),
            ('', ''),
            (HDPARM_INFO_TEMPLATE % hdparm_info_fields, ''),
        ]

        block_device = hardware.BlockDevice('/dev/sda', 'big', 1073741824,
                                            True)
        self.hardware.erase_block_device(block_device)
        mocked_execute.assert_has_calls([
            mock.call('hdparm', '-I', '/dev/sda'),
            mock.call('hdparm', '--user-master', 'u', '--security-set-pass',
                      'NULL', '/dev/sda', check_exit_code=[0]),
            mock.call('hdparm', '--user-master', 'u', '--security-erase',
                      'NULL', '/dev/sda', check_exit_code=[0]),
            mock.call('hdparm', '-I', '/dev/sda'),
        ])

    @mock.patch.object(utils, 'execute')
    def test_erase_block_device_ata_nosecurtiy(self, mocked_execute):
        hdparm_output = HDPARM_INFO_TEMPLATE.split('\nSecurity:')[0]

        mocked_execute.side_effect = [
            (hdparm_output, '')
        ]

        block_device = hardware.BlockDevice('/dev/sda', 'big', 1073741824,
                                            True)
        self.assertRaises(errors.BlockDeviceEraseError,
                          self.hardware.erase_block_device,
                          block_device)

    @mock.patch.object(utils, 'execute')
    def test_erase_block_device_ata_not_supported(self, mocked_execute):
        hdparm_output = HDPARM_INFO_TEMPLATE % {
            'supported': 'not\tsupported',
            'enabled': 'not\tenabled',
            'frozen': 'not\tfrozen',
        }

        mocked_execute.side_effect = [
            (hdparm_output, '')
        ]

        block_device = hardware.BlockDevice('/dev/sda', 'big', 1073741824,
                                            True)
        self.assertRaises(errors.BlockDeviceEraseError,
                          self.hardware.erase_block_device,
                          block_device)

    @mock.patch.object(utils, 'execute')
    def test_erase_block_device_ata_security_enabled(self, mocked_execute):
        hdparm_output = HDPARM_INFO_TEMPLATE % {
            'supported': '\tsupported',
            'enabled': '\tenabled',
            'frozen': 'not\tfrozen',
        }

        mocked_execute.side_effect = [
            (hdparm_output, '')
        ]

        block_device = hardware.BlockDevice('/dev/sda', 'big', 1073741824,
                                            True)
        self.assertRaises(errors.BlockDeviceEraseError,
                          self.hardware.erase_block_device,
                          block_device)

    @mock.patch.object(utils, 'execute')
    def test_erase_block_device_ata_frozen(self, mocked_execute):
        hdparm_output = HDPARM_INFO_TEMPLATE % {
            'supported': '\tsupported',
            'enabled': 'not\tenabled',
            'frozen': '\tfrozen',
        }

        mocked_execute.side_effect = [
            (hdparm_output, '')
        ]

        block_device = hardware.BlockDevice('/dev/sda', 'big', 1073741824,
                                            True)
        self.assertRaises(errors.BlockDeviceEraseError,
                          self.hardware.erase_block_device,
                          block_device)

    @mock.patch.object(utils, 'execute')
    def test_erase_block_device_ata_failed(self, mocked_execute):
        hdparm_output_before = HDPARM_INFO_TEMPLATE % {
            'supported': '\tsupported',
            'enabled': 'not\tenabled',
            'frozen': 'not\tfrozen',
        }

        # If security mode remains enabled after the erase, it is indiciative
        # of a failed erase.
        hdparm_output_after = HDPARM_INFO_TEMPLATE % {
            'supported': '\tsupported',
            'enabled': '\tenabled',
            'frozen': 'not\tfrozen',
        }

        mocked_execute.side_effect = [
            (hdparm_output_before, ''),
            ('', ''),
            ('', ''),
            (hdparm_output_after, ''),
        ]

        block_device = hardware.BlockDevice('/dev/sda', 'big', 1073741824,
                                            True)
        self.assertRaises(errors.BlockDeviceEraseError,
                          self.hardware.erase_block_device,
                          block_device)


class TestDecommission(test_base.BaseTestCase):
    def setUp(self):
        super(TestDecommission, self).setUp()
        self.next_target = {
            'decommission_next_state': 'fake_next',
            'reboot_requested': True
        }
        self.decommission_steps = [
            {
                'state': 'update_bios',
                'function': 'update_bios',
                'priority': 10,
                'reboot_requested': False,
            },
            {
                'state': 'update_firmware',
                'function': 'update_firmware',
                'priority': 20,
                'reboot_requested': False,
            },
            {
                'state': 'erase_hardware',
                'function': 'erase_hardware',
                'priority': 30,
                'reboot_requested': False,
            },
        ]
        self.node = {
            'uuid': '8a2ff766-a28e-4bf2-aada-2c969ccf3398',
            'driver_info': {
                'decommission_target_state': 'update_bios',
                'hardware_manager_version': '1'},
            'properties': {
                "memory_mb": 524288,
                "cpu_arch": "amd64",
                "local_gb": 32,
                "cpus": 12
            }
        }
        self.ports = [
            {
                'node_id': '8a2ff766-a28e-4bf2-aada-2c969ccf3398',
                'address': 'aa:bb:cc:dd:ee:ff'
            },
            {
                'node_id': '8a2ff766-a28e-4bf2-aada-2c969ccf3398',
                'address': 'aa:bb:cc:dd:ee:fe'
            }
        ]
        self.hardware_manager = hardware.GenericHardwareManager()

    @mock.patch('ironic_python_agent.hardware.GenericHardwareManager'
                '.update_bios')
    @mock.patch('ironic_python_agent.hardware.GenericHardwareManager'
                '._get_next_target_state')
    def test_decommission(self, next_target_mock, bios_mock):
        next_target_mock.return_value = self.next_target
        decom_return = self.hardware_manager.decommission(self.node,
                                                          self.ports)
        bios_mock.assert_called_with(self.node, self.ports)
        self.assertEqual(self.next_target, decom_return)

    @mock.patch('ironic_python_agent.hardware.GenericHardwareManager'
                '.update_bios')
    @mock.patch('ironic_python_agent.hardware.GenericHardwareManager'
                '._get_next_target_state')
    def test_decommission_first_run(self, next_target_mock, bios_mock):
        next_target_mock.return_value = self.next_target
        # Represent first run
        self.node['driver_info']['decommission_target_state'] = None
        decom_return = self.hardware_manager.decommission(self.node,
                                                          self.ports)
        bios_mock.assert_called_with(self.node, self.ports)
        self.assertEqual(self.next_target, decom_return)

    def test_decommission_invalid_driver_info(self):
        self.node['driver_info'] = {}
        self.assertRaises(errors.DecommissionError,
                          self.hardware_manager.decommission,
                          self.node,
                          self.ports)

    def test_decommission_version_mismatch(self):
        self.hardware_manager.HARDWARE_MANAGER_VERSION = '2'
        self.node['driver_info']['decommission_target_state'] = None
        self.assertRaises(errors.WrongDecommissionVersion,
                          self.hardware_manager.decommission,
                          self.node,
                          self.ports)

    @mock.patch('ironic_python_agent.hardware._get_sorted_steps')
    def test_decommission_invalid_state(self, sorted_mock):
        sorted_mock.return_value = {}
        self.assertRaises(errors.DecommissionError,
                          self.hardware_manager.decommission,
                          self.node,
                          self.ports)

    @mock.patch('ironic_python_agent.hardware.GenericHardwareManager'
                '.get_decommission_steps')
    def test_decommission_invalid_function(self, steps_mock):
        self.decommission_steps[0]['function'] = 'not_update_bios'
        steps_mock.return_value = self.decommission_steps
        self.assertRaises(errors.DecommissionError,
                          self.hardware_manager.decommission,
                          self.node,
                          self.ports)

    @mock.patch('ironic_python_agent.hardware.GenericHardwareManager'
                '.update_bios')
    def test_decommission_function_error(self, bios_mock):
        bios_mock.side_effect = Exception
        self.assertRaises(errors.DecommissionError,
                          self.hardware_manager.decommission,
                          self.node,
                          self.ports)

    def test__get_next_target_state(self):
        next_step = self.hardware_manager._get_next_target_state(
            self.decommission_steps, self.decommission_steps[0], None)
        expected_next = {
            'decommission_next_state': 'update_firmware',
            'reboot_requested': False,
            'step_return_value': None,
            'hardware_manager_version': '1'
        }
        self.assertEqual(expected_next, next_step)

    def test__get_next_target_state_done(self):
        next_step = self.hardware_manager._get_next_target_state(
            self.decommission_steps, self.decommission_steps[2], None)
        expected_next = {
            'decommission_next_state': 'DONE',
            'reboot_requested': False,
            'step_return_value': None,
            'hardware_manager_version': '1'
        }
        self.assertEqual(expected_next, next_step)

    def test__get_sorted_steps(self):
        sorted_steps = hardware._get_sorted_steps(self.decommission_steps)
        self.assertEqual(self.decommission_steps, sorted_steps)

        unsorted_steps = [
            {
                'state': 'update_bios',
                'function': 'update_bios',
                'priority': 30,
                'reboot_requested': False,
            },
            {
                'state': 'update_firmware',
                'function': 'update_firmware',
                'priority': 20,
                'reboot_requested': False,
            },
            {
                'state': 'erase_hardware',
                'function': 'erase_hardware',
                'priority': 10,
                'reboot_requested': False,
            },
        ]
        expected_steps = [
            {
                'state': 'erase_hardware',
                'function': 'erase_hardware',
                'priority': 10,
                'reboot_requested': False,
            },
            {
                'state': 'update_firmware',
                'function': 'update_firmware',
                'priority': 20,
                'reboot_requested': False,
            },
            {
                'state': 'update_bios',
                'function': 'update_bios',
                'priority': 30,
                'reboot_requested': False,
            },
        ]
        sorted_steps = hardware._get_sorted_steps(unsorted_steps)
        self.assertEqual(expected_steps, sorted_steps)


class TestVerify(test_base.BaseTestCase):
    def setUp(self):
        super(TestVerify, self).setUp()
        # Truncated node object
        self.node = {
            'uuid': '8a2ff766-a28e-4bf2-aada-2c969ccf3398',
            'driver_info': {},
            'properties': {
                "memory_mb": 524288,
                "cpu_arch": "amd64",
                "local_gb": 32,
                "cpus": 12
            }
        }

        self.hardware_manager = hardware.GenericHardwareManager()
        # 32GB SSD
        self.disk = hardware.BlockDevice(
            '/dev/sda', 'super_duper_solid_state', 32 * 1024 * 1024 * 1024, 0)
        # 512 GB of RAM
        self.memory = hardware.Memory(549755813888)
        # 12 fast cores
        self.cpu = hardware.CPU('Intel Xeon E5-2630 v2', '2600.058', 12)
        self.interface = hardware.NetworkInterface('eth0', 'aa:bb:cc:dd:ee:ff')
        self.list_hardware = {
            'interfaces': [self.interface],
            'cpu': self.cpu,
            'disks': [self.disk],
            'memory': self.memory
        }

    @mock.patch('ironic_python_agent.hardware.GenericHardwareManager.'
                'get_os_install_device')
    @mock.patch('ironic_python_agent.hardware.HardwareManager.'
                'list_hardware_info')
    def test_verify_properties(self, list_mock, install_mock):
        list_mock.return_value = self.list_hardware
        install_mock.return_value = '/dev/sda'

        result = self.hardware_manager.verify_properties(self.node)
        self.assertIsNone(result)

    def test__verify_cpu_count_fail(self):
        self.node['properties']['cpus'] = 20
        self.assertRaises(
            errors.VerificationFailed,
            self.hardware_manager._verify_cpu_count,
            self.node['properties'],
            self.list_hardware)

    def test__verify_memory_size_fail(self):
        self.node['properties']['memory_mb'] = 32768
        self.assertRaises(
            errors.VerificationFailed,
            self.hardware_manager._verify_memory_size,
            self.node['properties'],
            self.list_hardware)

    @mock.patch('ironic_python_agent.hardware.GenericHardwareManager.'
                'get_os_install_device')
    def test__verify_disks_size_fail(self, install_mock):
        install_mock.return_value = '/dev/sda'
        self.node['properties']['local_gb'] = 10
        self.assertRaises(
            errors.VerificationFailed,
            self.hardware_manager._verify_disks_size,
            self.node['properties'],
            self.list_hardware)

    @mock.patch('ironic_python_agent.hardware.GenericHardwareManager.'
                'get_os_install_device')
    def test__verify_disks_size_no_name(self, install_mock):
        install_mock.return_value = '/dev/not_sda'
        self.assertRaises(
            errors.VerificationFailed,
            self.hardware_manager._verify_disks_size,
            self.node['properties'],
            self.list_hardware)
