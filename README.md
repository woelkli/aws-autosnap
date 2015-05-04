aws-autosnap
=================
aws-autosnap is a python script to make it easy to *systematically snapshot any instances you wish*.

Simply add a tag to each instance you want snapshots of, configure and install a cronjob for aws-autosnap and you are off. It will even handle cleaning old snapshots on a daily, weekly, or yearly basis so that you can setup the retention policy to suit.

Features:
- *Python based*: Leverages boto and is easy to configure and run as a crontab
- *Simple tag system*: Just add a customizable tag to each of your EBS volumes you want snapshots of
- *Configure retention policy*: Configure how many days, weeks, and months worth of snapshots you want to retain
- *SNS Notifications* (optional): aws-autosnap works with Amazon SNS our of the box, so you can be notified of snapshots

Usage
==========
1. Install and configure Python and Boto (See: https://github.com/boto/boto)
2. (optional) Create a SNS topic in AWS and copy the ARN into the config file
3. (optional) Subscribe with a email address to the SNS topic
4. Create either an IAM user or EC2 instance role to authenticate with AWS.
  * If using an IAM user, you must set the access and secret keys in the config file.
  * Attach a security policy for this user/role (see the [sample IAM policy](iam.policy.sample)).
5. Create `config.py` in the script's directory (use config.sample for reference).
6. For each instance that you want to snapshot, add the following tags:
  * (required) `autosnap:true`: indicates to autosnap to snapshot this instance (a custom `tag_name` and `tag_value` can be set in `config.py`).
  * (required) `autosnap_frequency:X`: how often (in hours) you want this instance to be snapshotted.
  * (optional) `autosnap_retention:X`: how many snapshots you want to keep (if not specified, it will use the value in `config.py`).
7. (optional, but recommended) schedule this script to run on a frequent basis (at least as often as the lowest value of `autosnap_frequency`). E.g. if you have some instances you want to snapshot hourly, and some you want to snapshot daily, run the script hourly, and set the `autosnap_frequency` for each instance to either 1 or 24. Autosnap will only snapshot an instance if at least X hours have passed since the last snapshot it's taken (where X = `autosnap_frequency`).


Results
==========
When this script creates a snapshot, it will tag the snapshot with 'snapshot\_type:autosnap' (along with some other useful tags). Later, when it is creating the list of snapshots to delete, it will only consider snapshots for a given volume if that tag is present. This allows you to make your own snapshots without having to worry about autosnap deleting them later (just make sure you don't tag it with 'snapshot_type:autosnap').
