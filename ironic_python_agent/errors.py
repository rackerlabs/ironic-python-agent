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

from ironic_python_agent import encoding


class RESTError(Exception, encoding.Serializable):
    """Base class for errors generated in ironic-python-client."""
    message = 'An error occurred'
    details = 'An unexpected error occurred. Please try back later.'
    status_code = 500
    serializable_fields = ('type', 'code', 'message', 'details')

    def __init__(self, *args, **kwargs):
        super(RESTError, self).__init__(*args, **kwargs)
        self.type = self.__class__.__name__
        self.code = self.status_code


class InvalidContentError(RESTError):
    """Error which occurs when a user supplies invalid content, either
    because that content cannot be parsed according to the advertised
    `Content-Type`, or due to a content validation error.
    """
    message = 'Invalid request body'
    status_code = 400

    def __init__(self, details):
        self.details = details


class NotFound(RESTError):
    """Error which occurs when a user supplies invalid content, either
    because that content cannot be parsed according to the advertised
    `Content-Type`, or due to a content validation error.
    """
    message = 'Not found'
    status_code = 404
    details = 'The requested URL was not found.'


class CommandExecutionError(RESTError):
    """Error raised when a command fails to execute."""

    message = 'Command execution failed'

    def __init__(self, details):
        super(CommandExecutionError, self).__init__()
        self.details = details


class InvalidCommandError(InvalidContentError):
    """Error which is raised when an unknown command is issued."""

    messsage = 'Invalid command'

    def __init__(self, details):
        super(InvalidCommandError, self).__init__(details)


class InvalidCommandParamsError(InvalidContentError):
    """Error which is raised when command parameters are invalid."""

    message = 'Invalid command parameters'

    def __init__(self, details):
        super(InvalidCommandParamsError, self).__init__(details)


class RequestedObjectNotFoundError(NotFound):
    def __init__(self, type_descr, obj_id):
        details = '{0} with id {1} not found.'.format(type_descr, obj_id)
        super(RequestedObjectNotFoundError, self).__init__(details)
        self.details = details


class IronicAPIError(RESTError):
    """Error raised when a call to the agent API fails."""

    message = 'Error in call to ironic-api.'

    def __init__(self, details):
        super(IronicAPIError, self).__init__(details)
        self.details = details


class HeartbeatError(IronicAPIError):
    """Error raised when a heartbeat to the agent API fails."""

    message = 'Error heartbeating to agent API.'

    def __init__(self, details):
        super(HeartbeatError, self).__init__(details)


class LookupNodeError(IronicAPIError):
    """Error raised when the node configuration lookup to the Ironic API
    fails.
    """

    message = 'Error getting configuration from Ironic.'

    def __init__(self, details):
        super(LookupNodeError, self).__init__(details)


class LookupAgentIPError(IronicAPIError):
    """Error raised when automatic IP lookup fails."""

    message = 'Error finding IP for Ironic Agent'

    def __init__(self, details):
        super(IronicAPIError, self).__init__(details)


class LookupAgentInterfaceError(IronicAPIError):
    """Error raised when agent interface lookup fails."""

    message = 'Error finding network interface for Ironic Agent'

    def __init__(self, details):
        super(IronicAPIError, self).__init__(details)


class ImageDownloadError(RESTError):
    """Error raised when an image cannot be downloaded."""

    message = 'Error downloading image.'

    def __init__(self, image_id, reason):
        super(ImageDownloadError, self).__init__()
        self.reason = reason
        self.details = 'Could not download image with id %s: %s' % (image_id,
                                                                    reason)


class ImageChecksumError(RESTError):
    """Error raised when an image fails to verify against its checksum."""

    message = 'Error verifying image checksum.'

    def __init__(self, image_id):
        super(ImageChecksumError, self).__init__()
        self.details = 'Image with id {0} failed to verify against checksum.'
        self.details = self.details.format(image_id)


class ImageWriteError(RESTError):
    """Error raised when an image cannot be written to a device."""

    message = 'Error writing image to device.'

    def __init__(self, device, exit_code, stdout, stderr):
        super(ImageWriteError, self).__init__()
        self.details = ('Writing image to device {0} failed with exit code '
                        '{1}. stdout: {2}. stderr: {3}')
        self.details = self.details.format(device, exit_code, stdout, stderr)


class ConfigDriveTooLargeError(RESTError):
    """Error raised when a configdrive is larger than the partition."""
    message = 'Configdrive is too large for intended partition.'

    def __init__(self, filename, filesize):
        details = ('Configdrive at {0} has size {1}, which is larger than '
                   'the intended partition.').format(filename, filesize)
        super(ConfigDriveTooLargeError, self).__init__(details)
        self.details = details


class ConfigDriveWriteError(RESTError):
    """Error raised when a configdrive directory cannot be written to a
    device.
    """

    message = 'Error writing configdrive to device.'

    def __init__(self, device, exit_code, stdout, stderr):
        details = ('Writing configdrive to device {0} failed with exit code '
                   '{1}. stdout: {2}. stderr: {3}.')
        details = details.format(device, exit_code, stdout, stderr)
        super(ConfigDriveWriteError, self).__init__(details)
        self.details = details


class SystemRebootError(RESTError):
    """Error raised when a system cannot reboot."""

    message = 'Error rebooting system.'

    def __init__(self, exit_code, stdout, stderr):
        super(SystemRebootError, self).__init__()
        self.details = ('Reboot script failed with exit code {0}. stdout: '
                        '{1}. stderr: {2}.')
        self.details = self.details.format(exit_code, stdout, stderr)


class BlockDeviceEraseError(RESTError):
    """Error raised when an error occurs erasing a block device."""

    message = 'Error erasing block device'

    def __init__(self, details):
        super(BlockDeviceEraseError, self).__init__(details)
        self.details = details


class BlockDeviceError(RESTError):
    """Error raised when a block devices causes an unknown error"""
    message = 'Block device caused unknown error'

    def __init__(self, details):
        super(BlockDeviceError, self).__init__(details)
        self.details = details


class VirtualMediaBootError(RESTError):
    """Error raised when booting ironic-python-client from virtual media
    fails.
    """
    message = 'Booting ironic-python-client from virtual media failed.'

    def __init__(self, details):
        super(RESTError, self).__init__(details)
        self.details = details


class WrongDecommissionVersion(RESTError):
    """Error raised when Ironic and the Agent have different versions."""
    message = 'Decommission version mismatch, reboot to new agent'

    def __init__(self, agent_version, node_version):
        self.status_code = 409
        self.details = ('Agent decommission version: {0}, node decommission '
                        'version: {1}')
        self.details = self.details.format(agent_version, node_version)
        self.agent_version = agent_version
        self.node_version = node_version


class ExtensionError(Exception):
    pass


class UnknownNodeError(Exception):
    """Error raised when the agent is not associated with an Ironic node."""

    message = 'Agent is not associated with an Ironic node.'

    def __init__(self, message=None):
        if message is not None:
            self.message = message
        super(UnknownNodeError, self).__init__(self.message)


class DecommissionError(RESTError):
    message = 'Agent failed to decommission.'

    def __init__(self, message):
        self.message = message
        super(DecommissionError, self).__init__(self.message)


class VerificationError(RESTError):
    def __init__(self, message):
        self.message = message
        super(VerificationError, self).__init__(self.message)


class VerificationFailed(VerificationError):
    def __init__(self, message):
        self.status_code = 409
        self.message = ('Verification failed because: %s' % message)
        super(VerificationFailed, self).__init__(self.message)
