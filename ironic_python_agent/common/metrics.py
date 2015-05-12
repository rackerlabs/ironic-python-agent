# Copyright 2014 Rackspace Hosting
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
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

import abc
import random
import six
import socket
import time

import contextlib
import functools
from oslo.config import cfg
from oslo_log import log

metrics_opts = [
    cfg.StrOpt('backend',
               default='noop',
               help='Backend to use for the metrics system.'),
    cfg.BoolOpt('prepend_host',
                default=False,
                help='Prepend the value of CONF.host to all metric names '
                     '(after the global_prefix).'),
    cfg.BoolOpt('prepend_host_reverse',
                default=True,
                help='Split the prepended host value by "." and reverse it '
                '(to better match the reverse hierarchical form of domain '
                'names).'),
    cfg.BoolOpt('prepend_uuid',
                default=False,
                help='Prepend the node\'s Ironic UUID to all metric names '
                     '(after the global_prefix).'),
    cfg.StrOpt('global_prefix',
               default='',
               help='Prefix all metric names with this value (before the'
                    'host, if prepend_host is set).'),
    cfg.StrOpt('statsd_host',
               default='localhost',
               help='Host for use with the statsd backend.'),
    cfg.IntOpt('statsd_port',
               default=8125,
               help='Port to use with the statsd backend.')
    ]

LOG = log.getLogger(__name__)

CONF = cfg.CONF
CONF.register_opts(metrics_opts, group='metrics')


@six.add_metaclass(abc.ABCMeta)
class MetricLogger(object):
    """Abstract class representing a metrics logger."""

    def __init__(self, prefix_parts, delimiter):
        if isinstance(prefix_parts, basestring):
            self._prefix_parts = [prefix_parts]
        else:
            self._prefix_parts = list(prefix_parts)

        self._delimiter = delimiter

    def _getMetricName(self, m_parts):
        if isinstance(m_parts, basestring):
            m_parts = [m_parts]

        return self._delimiter.join(self._prefix_parts + list(m_parts))

    def gauge(self, m_parts, m_value):
        """Send gauge metric data."""
        self._gauge(self._getMetricName(m_parts), m_value)

    def counter(self, m_parts, m_value, sample_rate=None):
        """Send counter metric data.

        Optionally, specify sample_rate in the interval [0.0, 1.0] to
        sample data probabilistically where:

            P(send metric data) = sample_rate

        If sample_rate is None, then always send metric data, but do not
        have the backend send sample rate information (if supported).
        """
        if (sample_rate is not None
                and sample_rate < 0.0
                or sample_rate > 1.0):
            raise ValueError("sample_rate must be None, or in the interval "
                             "[0.0, 1.0]")

        if sample_rate is None or random.random() < sample_rate:
            return self._counter(self._getMetricName(m_parts) + '.counter',
                                 m_value, sample_rate=sample_rate)

    def timer(self, m_parts, m_value):
        """Send timer data."""
        self._timer(self._getMetricName(m_parts), m_value)

    def meter(self, m_parts, m_value):
        """Send meter data."""
        self._meter(self._getMetricName(m_parts), m_value)

    @abc.abstractmethod
    def _gauge(self, m_parts, m_value):
        """Abstract method for backends to implement gauge behavior."""

    @abc.abstractmethod
    def _counter(self, m_parts, m_value, sample_rate=None):
        """Abstract method for backends to implement counter behavior."""

    @abc.abstractmethod
    def _timer(self, m_parts, m_value):
        """Abstract method for backends to implement timer behavior."""

    @abc.abstractmethod
    def _meter(self, m_parts, m_value):
        """Abstract method for backends to implement meter behavior."""

    def instrument(self, *parts):
        """Returns a decorator that instruments a function, bound to this
        MetricLogger.  For example:

        from ironic_python_agent.common import metrics

        METRICS = metrics.getLogger()

        @METRICS.instrument('foo')
        def foo(bar, baz):
            print bar, baz
        """
        def decorator(f):
            @functools.wraps(f)
            def wrapped(*args, **kwargs):
                start = time.time()
                result = f(*args, **kwargs)
                duration = (time.time() - start) * 1000

                # Log the timing data
                self.timer(parts, duration)
                return result
            return wrapped
        return decorator


class NoopMetricLogger(MetricLogger):
    """Noop metric logger that throws away all metric data."""

    def __init__(self, prefix, delimiter):
        super(NoopMetricLogger, self).__init__(prefix, delimiter)

    def _gauge(self, m_name, m_value):
        pass

    def _counter(self, m_name, m_value, sample_rate=None):
        pass

    def _timer(self, m_name, m_value):
        pass

    def _meter(self, m_name, m_value):
        pass


class StatsdMetricLogger(MetricLogger):
    """Metric logger that reports data via the statsd protocol."""

    GAUGE_TYPE = 'g'
    COUNTER_TYPE = 'c'
    TIMER_TYPE = 'ms'
    METER_TYPE = 'm'

    def __init__(self, prefix_parts, delimiter,
                 host=CONF.metrics.statsd_host,
                 port=CONF.metrics.statsd_port):
        """Initialize a StatsdMetricLogger with the given prefix list,
        delimiter, host, and port.
        """
        super(StatsdMetricLogger, self).__init__(prefix_parts, delimiter)

        self._host = host
        self._port = port

        self._target = (self._host, self._port)

    def _send(self, m_name, m_value, m_type, sample_rate=None):
        if sample_rate is None:
            metric = '%s:%s|%s' % (m_name, m_value, m_type)
        else:
            metric = '%s:%s|%s@%s' % (m_name, m_value, m_type, sample_rate)

        LOG.info('statsd: sending %(metric)s to %(target)s' %
                 {'metric': metric, 'target': self._target})

        # Ideally, we'd cache a sending socket in self, but that
        # results in a socket getting shared by multiple green threads.
        with contextlib.closing(self._open_socket()) as sock:
            return sock.sendto(metric, self._target)

    def _open_socket(self):
        return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def _gauge(self, m_name, m_value):
        return self._send(m_name, m_value, self.GAUGE_TYPE)

    def _counter(self, m_name, m_value, sample_rate=None):
        return self._send(m_name, m_value, self.COUNTER_TYPE,
                          sample_rate=sample_rate)

    def _timer(self, m_name, m_value):
        return self._send(m_name, m_value, self.TIMER_TYPE)

    def _meter(self, m_name, m_value):
        return self._send(m_name, m_value, self.METER_TYPE)


class InstrumentContext(object):
    """Metrics instrumentation context manager"""
    def __init__(self, prefix, *parts):
        self.logger = getLogger(prefix)
        self.parts = parts

    def __enter__(self):
        self.start_time = time.time()
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (time.time() - self.start_time) * 1000
        # Log the timing data
        self.logger.timer(self.parts, duration)


def instrument(prefix, *parts):
    """Returns a decorator that instruments a function

    For example:

    from ironic_python_agent.common import metrics

    @metrics.instrument(__name__, 'foo')
    def foo(bar, baz):
        print bar, baz
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            start = time.time()
            result = f(*args, **kwargs)
            duration = (time.time() - start) * 1000

            # Delay getting the logger so we can dynamically configure metrics
            logger = getLogger(prefix)
            # Log the timing data
            logger.timer(parts, duration)
            return result
        return wrapped
    return decorator


def instrument_context(prefix, *parts):
    """Returns a context manager that instruments a function

    For example:

    from ironic_python_agent.common import metrics

    with metrics.instrument_context(__name__, 'foo'):
        foo(bar, baz)
    """
    return InstrumentContext(prefix, '.'.join(parts))


def getLogger(prefix):
    """Return a metric logger with the specified prefix."""
    if isinstance(prefix, basestring):
        prefix = [prefix]

    if CONF.metrics.prepend_host:
        host = CONF.host

        if CONF.metrics.prepend_host_reverse:
            host = '.'.join(reversed(host.split('.')))

        prefix = [host] + prefix

    if CONF.metrics.prepend_uuid:
        prefix = [CONF.node_uuid] + prefix

    if CONF.metrics.global_prefix:
        prefix = [CONF.metrics.global_prefix] + prefix

    if CONF.metrics.backend == 'statsd':
        return StatsdMetricLogger(prefix, '.',
                                  host=CONF.metrics.statsd_host,
                                  port=CONF.metrics.statsd_port)
    else:
        return NoopMetricLogger(prefix, '.')


def set_config(config):
    """Modify config opts with external opts

    Allows the conductor to modify the metrics config when agent does the
    lookup call to the conductor.
    """
    for opt, val in config.items():
        setattr(CONF.metrics, opt, val)
