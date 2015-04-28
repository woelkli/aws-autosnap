#!/usr/bin/env python
#
# (c) 2012/2014 E.M. van Nuil / Oblivion b.v.
# Update 2015 by Zach Himsel

# Load our dependent libraries
from boto.ec2.connection import EC2Connection
from boto.ec2.regioninfo import RegionInfo
import boto.sns
from datetime import datetime
import sys
import logging
from config import config


# Let's initialize some stuff to use later...
# Init message to return result via SNS
message = ""
errmsg = ""
# Init count variables
total_creates = 0
total_deletes = 0
count_errors = 0
count_success = 0
count_total = 0
# Init deletion list
deletelist = []


# Setup logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(message)s',
                    datefmt='%y-%m-%d %H:%M',
                    filename=config['log_file'],
                    filemode='a')
# Set up log stream to mirror to stdout
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)
# Start log
logging.info("Initializing snapshot process")


# Get settings from config.py
ec2_region_name = config['ec2_region_name']
ec2_region_endpoint = config['ec2_region_endpoint']
sns_arn = config.get('sns_arn')
proxyHost = config.get('proxyHost')
proxyPort = config.get('proxyPort')
tag_name = config['tag_name']
tag_value = config['tag_value']
region = RegionInfo(name=ec2_region_name, endpoint=ec2_region_endpoint)


# Set up our AWS and SNS connection objects
try:
    # Try to load user-specified access keys (if they exist)
    aws_access_key = config['aws_access_key']
    aws_secret_key = config['aws_secret_key']
    if proxyHost:
        # Did the user specify proxy settings?
        aws = EC2Connection(aws_access_key, aws_secret_key, region=region,
                            proxy=proxyHost, proxy_port=proxyPort)
        sns = boto.sns.connect_to_region(
            ec2_region_name,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            proxy=proxyHost, proxy_port=proxyPort)
    else:
        # No?
        aws = EC2Connection(aws_access_key, aws_secret_key, region=region)
        sns = boto.sns.connect_to_region(
            ec2_region_name,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key)
    logging.info("Authenticating with IAM access key: " + aws_access_key)
except:
    # If they didn't, assume we're using an IAM role
    if proxyHost:
        # Did the user specify proxy settings?
        aws = EC2Connection(region=region, proxy=proxyHost, proxy_port=proxyPort)
        sns = boto.sns.connect_to_region(ec2_region_name, proxy=proxyHost,
                                         proxy_port=proxyPort)
    else:
        # No?
        aws = EC2Connection(region=region)
        sns = boto.sns.connect_to_region(ec2_region_name)
    logging.info("Authenticating with IAM Role")


# Alright, let's start doing things
# First, make a list of all the instances that match the tag criteria...
instances = aws.get_only_instances(filters={'tag:' + tag_name: tag_value})

# ...and do things for each one.
for instance in instances:
    try:
        # Check if the instance has a retention override tag
        keep_snapshots = int(instance.tags['autosnap_retention'])
        logging.info("%s: Found instance, keeping %s snapshots (set by instance tag)",
                     instance.id, keep_snapshots)
    except:
        # Otherwise, set it to the global setting
        keep_snapshots = config['keep_snapshots']
        logging.info("%s: Found instance, keeping %s snapshots (set globally)",
                     instance.id, keep_snapshots)

    # Make a list of all volumes attached to this instance
    volumes = aws.get_all_volumes(filters={
        'attachment.instance-id': instance.id})
    if 'Name' in instance.tags:
        instance_name = "{0}".format(instance.tags['Name'])
    else:
        instance_name = "{0}".format(instance.id)

    for volume in volumes:
        # Create a new snapshot for each volume
        logging.info("%s/%s: Found volume, taking snapshot", instance.id, volume.id)
        try:
            # Increase our "total processed" count
            count_total += 1
            # Set the snapshot description
            description = "AUTOSNAP: {0} ({1}) at {2}".format(
                instance_name,
                volume.id,
                datetime.today().strftime('%d-%m-%Y %H:%M:%S')
            )
            try:
                # Create snapshot (and store the ID)
                current_snapshot = volume.create_snapshot(description)
                # Give snapshot a tag that indicates it's ours
                current_snapshot.add_tag("snapshot_type", "autosnap")
                # Uses instance name for snapshot name
                current_snapshot.add_tag("Name", instance_name)
                logging.info("%s/%s/%s: Snapshot created",
                             instance.id, volume.id, current_snapshot.id)
                total_creates += 1
            except Exception as e:
                logging.error("%s/%s: Error while creating snapshot: %s",
                              instance.id, volume.id, e)
                pass

            # Ok, now that the new snapshot has started, let's clean up the old ones
            # Make a list of snapshots for this instance that has our tag in it
            snapshots = aws.get_all_snapshots(filters={
                'volume-id': volume.id,
                'tag:snapshot_type': 'autosnap'})
            deletelist = []  # Make sure the delete list is blank!
            for snapshot in snapshots:
                deletelist.append(snapshot)

            # Sort the delete list by snapshot age
            def date_compare(snapshot1, snapshot2):
                if snapshot1.start_time < snapshot2.start_time:
                    return -1
                elif snapshot1.start_time == snapshot2.start_time:
                    return 0
                return 1
            deletelist.sort(date_compare)

            # And trim off the latest X snapshots
            delta = len(deletelist) - keep_snapshots
            for deletesnap in range(delta):
                snapshot = deletelist[deletesnap]
                logging.info("%s/%s/%s: Deleting snapshot (%s)",
                             instance.id, volume.id, snapshot.id, snapshot.start_time)
                snapshot.delete()  # Delete it
                total_deletes += 1  # Increase our deletion counter

        except Exception as e:
            logging.error("%s/%s: Error processing volume: %s",
                          instance.id, volume.id, e)
            errmsg += "{0}:{1}: Error processing volume: {2}".format(instance.id, volume.id, e)
            count_errors += 1
        else:
            count_success += 1

# Finish up the log file...
logging.info('Finished processing snapshots')
logging.info("Total snapshots created/deleted/errors: %s/%s/%s",
             str(total_creates), str(total_deletes), str(count_errors))

# Report outcome to SNS (if configured)
if sns_arn:
    if errmsg:
        sns.publish(
            sns_arn, 'Error in processing volumes: '
            + errmsg, 'Error with AWS Snapshot')
    sns.publish(sns_arn, message, 'Finished AWS snapshotting')
