#
# Copyright 2014 Rackspace
# All Rights Reserved
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
import socket

from ironic_python_agent.common import metrics
from oslo_config import cfg
from oslotest import base as test_base


CONF = cfg.CONF


class MockedMetricLogger(metrics.MetricLogger):
    _gauge = mock.Mock()
    _counter = mock.Mock()
    _timer = mock.Mock()
    _meter = mock.Mock()


class TestMetricLogger(test_base.BaseTestCase):
    def setUp(self):
        super(TestMetricLogger, self).setUp()
        self.ml = MockedMetricLogger('prefix', '.')
        self.ml_no_prefix = MockedMetricLogger([], '.')
        self.ml_list_prefix = MockedMetricLogger(['pre1', 'pre2', 'pre3'], '.')
        self.ml_other_delim = MockedMetricLogger('prefix', '*')

    def test_init(self):
        self.assertEqual(self.ml._prefix_parts, ['prefix'])
        self.assertEqual(self.ml._delimiter, '.')

        self.assertEqual(self.ml_no_prefix._prefix_parts, [])
        self.assertEqual(self.ml_list_prefix._prefix_parts,
                         ['pre1', 'pre2', 'pre3'])
        self.assertEqual(self.ml_other_delim._delimiter, '*')

    def test_get_metric_name(self):
        self.assertEqual(
            self.ml._getMetricName('metric'),
            'prefix.metric')

        self.assertEqual(
            self.ml._getMetricName(['part1', 'part2', 'part3']),
            'prefix.part1.part2.part3')

        self.assertEqual(
            self.ml_no_prefix._getMetricName('metric'),
            'metric')

        self.assertEqual(
            self.ml_no_prefix._getMetricName(['part1', 'part2', 'part3']),
            'part1.part2.part3')

        self.assertEqual(
            self.ml_list_prefix._getMetricName('metric'),
            'pre1.pre2.pre3.metric')

        self.assertEqual(
            self.ml_list_prefix._getMetricName(['part1', 'part2', 'part3']),
            'pre1.pre2.pre3.part1.part2.part3')

        self.assertEqual(
            self.ml_other_delim._getMetricName('metric'),
            'prefix*metric')

        self.assertEqual(
            self.ml_other_delim._getMetricName(['part1', 'part2', 'part3']),
            'prefix*part1*part2*part3')

    def test_gauge(self):
        self.ml.gauge('metric', 10)
        self.ml._gauge.assert_called_once_with('prefix.metric', 10)

    def test_counter(self):
        self.ml.counter('metric', 10)
        self.ml._counter.assert_called_once_with(
            'prefix.metric', 10,
            sample_rate=None)
        self.ml._counter.reset_mock()

        # TODO(Alex Weeks): Verify that sample_rates != 1.0 result in
        # probabilistic behavior as expected
        self.ml.counter('metric', 10, sample_rate=1.0)
        self.ml._counter.assert_called_once_with(
            'prefix.metric', 10,
            sample_rate=1.0)
        self.ml._counter.reset_mock()

        self.ml.counter('metric', 10, sample_rate=0.0)
        self.assertFalse(self.ml._counter.called)

        self.assertRaises(ValueError, self.ml.counter,
            'metric', 10, sample_rate=-0.1)
        self.assertRaises(ValueError, self.ml.counter,
            'metric', 10, sample_rate=1.1)

    def test_timer(self):
        self.ml.timer('metric', 10)
        self.ml._timer.assert_called_once_with('prefix.metric', 10)

    def test_meter(self):
        self.ml.meter('metric', 10)
        self.ml._meter.assert_called_once_with(
            'prefix.metric', 10)

    @mock.patch('ironic_python_agent.common.metrics.MetricLogger.timer')
    def test_instrument(self, mock_timer):

        @self.ml.instrument('foo', 'bar', 'baz')
        def func(x):
            return x * x

        func(10)

        mock_timer.assert_called_once_with(('foo', 'bar', 'baz'), mock.ANY)


class TestStatsdMetricLogger(test_base.BaseTestCase):
    def setUp(self):
        super(TestStatsdMetricLogger, self).setUp()
        self.ml = metrics.StatsdMetricLogger('prefix', '.', 'test-host', 4321)

    def test_init(self):
        self.assertEqual(self.ml._host, 'test-host')
        self.assertEqual(self.ml._port, 4321)
        self.assertEqual(self.ml._target, ('test-host', 4321))

    @mock.patch('ironic_python_agent.common.metrics.StatsdMetricLogger._send')
    def test_gauge(self, mock_send):
        self.ml._gauge('metric', 10)
        mock_send.assert_called_once_with('metric', 10, 'g')

    @mock.patch('ironic_python_agent.common.metrics.StatsdMetricLogger._send')
    def test_counter(self, mock_send):
        self.ml._counter('metric', 10)
        mock_send.assert_called_once_with('metric', 10, 'c', sample_rate=None)
        mock_send.reset_mock()

        self.ml._counter('metric', 10, sample_rate=1.0)
        mock_send.assert_called_once_with('metric', 10, 'c', sample_rate=1.0)

    @mock.patch('ironic_python_agent.common.metrics.StatsdMetricLogger._send')
    def test_timer(self, mock_send):
        self.ml._timer('metric', 10)
        mock_send.assert_called_once_with('metric', 10, 'ms')

    @mock.patch('ironic_python_agent.common.metrics.StatsdMetricLogger._send')
    def test_meter(self, mock_send):
        self.ml._meter('metric', 10)
        mock_send.assert_called_once_with('metric', 10, 'm')

    @mock.patch('socket.socket')
    def test_open_socket(self, mock_socket_constructor):
        self.ml._open_socket()
        mock_socket_constructor.assert_called_once_with(
            socket.AF_INET,
            socket.SOCK_DGRAM)

    @mock.patch('socket.socket')
    def test_send(self, mock_socket_constructor):
        mock_socket = mock.Mock()
        mock_socket_constructor.return_value = mock_socket

        self.ml._send('part1.part2', 2, 'type')
        mock_socket.sendto.assert_called_once_with(
            'part1.part2:2|type',
            ('test-host', 4321))
        mock_socket.close.assert_called_once_with()
        mock_socket.reset_mock()

        self.ml._send('part1.part2', 3.14159, 'type')
        mock_socket.sendto.assert_called_once_with(
            'part1.part2:3.14159|type',
            ('test-host', 4321))
        mock_socket.close.assert_called_once_with()
        mock_socket.reset_mock()

        self.ml._send('part1.part2', 5, 'type')
        mock_socket.sendto.assert_called_once_with(
            'part1.part2:5|type',
            ('test-host', 4321))
        mock_socket.close.assert_called_once_with()
        mock_socket.reset_mock()

        self.ml._send('part1.part2', 5, 'type', sample_rate=0.5)
        mock_socket.sendto.assert_called_once_with(
            'part1.part2:5|type@0.5',
            ('test-host', 4321))
        mock_socket.close.assert_called_once_with()


class TestGetLogger(test_base.BaseTestCase):
    def setUp(self):
        super(TestGetLogger, self).setUp()

    def config(self, **kw):
        """Override config options for a test."""
        group = kw.pop('group', None)
        for k, v in kw.iteritems():
            CONF.set_override(k, v, group)

    def test_default_backend(self):
        self.config(backend='noop',
                    group='metrics')
        logger = metrics.getLogger('foo')
        self.assertIsInstance(logger, metrics.NoopMetricLogger)

    def test_statsd_backend(self):
        self.config(backend='statsd',
                    group='metrics')

        logger = metrics.getLogger('foo')
        self.assertIsInstance(logger, metrics.StatsdMetricLogger)

    def test_config_opts(self):
        self.config(host='test')
        self.config(prepend_host=True, group='metrics')
        self.config(prepend_host_reverse=True, group='metrics')
        self.config(global_prefix='test', group='metrics')
        self.config(backend='statsd', group='metrics')

        logger = metrics.getLogger('foo')
        self.assertIsInstance(logger, metrics.StatsdMetricLogger)
