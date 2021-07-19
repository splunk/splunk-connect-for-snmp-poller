#
# Copyright 2021 Splunk Inc.
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
#

from splunk_connect_for_snmp_poller.manager.realtime.oid_constant import OidConstant
from pysnmp.proto.rfc1902 import TimeTicks


class __RealTimeData:
    def __init__(self, element_type, element_value):
        self.element_type = element_type
        self.element_value = element_value

    def value(self):
        return self.element_value


def _device_probably_restarted(old_sysuptime, new_sysuptime):
    try:
        return TimeTicks(int(old_sysuptime.value())) > TimeTicks(
            int(new_sysuptime.value())
        )
    except ValueError:
        return False


""""
With virtualization becoming more and more common, we need some way of detecting when, for the same IP, a new device 
was redeployed. One common way of doing this is to analyze DISMAN-EVENT-MIB::sysUpTimeInstance. 
If its new value is less than the previous one, it probably means a device was re-deployed and the DHCP probably 
assigned it the same IP. In this case we need to re-do an SNMP WALK.

Parameters
----------
realtime_collection: dict
    This is a dictionary in the format {"OID": {"type": "your-oid-type", "value": "value as string"}, ... }
input_data_collection: dict
    This is a dictionary in the format {"OID": {"type": "your-oid-type", "value": "value as string"}, ... }
    
Returns
-------
True if both dictionaries have a "SYS_UP_TIME_INSTANCE" key, and the input_data_collection has a value that is
less than  realtime_collection. False otherwise.
"""


def _device_restarted(realtime_collection, input_data_collection):
    if OidConstant.SYS_UP_TIME_INSTANCE in realtime_collection:
        if OidConstant.SYS_UP_TIME_INSTANCE in input_data_collection:
            old_value = realtime_collection[OidConstant.SYS_UP_TIME_INSTANCE]
            old_rt_record = __RealTimeData(old_value["type"], old_value["value"])
            new_value = input_data_collection[OidConstant.SYS_UP_TIME_INSTANCE]
            new_rt_record = __RealTimeData(new_value["type"], new_value["value"])
            return _device_probably_restarted(old_rt_record, new_rt_record)
    return False


def should_redo_walk(realtime_collection, input_data):
    if realtime_collection and input_data:
        return _device_restarted(realtime_collection, input_data)
    else:
        return False
