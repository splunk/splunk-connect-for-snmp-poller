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

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import ConnectionFailure

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
            os.environ["MONGO_URI"],
        )
        if os.environ.get("MONGO_USER"):
            self._client.admin.authenticate(
                os.environ["MONGO_USER"], os.environ["MONGO_PASS"]
            )

        self._walked_hosts = self._client[mongo_config["database"]][
            mongo_config["walked_collection"]
        ]
        self._unwalked_hosts = self._client[mongo_config["database"]][
            mongo_config["unwalked_collection"]
        ]

    def is_connected(self):
        try:
            self._client.admin.command("ismaster")
            return True
        except ConnectionFailure:
            return False

    def contains_host(self, host):
        return self._walked_hosts.find({"_id": host}).count()

    def first_time_walk_was_initiated(self, host, flag_name):
        return self._walked_hosts.find({"_id": host, flag_name: True}).count()

    def add_host(self, host):
        try:
            self._walked_hosts.insert_one({"_id": host})
        except:  # noqa: E722
            logger.info(f"Id {host} already exists in MongoDB")

    def get_all_unwalked_hosts(self):
        return list(self._unwalked_hosts.find({}))

    def add_onetime_walk_result(self, host, version, community):
        logger.debug("Add host %s to unwalked_host collection", host)
        self._unwalked_hosts.insert_one(
            {
                "_id": host,
                "host": host,
                "version": version,
                "community": community,
            }
        )

    def delete_onetime_walk_result(self, host):
        logger.debug("Delete host %s from unwalked_host collection", host)
        self._unwalked_hosts.delete_one({"_id": host})

    def delete_host(self, host):
        logger.debug("Delete host %s from walked_host collection", host)
        self._walked_hosts.delete_one({"_id": host})

    def clear(self):
        self._walked_hosts.remove()

    def update_walked_host(self, host, element):
        logger.debug(f"Updating walked_hosts for host {host} with = {element}")
        self._walked_hosts.find_one_and_update(
            {"_id": host},
            {"$set": element},
            return_document=ReturnDocument.AFTER,
            upsert=True,
        )

    def real_time_data_for(self, host):
        full_collection = self._walked_hosts.find_one({"_id": host})
        if (
            full_collection
            and WalkedHostsRepository.MIB_REAL_TIME_DATA in full_collection
        ):
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

    # Input is what extract_network_interface_data_from_walk() returns
    def update_mib_static_data_for(self, host, existing_data, additional_data):
        if not existing_data and not additional_data:
            return
        for el in existing_data:
            for key, value in el.items():
                self.update_static_data_for_one_existing(host, "IF-MIB", key, value)
        if additional_data:
            self.update_static_data_for_one(host, additional_data)

    def update_static_data_for_one(self, host, static_data_dictionary):
        logger.info(f"Updating static data for {host} with {static_data_dictionary}")
        for oid_family in static_data_dictionary.keys():
            index_dict = static_data_dictionary[oid_family]
            if index_dict:
                self._walked_hosts.update(
                    {"_id": host},
                    {
                        "$set": {
                            f"MIB-STATIC-DATA.{oid_family}.{enricher_additional_varbinds}": index_dict
                        }
                    },
                    upsert=True,
                )

    def update_static_data_for_one_existing(
        self, host, oid_family, attribute, attribute_values
    ):
        self._walked_hosts.update(
            {"_id": host},
            {
                "$set": {
                    f"MIB-STATIC-DATA.{oid_family}.{enricher_existing_varbinds}.{attribute}": attribute_values
                }
            },
            upsert=True,
        )

    def delete_oidfamilies_from_static_data(self, host, oid_families):
        logger.info(f"Deleting oidfamilies {oid_families} from {host}")
        for oid_family in oid_families:
            self._walked_hosts.find_one_and_update(
                {"_id": host},
                {"$unset": {f"MIB-STATIC-DATA.{oid_family}": ""}},
            )

    def delete_all_static_data(self):
        self._walked_hosts.update_many(
            {},
            {"$unset": {"MIB-STATIC-DATA": ""}},
        )
