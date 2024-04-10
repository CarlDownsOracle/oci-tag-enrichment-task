#
# oci-tag-enrichment-task version 1.0.
#
# Copyright (c) 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.

import io
import json
import logging
import os
import oci
from functools import lru_cache
from fdk import response
from oci.config import from_file

# -------------------------------------------
# Configurable Variables
# -------------------------------------------

# This OCI Function Task is designed to enrich a given payload by retrieving and adding OCI tags associated
# with OCIDs present in the event.  The task by default will target all OCID keys present in payload.
# Optionally, you can specify a target list of OCID types to include.

include_all_ocids = eval(os.getenv('INCLUDE_TAGS_FOR_ALL_OCIDS', "True"))

# To target specific OCID keys, configure TARGET_OCID_KEYS with a comma-separated list of
# OCID keys (l-values).  The tags for each corresponding OCID, if present in the payload, will be
# retrieved and added.  The default value is a sampling of some well-known OCID keys but is by no means exhaustive.

target_ocid_keys = os.getenv('TARGET_OCID_KEYS', 'compartmentId vcnId subnetId vnicId vnicsubnetocid').split(' ')

# The default for TARGET_OCID_KEYS above is a superset of keys that will never all be present in any one
# event.  If False, TARGET_OCID_KEYS_WARN_IF_NOT_FOUND suppress log warnings for keys not found in
# the event payload.

target_ocid_keys_warn_if_not_found = eval(os.getenv('TARGET_OCID_KEYS_WARN_IF_NOT_FOUND', "False"))

# The TAG_ASSEMBLY_KEY is the l-value under which the tag collection will be added to the event payload.

tag_assembly_key = os.getenv('TAG_ASSEMBLY_KEY', 'tags')

# The TAG_POSITION_KEY is optional.  If defined, it tells us where in the event object to place the tag collection.

tag_position_key = os.getenv('TAG_POSITION_KEY', None)

# OCI supports 'freeform', 'defined' and 'system' tag types.  The INCLUDE parameters determine which tag types the
# function will include.  The INCLUDE_EMPTY_TAGS parameter determines whether empty 'freeform', 'defined' and 'system'
# tag dictionaries are to be included when empty.

include_freeform_tags = eval(os.getenv('INCLUDE_FREEFORM_TAGS', "True"))
include_defined_tags = eval(os.getenv('INCLUDE_DEFINED_TAGS', "True"))
include_system_tags = eval(os.getenv('INCLUDE_SYSTEM_TAGS', "True"))
include_empty_tags = eval(os.getenv('INCLUDE_EMPTY_TAGS', "False"))

# Set all registered loggers to the configured log_level

logging_level = os.getenv('LOGGING_LEVEL', 'INFO')
loggers = [logging.getLogger()] + [logging.getLogger(name) for name in logging.root.manager.loggerDict]
[logger.setLevel(logging.getLevelName(logging_level)) for logger in loggers]

# -------------------------------------------
# Function Entry Point & Helpers
# -------------------------------------------


def handler(ctx, data: io.BytesIO = None):
    """
    OCI Function Entry Point
    :param ctx: InvokeContext
    :param data: data payload
    :return: events with OCI tags added.
    """

    preamble = " {} / event count = {} / logging level = {}"

    try:
        payload = json.loads(data.getvalue())
        logging.getLogger().info(preamble.format(ctx.FnName(), len(payload), logging_level))
        add_tags_to_payload(payload)

        return response.Response(ctx,
                                 status_code=200,
                                 response_data=json.dumps(payload, indent=4),
                                 headers={"Content-Type": "application/json"})

    except (Exception, ValueError) as ex:
        logging.getLogger().error(f'error handling task function payload: {ex}')
        raise


def add_tags_to_payload(payload):
    """
    :param payload: payload is either a single event dictionary or a list of events.
    :return: the original payload (single event or list) with tags added.
    """

    if isinstance(payload, list):
        for event in payload:
            tag_collection = assemble_event_tags(event)
            position_tags_on_event(event, tag_collection)

    else:
        tag_collection = assemble_event_tags(payload)
        position_tags_on_event(payload, tag_collection)


def position_tags_on_event(event, tag_collection: dict):
    """
    Positions the tag collection object on the payload based on given rules.
    """

    # The 'tag_position_key' is optional.
    # If not empty, it tells us where in the nested payload to place the tag collection.
    # if position is found in the event and the position is a list or dictionary
    # that does not contain a 'tags' key, then add the collection there using 'tag_assembly_key' as the key.

    if tag_position_key:
        position = get_dictionary_value(event, tag_position_key)
        if position is not None:
            if isinstance(position, dict):
                if position.get(tag_assembly_key) is None:
                    position[tag_assembly_key] = tag_collection
                    return
            elif isinstance(position, list):
                position.append({tag_assembly_key: tag_collection})
                return
        else:
            raise RuntimeError(f'tag position noy found in payload / {tag_position_key}')

    # otherwise, default behavior is to add the collection
    # at the root of the payload.

    event[tag_assembly_key] = tag_collection


def assemble_event_tags(event: dict):
    """
    returns: assembly of all OCID tags as one dictionary (per config rules).
    """

    tag_assembly = {}

    tuple_list = assemble_ocid_list(event)
    for target_ocid in tuple_list:
        if tag_assembly.get(target_ocid) is not None:
            continue

        ocid_tags = retrieve_ocid_tags(target_ocid)
        tag_assembly[target_ocid] = ocid_tags

    logging.debug(f'tag_assembly / {tag_assembly}')
    return tag_assembly


def assemble_ocid_list(dictionary: dict, ocid_list=None):
    """
    recursively assembles a list of OCIDS from the payload dictionary based on configuration rules.
    """

    if ocid_list is None:
        ocid_list = []

    for key, value in dictionary.items():
        if isinstance(value, dict):
            assemble_ocid_list(dictionary=value, ocid_list=ocid_list)

        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    assemble_ocid_list(dictionary=entry, ocid_list=ocid_list)

        else:
            if isinstance(value, str) and value.startswith('ocid1.'):
                if include_all_ocids is True or key in target_ocid_keys:
                    ocid_list.append(value)

    return ocid_list


@lru_cache(maxsize=5000)
def retrieve_ocid_tags(target_ocid):
    """
    Retrieves the tags (if any) for the given target_ocid.
    Note that search results are LRU-cached for performance.
    """

    tag_object = {}
    if target_ocid is None:
        return tag_object

    logging.debug(f'searching / {target_ocid}')
    structured_search = oci.resource_search.models.StructuredSearchDetails(
            query="query all resources where identifier = '{}'".format(target_ocid),
            matching_context_type=oci.resource_search.models.SearchDetails.MATCHING_CONTEXT_TYPE_NONE,
            type='Structured')

    search_response = search_client.search_resources(structured_search)
    if hasattr(search_response, 'data'):

        resource_summary_collection = search_response.data
        for resource_summary in resource_summary_collection.items:

            if target_ocid != resource_summary.identifier:
                raise Exception(f'identifier mismatch / {target_ocid} / {resource_summary.identifier}')

            logging.debug(f'resource_summary / {resource_summary}')

            collect_tags(tag_object, 'freeform', include_freeform_tags, resource_summary.freeform_tags)
            collect_tags(tag_object, 'defined', include_defined_tags, resource_summary.defined_tags)
            collect_tags(tag_object, 'system', include_system_tags, resource_summary.system_tags)

    logging.debug(f'retrieved / ocid / {target_ocid} / tags / {tag_object}')
    return tag_object


def collect_tags(dictionary, tag_type_key, include_this_tag_type, results):
    """
    Adds the tag results to the dictionary based on configuration rules.
    """

    if include_this_tag_type is False:
        return

    if not results and include_empty_tags is False:
        return

    dictionary[tag_type_key] = results


def get_dictionary_value(dictionary: dict, target_key: str):
    """
    Recursive method to find value within a dictionary which may also have nested lists / dictionaries.
    If a target_key exists multiple times in the dictionary, the first one found will be returned.
    """

    if dictionary is None:
        raise Exception(f'dictionary is None / {target_key}')

    target_value = dictionary.get(target_key)
    if target_value is not None:
        return target_value

    for key, value in dictionary.items():
        if isinstance(value, dict):
            target_value = get_dictionary_value(dictionary=value, target_key=target_key)
            if target_value is not None:
                return target_value

        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    target_value = get_dictionary_value(dictionary=entry, target_key=target_key)
                    if target_value is not None:
                        return target_value


def local_test_mode(filename):
    """
    Processes a file of events locally / outside the OCI Fn system.
    """

    logging.info("local testing started")

    with open(filename, 'r') as f:
        contents = json.load(f)
        if isinstance(contents, dict):
            contents = [contents]

        add_tags_to_payload(contents)
        logging.info(json.dumps(contents, indent=4))

    logging.info("local testing completed")


if __name__ == "__main__":
    profile_name = os.getenv('OCI_CLI_PROFILE', "not_configured")
    configuration = from_file(profile_name=profile_name)
    search_client = oci.resource_search.ResourceSearchClient(config=configuration)
    local_test_mode('data/oci.metrics.json')
else:
    signer = oci.auth.signers.get_resource_principals_signer()
    search_client = oci.resource_search.ResourceSearchClient(config={}, signer=signer)
