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
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
import logging
import os
from collections import defaultdict

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import ConnectionFailure

from splunk_connect_for_snmp_poller.manager.realtime.interface_mib import InterfaceMib

from .manager.variables import enricher_additional_varbinds, enricher_existing_varbinds

logger = logging.getLogger(__name__)

"""
In order to store some general data into Mongo we use the following structure.
Each WalkedHostsRepository can contain the following fields:
* _id: a unique key that represents a concrete host (always present)
* MIB-STATIC-DATA: a dictionary that contains some required-MIB data for further processing. For example, when
  enriching the OIDs related to network interfaces, as part of the intial walk for a given host we plan to store
  in this dictionary -at least- the following information:
  "MIB-STATIC-DATA": {              <----- GENERAL STATIC MIB DATA
    "IF-MIB": {                     <----- NETWORK INTERFACES DATA
      "ifNumber": 2,                <----- TOTAL NUMBER OF NETWORK INTERFACES
      "ifIndex": [1, 2],            <----- INDEX MAPPING FOR OIDs
      "ifDescr": ["lo", "eth0"],    <----- INDEX MAPPING FOR OIDs (IF-MIB*.1 -> "lo", IF-MIB*.2 -> "eth0", ...)
    }
  }

  For example:
  IF-MIB::ifNumber.0 = INTEGER: 2
  IF-MIB::ifIndex.1 = INTEGER: 1
  IF-MIB::ifIndex.2 = INTEGER: 2
  IF-MIB::ifDescr.1 = STRING: lo
  IF-MIB::ifDescr.2 = STRING: eth0
  IF-MIB::ifType.1 = INTEGER: softwareLoopback(24)
  IF-MIB::ifType.2 = INTEGER: ethernetCsmacd(6)
  IF-MIB::ifPhysAddress.1 = STRING:
  IF-MIB::ifPhysAddress.2 = STRING: 0:12:79:62:f9:40
  IF-MIB::ifAdminStatus.1 = INTEGER: up(1)
  IF-MIB::ifAdminStatus.2 = INTEGER: up(1)

* MIB_REAL_TIME_DATA: a dictionary that contains some MIB real-time data that needs to be collected constantly.
  At the moment, we only need to collect sysUpTimeInstance data in order to decide when we need to re-walk
  a given host.
"""


class WalkedHostsRepository:
    MIB_REAL_TIME_DATA = "MIB-REAL-TIME-DATA"
    MIB_STATIC_DATA = "MIB-STATIC-DATA"

    def __init__(self, mongo_config):
        self._client = MongoClient(
            os.environ["MONGO_SERVICE_SERVICE_HOST"],
            int(os.environ["MONGO_SERVICE_SERVICE_PORT"]),
        )
        if os.environ.get("MONGO_USER"):
            self._client.admin.authenticate(
                os.environ["MONGO_USER"], os.environ["MONGO_PASS"]
            )

        self._walked_hosts = self._client[mongo_config["database"]][
            mongo_config["collection"]
        ]

    def is_connected(self):
        try:
            self._client.admin.command("ismaster")
            return True
        except ConnectionFailure:
            return False

    def contains_host(self, host):
        return self._walked_hosts.find({"_id": host}).count()

    def add_host(self, host):
        self._walked_hosts.insert_one({"_id": host})

    def delete_host(self, host):
        logger.debug("Delete host %s from walked_host collection", host)
        self._walked_hosts.delete_one({"_id": host})

    def clear(self):
        self._walked_hosts.remove()

    def real_time_data_for(self, host):
        full_collection = self._walked_hosts.find_one({"_id": host})
        if WalkedHostsRepository.MIB_REAL_TIME_DATA in full_collection:
            return full_collection[WalkedHostsRepository.MIB_REAL_TIME_DATA]
        else:
            return None

    def static_data_for(self, host):
        full_collection = self._walked_hosts.find_one({"_id": host})
        if not full_collection:
            logger.debug("No id %s in walked_host collection", host)
            return None
        if WalkedHostsRepository.MIB_STATIC_DATA in full_collection:
            mib_static_data = full_collection[WalkedHostsRepository.MIB_STATIC_DATA]
            return mib_static_data
        else:
            return None

    def update_real_time_data_for(self, host, input_dictionary):
        if input_dictionary:
            real_time_data_dictionary = {
                WalkedHostsRepository.MIB_REAL_TIME_DATA: input_dictionary
            }
            self._walked_hosts.find_one_and_update(
                {"_id": host},
                {"$set": real_time_data_dictionary},
                return_document=ReturnDocument.AFTER,
            )

    def create_mib_static_data_mongo_structure(self, existing_data, additional_data):
        """
        This function creates database mib static data structure out of existing_data and additional_data provided
        from config.yaml and the data derived from SNMP Walk, for ex.:
        existing_data = [{'interface_index': ['1', '2']}, {'interface_desc': ['lo', 'eth0']}]
        additional_data = {'IF-MIB': {'indexNum': 'index_num'}, 'SNMPv2-MIB': {'indexNum': 'index_num'}}

        Returned structure should look like this:
        { "MIB-STATIC-DATA": {
            {'IF-MIB':
                        {'existingVarBinds': [{'interface_index': ['1', '2']}, {'interface_desc': ['lo', 'eth0']}],
                        'additionalVarBinds': {'indexNum': 'index_num'}},
            'SNMPv2-MIB':
                        {'additionalVarBinds': {'indexNum': 'index_num'}}
            }
        }
        """
        static_data_dictionary = {"MIB-STATIC-DATA": defaultdict(dict)}
        static_data_dictionary_mib = static_data_dictionary["MIB-STATIC-DATA"]
        if existing_data:
            static_data_dictionary_mib[InterfaceMib.IF_MIB_DATA_MONGO_IDENTIFIER][
                enricher_existing_varbinds
            ] = existing_data
        for el in additional_data.keys():
            static_data_dictionary_mib[el][
                enricher_additional_varbinds
            ] = additional_data[el]
        return static_data_dictionary

    # Input is what extract_network_interface_data_from_walk() returns
    def update_mib_static_data_for(self, host, existing_data, additional_data):
        if not existing_data and not additional_data:
            return
        static_data_dictionary = self.create_mib_static_data_mongo_structure(
            existing_data, additional_data
        )
        self._walked_hosts.find_one_and_update(
            {"_id": host},
            {"$set": static_data_dictionary},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return static_data_dictionary["MIB-STATIC-DATA"]
