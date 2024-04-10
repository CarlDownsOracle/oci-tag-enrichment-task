# Enriching Log and Metric Event Payloads with OCI Tags

---

### Why are Tags not Present on Log and Metric Events?

OCI supports a robust [Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm) 
feature that allows customers to tag provisioned objects as needed to meet virtually any business use case.
However, most OCI services don't include OCI tags when they emit logs
and metrics to [Logging](https://docs.oracle.com/en-us/iaas/Content/Logging/home.htm) and 
[Monitoring](https://docs.oracle.com/en-us/iaas/Content/Monitoring/home.htm) 
because including tags would be expensive, adversely impacting storage and bandwidth usage.

### Observability Correlation Use Cases

Many customer use cases, however, call for a way to map log and metric events to business objects so 
that downstream Observability systems can perform required correlative analyses.  Thus, they need
events with tags included.

### Solution Brief

This sample solves that problem through the use of
[OCI Service Connector Function Tasks](https://docs.oracle.com/en-us/iaas/Content/connector-hub/overview.htm). 
The sample Function Task "enriches" an event by selectively retrieving and adding tags to each as 
the Service Connector processes them. 

See [OCI Service Connector Overview](https://docs.oracle.com/en-us/iaas/Content/connector-hub/overview.htm) for 
a thorough explanation of Functions Tasks.

![](images/sch-functions-task.png)

----


## Functions Primer

If you’re new to Functions, get familiar by running through 
the [Quick Start guide on OCI Functions](http://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsquickstartguidestop.htm) before proceeding.


## IAM Setup

### OCI Compartment

For illustration purposes, we will define a compartment with the name `tag-enrichment-comp`.


### OCI Policy

Since the functions task uses the OCI SDK to retrieve tags, it will need permissions to do so.  

#### Dynamic Group

Functions are resources in OCI IAM parlance, do we need to set up a dynamic group called `tag-enrichment-dynamic-group` 
that includes function resources in the compartment.  The OCID should be the one corresponding to `tag-enrichment-comp`.

```
resource.compartment.id = 'ocid1.compartment.oc1....'
```

#### Policies

Next we need to grant the task the ability to search the various types of OCI resources we have in our use case.
In the below example, some sample permissions are present as a guide.  For example, your function may need to 
retrieve the tags for VCNs, subnets, buckets and objects in `tag-enrichment-comp`, or it may need to get tags for 
any resource in the compartment.  Adjust this as needed for your use case.

```
Allow dynamic-group tag-enrichment-dynamic-group to use tag-namespaces in compartment tag-enrichment-comp
Allow dynamic-group tag-enrichment-dynamic-group to manage object-family in compartment tag-enrichment-comp
Allow dynamic-group tag-enrichment-dynamic-group to manage virtual-network-family in compartment tag-enrichment-comp
Allow dynamic-group tag-enrichment-dynamic-group to manage all-resources in compartment tag-enrichment-comp
Allow dynamic-group tag-enrichment-dynamic-group to manage compartments in compartment tag-enrichment-comp
```

## Function Setup

See the [Quick Start guide on OCI Functions](http://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsquickstartguidestop.htm) reference.
This task supports a number of configuration options (see below).


### Selecting Target OCIDs

The default behavior is to collect and attach all tags for all OCIDs present in an event payload.
The `INCLUDE_TAGS_FOR_ALL_OCIDS` configuration parameter controls this.

If you only want to target specific OCID keys to retrieve, set `INCLUDE_TAGS_FOR_ALL_OCIDS` == `False` and define the list 
of `TARGET_OCID_KEYS` to search for in the event payloads. Set the `TARGET_OCID_KEYS` to a comma-separated 
list of OCID keys (l-values in the payload) to include.  The delimiters separating OCID keys must
be **commas only ... no spaces!** Finally, the default `TARGET_OCID_KEYS` values are just examples
that you will want to change.


### What about Nested Payloads?

Target OCIDs can exist anywhere in the event payload, and will be found regardless of nested position.

### What about Performance?

The results are cached when retrieved within the Function container using an LRU cache.

### Function Testing

Once you have the Fn Application created, Function built and deployed to the Application, we can perform some tests
from the cloud shell without having to set up a Service Connector.

Add a freeform tag to the VCN you created for the Fn Application.  An example freeform tag:

    "app-test": "working" 

We will invoke the function by passing it a simulated event payload that looks like this:

    {
      "vcnId": "ocid1.vcn.oc1.iad...."
    }

Now let's invoke the Function from the directory in cloud shell where the function code is located, 
passing in a simulated 'event' payload like so:

    echo -n '{"vcnId":"your-vcn-id-goes-here"}' | fn invoke tag-enrichment-app oci-tag-enrichment-task

You should see the same payload returned with `tags` collection added ... something like this:

    {
        "vcnId": "ocid1.vcn.oc1.iad....",
        "tags": {
            "ocid1.vcn.oc1.iad....": {
                "freeform": {
                    "VCN": "VCN-2024-03-01T20:57:32"
                    "app-test": "working"
                }
            }
        }
    }

### Changing the Assembly Key

The l-value _tags_ can be changed.  Simply set `TAG_ASSEMBLY_KEY` to name it whatever you like.

### Changing Placement in the Payload 

If you want to position the tag collection somewhere other than at the top, you can set `TAG_POSITION_KEY`.
If the `TAG_POSITION_KEY` position in your payload is a dictionary, the tag collection will be 
added using `TAG_ASSEMBLY_KEY` as the position.  

As an example, let's assume we have defined function configuration `TAG_POSITION_KEY` as `"compliance"`.   Now simulate
a call with a payload that has that position in it, declared as an object:

    echo -n '{"vcnId":"your-vcn-id-goes-here", "compliance": {}}' | fn invoke tag-enrichment-app oci-tag-enrichment-task

So, this is what you get back when positioning within an existing object:
    
    {
        "vcnId": "ocid1.vcn.oc1.iad....",
        "compliance": {
            "tags": {
                "ocid1.vcn.oc1.iad....": {
                    "freeform": {
                        "VCN": "VCN-2024-03-01T20:57:32"
                        "app-test": "working"
                    }
                }
            }
        }
    }

If the `TAG_POSITION_KEY` position is an array, then the tag collection is added as an object to the list. 
Here is an example of positioning within as existing array:

    echo -n '{"vcnId":"your-vcn-id-goes-here", "compliance": ["something"]}' | fn invoke tag-enrichment-app oci-tag-enrichment-task

... yields this result:

    {
        "vcnId": "ocid1.vcn.oc1.iad....",
        "compliance": [
            "something",
            {
                "tags": {
                    "ocid1.vcn.oc1.iad....": {
                        "freeform": {
                            "VCN": "VCN-2024-03-01T20:57:32"
                            "app-test": "working"
                        }
                    }
                }
            }
        ]
    }

If the `TAG_POSITION_KEY` position l-value is missing from the payload, an error is thrown.


## Service Connector Setup

As a sample test scenario, let's write tag-enriched `VCN Flow Logs` to an `Object Storage Bucket`.


![](images/sch-mapping.png)

**Configure VCN Tags**
* Just use the VCN that the Function App requires.
* Add freeform or defined tags to the subnets on your VCN in `tag-enrichment-comp`.

**Configure VCN Flow Logs**
* Enable VCN Flow logs for the VCN in `tag-enrichment-comp`.

**Configure Task**
* VCN Flow Logs include a `vnicsubnetocid` OCID key.  That exists by default in `TARGET_OCID_KEYS`.

**Create Object Storage**
* Create a bucket in `tag-enrichment-comp`.

**Create Service Connector**
* Create a service connector instance in `tag-enrichment-comp`.
* Configure it to:
  * Select VCN Flow Logs as Source
  * Select Functions Task and point to this Task Function
  * Select Object Storage as Target

_NOTE: BE SURE TO ACCEPT THE POLICY UPDATES THE SERVICE CONNECTOR DIALOG OFFERS YOU!_

## Troubleshooting

### Enable Fn Application Invocation Logs

If you are getting an unexpected behavior, enable the function invocation logs for the Function App.  
Then set `LOGGING_LEVEL` == `DEBUG` to have the function write full debugging output to that log.

### Task function is timing out

You can reduce the amount of work passed to the Task Function to resolve this. Edit the Task portion of 
the Service Connector, click `Show additional options` and then `Use manual settings`. Set `Batch size limit (KBs)` 
to a smaller number to reduce the batch size.  Conversely, you can extend the time limit by 
increasing `Batch time limit (seconds)`.

### Task function is not adding any tags

The function must have `resource principal` permissions granted to it in order to successfully
retrieve tags for a given Object.  See Dynamic Group & Policies discussion above. 

If the invocation logs show the search API is being successfully called for an OCID but no tags are returned, you probably are 
seeing an [auth issue](https://docs.oracle.com/en-us/iaas/Content/connector-hub/overview.htm#Authenti). Modify 
your policy to grant the Function resource appropriate access. 

### Task function is not adding the target tags

If you have `INCLUDE_TAGS_FOR_ALL_OCIDS` == `False` set, be sure you have the correct OCID `keys` (l-values) in 
your `TARGET_OCID_KEYS` and that the delimiter is a comma with no spaces. Use the invocation logs to confirm that 
the function is searching for the OCID key.   

### Task function is adding stale tags

This function has a cache which it uses to avoid making unnecessary search API calls. Tag values rarely change so
the cache should not be an issue.  However, you can clear the cache by causing the Service Connector to restart 
the Function container.  The easiest way to do that is to change a Fn Application configuration parameter.

----

## Function Configuration Options

Here are the supported variables.  The defaults are fine for most use cases.

| Environment Variable               |                      Default                       | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                           |
|------------------------------------|:--------------------------------------------------:|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| INCLUDE_TAGS_FOR_ALL_OCIDS         |                        True                        | Target OCIDs can exist anywhere in the event JSON payload, regardless of nested position.  Simply provide a comma-separated list of OCID keys (l-values) in the JSON.  The tags for each will be retrieved and added.                                                                                                                                                                                                             |
| TARGET_OCID_KEYS                   | compartmentId,vcnId,subnetId,vnicId,vnicsubnetocid | Target OCIDs can exist anywhere in the event JSON payload, regardless of nested position.  Simply provide a comma-separated list of OCID keys (l-values) in the JSON.  The tags for each will be retrieved and added.                                                                                                                                                                                                             |
| TARGET_OCID_KEYS_WARN_IF_NOT_FOUND |                       False                        | A superset of 'target_ocid_keys' may be declared to cover a wide variety of heterogeneous event types.  Default of False suppresses log warnings when a target OCID key is not found in the event payload.                                                                                                                                                                                                                        |
| INCLUDE_FREEFORM_TAGS              |                        True                        | Determine whether 'freeform' tags should be included.                                                                                                                                                                                                                                                                                                                                                                             |
| INCLUDE_DEFINED_TAGS               |                        True                        | Determine whether 'defined' tags should be included.                                                                                                                                                                                                                                                                                                                                                                              |
| INCLUDE_SYSTEM_TAGS                |                        True                        | Determine whether 'system' tags should be included.                                                                                                                                                                                                                                                                                                                                                                               |
| INCLUDE_EMPTY_TAGS                 |                       False                        | Determines whether empty tag dictionaries will be emitted for 'freeform', 'defined' or 'system' tag types when there are none found.  Downstream logic may expect to find these l-values even if empty. If that is the case, set this to False.                                                                                                                                                                                   |
| TAG_ASSEMBLY_KEY                   |                        tags                        | The assembly key is the dictionary key used to add the tag collection to the event.                                                                                                                                                                                                                                                                                                                                               |
| TAG_POSITION_KEY                   |                                                    | If not empty, `TAG_POSITION_KEY` tells us where in the nested event JSON object to place the tag collection.  If the position is found in the event and the position is a dictionary that does not already contain a `TAG_POSITION_KEY` key, the collection is added there using `TAG_ASSEMBLY_KEY` as the key.  If position is an array, then the tag collection is appended to the array and the `TAG_POSITION_KEY` is ignored. |
| LOGGING_LEVEL                      |                        INFO                        | Controls function logging outputs.  Choices: INFO, WARN, CRITICAL, ERROR, DEBUG                                                                                                                                                                                                                                                                                                                                                   |


## License
Copyright (c) 2014, 2023 Oracle and/or its affiliates
The Universal Permissive License (UPL), Version 1.0
