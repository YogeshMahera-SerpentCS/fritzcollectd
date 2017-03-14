# fritzcollectd - FRITZ!Box collectd plugin
# Copyright (c) 2014-2017 Christian Fetzer
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

""" Tests for fritzcollectd """

import collections
import sys

import mock

from nose.tools import with_setup


class CollectdMock(object):
    """ Mocks the collectd object that is injected into plugins when
        collectd loads them. This allows to use the fritzcollectd module
        independently from collectd. """

    def __init__(self):
        self._cb_init = None
        self._cb_config = None
        self._cb_read = None
        self._cb_shutdown = None
        self.values = []
        self.warning = mock.Mock()

    def reset_mock(self):
        """ Reset values and mock calls. Must be called for every test. """
        del self.values[:]
        self.warning.reset_mock()

    def register_config(self, cb_config):
        """ Plugins are required to register a configuration callback. The
            callback is called when the plugin configuration is loaded. """
        self._cb_config = cb_config

    def register_init(self, cb_init):
        """ Plugins are required to register an initialization callback. The
            callback is called when a plugin is loaded. """
        self._cb_init = cb_init

    def register_read(self, cb_read):
        """ Plugins are required to register a read callback. The callback is
            called periodically to read data. """
        self._cb_read = cb_read

    def register_shutdown(self, cb_shutdown):
        """ Plugins can register a shutdown callback. The callback is called
            when collectd shuts down. """
        self._cb_shutdown = cb_shutdown

    def process(self, config=None):
        """ Simulates collectd. Call callbacks once. """
        if config is None:
            config = CollectdConfig()
        try:
            self._cb_config(config)
            self._cb_init()
            self._cb_read()
        finally:
            self._cb_shutdown()

    def Values(self):  # pylint: disable=invalid-name
        """ Plugins call this in their read callback in order to report
            measurements to collectd. """
        return CollectdValues(self)


class CollectdConfig(object):  # pylint: disable=too-few-public-methods
    """ Config element passed to the collectd configuration callback. """

    def __init__(self, config=None):
        if config is None:
            self._config = {}
        else:
            self._config = config

    def __str__(self):
        return str(self.children)

    @property
    def children(self):
        """ Property passed to the collectd configuration callback. """
        node = collections.namedtuple('Node', ['key', 'values'])
        return [node(key=k, values=[v]) for k, v in self._config.items()]


class CollectdValues(object):  # pylint: disable=too-few-public-methods
    """ Represents a container class in which plugins can report
        measurements to collectd. """

    def __init__(self, collectd_mock):
        self.host = ''
        self.plugin = ''
        self.plugin_instance = ''
        self.type = ''
        self.type_instance = ''
        self.values = []
        self._collectd_mock = collectd_mock

    def __repr__(self):
        return 'Values({}, {}, {})'.format(
            self.type, self.type_instance, self.values[0])

    def dispatch(self):
        """ Dispatch measurements to collectd. """
        self._collectd_mock.values.append(self)


class FritzConnectionMock(object):  # pylint: disable=too-few-public-methods
    """ Mock for fritzconnection so that the fritzcollectd module can be used
        without a real router in unit tests. The mock is default configured
        to support the normal (good case) tests. """

    FRITZBOX_DATA = {
        ('WANIPConnection', 'GetStatusInfo'):
        {'NewConnectionStatus': 'Connected',
         'NewUptime': 35307},
        ('WANCommonInterfaceConfig', 'GetCommonLinkProperties'):
        {'NewLayer1DownstreamMaxBitRate': 10087000,
         'NewLayer1UpstreamMaxBitRate': 2105000,
         'NewPhysicalLinkStatus': 'Up'},
        ('WANCommonInterfaceConfig', 'GetAddonInfos'):
        {'NewByteSendRate': 3438,
         'NewByteReceiveRate': 67649,
         'NewTotalBytesSent': 1712232562,
         'NewTotalBytesReceived': 5221019883},
        ('LANEthernetInterfaceConfig', 'GetStatistics'):
        {'NewBytesSent': 23004321,
         'NewBytesReceived': 12045}
    }

    MODELNAME = 'FRITZ!Box 7490'

    def __init__(self):
        type(self).modelname = mock.PropertyMock(return_value=self.MODELNAME)
        self.call_action = mock.Mock(side_effect=self._side_effect_callaction)

    def _side_effect_callaction(self, service, action):
        return self.FRITZBOX_DATA[(service, action)]


# Instantiate mock so that tests can be executed without collectd.
MOCK = CollectdMock()
sys.modules['collectd'] = MOCK
import fritzcollectd  # noqa, pylint: disable=unused-import, wrong-import-position


@mock.patch('fritzconnection.FritzConnection', autospec=True)
@with_setup(teardown=MOCK.reset_mock)
def test_basic(fc_class_mock):
    """ Basic test with default configuration. """
    fc_class_mock.return_value = FritzConnectionMock()

    MOCK.process()
    assert len(MOCK.values) > 0


@mock.patch('fritzconnection.FritzConnection', autospec=True)
@with_setup(teardown=MOCK.reset_mock)
def test_configuration(fc_class_mock):
    """ Test if configuration parameters have the intended behavior. """
    config = CollectdConfig({'Address': 'localhost', 'Port': 1234,
                             'User': 'user', 'Password': 'password',
                             'Hostname': 'hostname', 'Instance': 'instance',
                             'UNKNOWN': 'UNKNOWN'})
    fc_class_mock.return_value = FritzConnectionMock()

    MOCK.process(config)
    fc_class_mock.assert_has_calls(
        [mock.call(address='localhost', password='password',
                   port=1234, user='user')])
    assert MOCK.warning.called
    assert len(MOCK.values) > 0
    assert MOCK.values[0].host == 'hostname'
    assert MOCK.values[0].plugin_instance == 'instance'
