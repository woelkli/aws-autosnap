#!/usr/bin/env python
#
# (c) 2012/2014 E.M. van Nuil / Oblivion b.v.
# Update 2015 by Zach Himsel

from boto.ec2.connection import EC2Connection
from boto.ec2.regioninfo import RegionInfo
import boto.sns
from datetime import datetime
import sys
import logging
from config import config


# Message to return result via SNS
message = ""
errmsg = ""

# Counters
total_creates = 0
total_deletes = 0
count_errors = 0

# List with snapshots to delete
deletelist = []

# Setup logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(message)s',
                    datefmt='%y-%m-%d %H:%M',
                    filename=config['log_file'],
                    filemode='a')
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)


# Start log
logging.info("Initializing snapshot process")

# Get settings from config.py
aws_access_key = config['aws_access_key']
aws_secret_key = config['aws_secret_key']
ec2_region_name = config['ec2_region_name']
ec2_region_endpoint = config['ec2_region_endpoint']
sns_arn = config.get('sns_arn')
proxyHost = config.get('proxyHost')
proxyPort = config.get('proxyPort')
tag_name = config['tag_name']
tag_value = config['tag_value']
region = RegionInfo(name=ec2_region_name, endpoint=ec2_region_endpoint)

count_success = 0
count_total = 0

# Connect to AWS (testing credentials)
if proxyHost:
    # proxy:
    # using roles
    if aws_access_key:
        conn = EC2Connection(aws_access_key, aws_secret_key, region=region,
                             proxy=proxyHost, proxy_port=proxyPort)
    else:
        conn = EC2Connection(region=region, proxy=proxyHost,
                             proxy_port=proxyPort)
else:
    # non proxy:
    # using roles
    if aws_access_key:
        conn = EC2Connection(aws_access_key, aws_secret_key, region=region)
        logging.info("Authenticating with IAM access key: " + aws_access_key)
    else:
        conn = EC2Connection(region=region)
        logging.info("Authenticating with IAM Role")

# Connect to SNS
if sns_arn:
    logging.info("Detected SNS settings, using SNS")
    if proxyHost:
        # proxy:
        # using roles:
        if aws_access_key:
            sns = boto.sns.connect_to_region(
                ec2_region_name,
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                proxy=proxyHost, proxy_port=proxyPort)
        else:
            sns = boto.sns.connect_to_region(ec2_region_name, proxy=proxyHost,
                                             proxy_port=proxyPort)
    else:
        # non proxy:
        # using roles
        if aws_access_key:
            sns = boto.sns.connect_to_region(
                ec2_region_name,
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key)
        else:
            sns = boto.sns.connect_to_region(ec2_region_name)


def get_resource_tags(resource_id):
    resource_tags = {}
    if resource_id:
        tags = conn.get_all_tags({'resource-id': resource_id})
        for tag in tags:
            # Tags starting with 'aws:' are reserved for internal use
            if not tag.name.startswith('aws:'):
                resource_tags[tag.name] = tag.value
    return resource_tags


def set_resource_tags(resource, tags):
    for tag_key, tag_value in list(tags.items()):
        if tag_key not in resource.tags or resource.tags[tag_key] != tag_value:
            resource.add_tag(tag_key, tag_value)

# Get all the instances that match the tag criteria
instances = conn.get_only_instances(filters={'tag:' + tag_name: tag_value})

# Iterate through each instance in the list
for instance in instances:
    try:
        keep_snapshots = int(instance.tags['autosnap_limit'])
        logging.info("%s: Found instance, keeping %s snapshots (set by instance tag)",
                     instance.id, keep_snapshots)
    except:
        keep_snapshots = config['keep_snapshots']
        logging.info("%s: Found instance, keeping %s snapshots (set globally)",
                     instance.id, keep_snapshots)

    # Get all the volumes attached to this instance
    volumes = conn.get_all_volumes(filters={
        'attachment.instance-id': instance.id})
    if 'Name' in instance.tags:
        instance_name = "{0}".format(instance.tags['Name'])
    else:
        instance_name = "{0}".format(instance.id)

    # Iterate through each volume attached to the selected instances
    for volume in volumes:
        logging.info("%s/%s: Found volume, taking snapshot", instance.id, volume.id)
        try:
            count_total += 1
            tags_volume = get_resource_tags(volume.id)
            # Detailed info for 'description' tag
            description = "AUTOSNAP: {0} ({1}) at {2}".format(
                instance_name,
                volume.id,
                datetime.today().strftime('%d-%m-%Y %H:%M:%S')
            )
            try:
                # Create snapshot
                current_snapshot = volume.create_snapshot(description)
                # Give snapshot the same tags from volume
                set_resource_tags(current_snapshot, tags_volume)
                # Give snapshot tag that indicates it's ours
                set_resource_tags(current_snapshot, {"snapshot_type": tag_name})
                # Uses instance name for snapshot name
                set_resource_tags(current_snapshot, {"Name": instance_name})
                logging.info("%s/%s/%s: Snapshot created and tagged with \"%s\"",
                             instance.id, volume.id, current_snapshot.id, tag_name)
                total_creates += 1
            except Exception as e:
                logging.error("%s/%s: Error while creating snapshot: %s",
                              instance.id, volume.id, e)
                pass

            snapshots = volume.snapshots()
            deletelist = []
            for snapshot in snapshots:
                tags_snapshot = get_resource_tags(snapshot.id)
                if tag_name in tags_snapshot.values():
                    deletelist.append(snapshot)

            def date_compare(snapshot1, snapshot2):
                if snapshot1.start_time < snapshot2.start_time:
                    return -1
                elif snapshot1.start_time == snapshot2.start_time:
                    return 0
                return 1

            deletelist.sort(date_compare)
            delta = len(deletelist) - keep_snapshots
            for deletesnap in range(delta):
                snapshot = deletelist[deletesnap]
                logging.info("%s/%s/%s: Deleting snapshot (%s)",
                             instance.id, volume.id, snapshot.id, snapshot.start_time)
                snapshot.delete()
                total_deletes += 1

        except Exception as e:
            logging.error("%s/%s: Error processing volume: %s",
                          instance.id, volume.id, e)
            errmsg += "{0}:{1}: Error processing volume: {2}".format(instance.id, volume.id, e)
            count_errors += 1
        else:
            count_success += 1

# Result message
logging.info('Finished processing snapshots')
logging.info("Total snapshots created/deleted/errors: %s/%s/%s",
             str(total_creates), str(total_deletes), str(count_errors))

# SNS reporting
if sns_arn:
    if errmsg:
        sns.publish(
            sns_arn, 'Error in processing volumes: '
            + errmsg, 'Error with AWS Snapshot')
    sns.publish(sns_arn, message, 'Finished AWS snapshotting')
