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
4. Create either an IAM user or role to authenticate.
  * If using an IAM user, you must set the access and secret keys in either the config file, or as env variables
  * Attach a security policy for this user/role (see the iam.policy.sample)
5. Create config.py in the script's directory (use config.samle for reference).
6. For each instance that you want to snapshot, add the tag/value specified in your config.py.
  * (optional) You can also add a tag 'autosnap_retention' to an instance to override the keep_snapshots setting in config.py
7. (optional) Install the script in the crontab. Example: 

		# chmod +x autosnap.py
		# crontab -e
		30 1 * * 1-5 /path/to/autosnap.py day
		30 2 * * 6 /path/to/autosnap.py week
		30 3 1 * * /path/to/autosnap.py month


Results
==========
When this script creates a snapshot, it will tag the snapshot with 'snapshot\_type:autosnap'. Later, when it is creating the list of snapshots to delete, it will only consider snapshots for a given volume if that tag is present. This allows you to make your own snapshots without having to worry about autosnap deleting them later (just make sure you don't tag it with 'snapshot_type:autosnap').
