#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import with_statement

import logging
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib2
from optparse import OptionParser
from sys import stderr
import boto
from boto.ec2.blockdevicemapping import BlockDeviceMapping, EBSBlockDeviceType
from boto import ec2

# A static URL from which to figure out the latest Mesos EC2 AMI
LATEST_AMI_URL = "https://s3.amazonaws.com/mesos-images/ids/latest-spark-0.7"


# Configure and parse our command-line arguments
def parse_args():
  parser = OptionParser(usage="spark-ec2 [options] <action> <cluster_name>"
      + "\n\n<action> can be: launch, destroy, login, stop, start, get-master",
      add_help_option=False)
  parser.add_option("-h", "--help", action="help",
                    help="Show this help message and exit")
  parser.add_option("-s", "--slaves", type="int", default=3,
      help="Number of slaves to launch (default: 1)")
  parser.add_option("-g", "--compute-groups", type="int", default=1,
      help="Computational groups to launch")
  parser.add_option("-w", "--wait", type="int", default=120,
      help="Seconds to wait for nodes to start (default: 120)")
  parser.add_option("-k", "--key-pair",
      help="Key pair to use on instances")
  parser.add_option("-i", "--identity-file", 
      help="SSH private key file to use for logging into instances")
  parser.add_option("-t", "--instance-type", default="m1.large",
      help="Type of instance to launch (default: m1.large). " +
           "WARNING: must be 64-bit; small instances won't work")
  parser.add_option("-m", "--master-instance-type", default="",
      help="Master instance type (leave empty for same as instance-type)")
  parser.add_option("-r", "--region", default="us-east-1",
      help="EC2 region zone to launch instances in")
  parser.add_option("-z", "--zone", default="",
      help="Availability zone to launch instances in, or 'all' to spread " +
           "slaves across multiple (an additional $0.01/Gb for bandwidth" +
           "between zones applies)")
  parser.add_option("-a", "--ami", default="latest",
      help="Amazon Machine Image ID to use, or 'latest' to use latest " +
           "available AMI (default: latest)")
  parser.add_option("-D", metavar="[ADDRESS:]PORT", dest="proxy_port", 
      help="Use SSH dynamic port forwarding to create a SOCKS proxy at " +
            "the given local address (for use with login)")
  parser.add_option("--resume", action="store_true", default=False,
      help="Resume installation on a previously launched cluster " +
           "(for debugging)")
  parser.add_option("--ebs-vol-size", metavar="SIZE", type="int", default=0,
      help="Attach a new EBS volume of size SIZE (in GB) to each node as " +
           "/vol. The volumes will be deleted when the instances terminate. " +
           "Only possible on EBS-backed AMIs.")
  parser.add_option("--swap", metavar="SWAP", type="int", default=1024,
      help="Swap space to set up per node, in MB (default: 1024)")
  parser.add_option("--spot-price", metavar="PRICE", type="float",
      help="If specified, launch slaves as spot instances with the given " +
            "maximum price (in dollars)")
  parser.add_option("--delete-groups", action="store_true", default=False,
      help="When destroying a cluster, delete the security groups that were created")
  parser.add_option("--topo", default="", help="Topology to upload")
            
  (opts, args) = parser.parse_args()
  if len(args) != 2:
    parser.print_help()
    sys.exit(1)
  (action, cluster_name) = args
  if opts.identity_file == None and action in ['launch', 'login']:
    print >> stderr, ("ERROR: The -i or --identity-file argument is " +
                      "required for " + action)
    sys.exit(1)
  
  # Boto config check
  # http://boto.cloudhackers.com/en/latest/boto_config_tut.html
  home_dir = os.getenv('HOME')
  if home_dir == None or not os.path.isfile(home_dir + '/.boto'):
    if not os.path.isfile('/etc/boto.cfg'):
      if os.getenv('AWS_ACCESS_KEY_ID') == None:
        print >> stderr, ("ERROR: The environment variable AWS_ACCESS_KEY_ID " +
                          "must be set")
        sys.exit(1)
      if os.getenv('AWS_SECRET_ACCESS_KEY') == None:
        print >> stderr, ("ERROR: The environment variable AWS_SECRET_ACCESS_KEY " +
                          "must be set")
        sys.exit(1)
  return (opts, action, cluster_name)


# Get the EC2 security group of the given name, creating it if it doesn't exist
def get_or_make_group(conn, name):
  groups = conn.get_all_security_groups()
  group = [g for g in groups if g.name == name]
  if len(group) > 0:
    return group[0]
  else:
    print "Creating security group " + name
    return conn.create_security_group(name, "Spark EC2 group")


# Wait for a set of launched instances to exit the "pending" state
# (i.e. either to start running or to fail and be terminated)
def wait_for_instances(conn, instances):
  while True:
    for i in instances:
      i.update()
    if len([i for i in instances if i.state == 'pending']) > 0:
      time.sleep(5)
    else:
      return


# Check whether a given EC2 instance object is in a state we consider active,
# i.e. not terminating or terminated. We count both stopping and stopped as
# active since we can restart stopped clusters.
def is_active(instance):
  return (instance.state in ['pending', 'running', 'stopping', 'stopped'])


# Launch a cluster of the given name, by setting up its security groups,
# and then starting new instances in them.
# Returns a tuple of EC2 reservation objects for the master, slave
# and zookeeper instances (in that order).
# Fails if there already instances running in the cluster's groups.
def launch_cluster(conn, opts, cluster_name):
  print "Setting up security groups..."
  input_group = get_or_make_group(conn, cluster_name + "-input")
  compute_group = get_or_make_group(conn, cluster_name + "-compute")
  if input_group.rules == []: # Group was just now created
    input_group.authorize(src_group=input_group)
    input_group.authorize(src_group=compute_group)
    input_group.authorize('tcp', 22, 22, '0.0.0.0/0')
    input_group.authorize('tcp', 4000, 4000, '0.0.0.0/0')
    input_group.authorize('tcp', 4001, 4001, '0.0.0.0/0')
  if compute_group.rules == []: # Group was just now created
    compute_group.authorize(src_group=input_group)
    compute_group.authorize(src_group=compute_group)
    compute_group.authorize('tcp', 22, 22, '0.0.0.0/0')
    compute_group.authorize('tcp', 4000, 4000, '0.0.0.0/0')
    compute_group.authorize('tcp', 4001, 4001, '0.0.0.0/0')
    compute_group.authorize('tcp', 5001, 5001, '0.0.0.0/0')

  # Check if instances are already running in our groups
  active_nodes = get_existing_cluster(conn, opts, cluster_name,
                                      die_on_error=False)
  if any(active_nodes):
    print >> stderr, ("ERROR: There are already instances running in " +
        "group %s, %s or %s" % (input_group.name, compute_group.name))
    sys.exit(1)
  
  # CHANGE THIS IF CHANGING REGIONS
  opts.ami = 'ami-90a1c1f9'
  
  print "Launching instances..."

  try:
    image = conn.get_all_images(image_ids=[opts.ami])[0]
  except:
    print >> stderr, "Could not find AMI " + opts.ami
    sys.exit(1)

  # Create block device mapping so that we can add an EBS volume if asked to
  block_map = BlockDeviceMapping()
  if opts.ebs_vol_size > 0:
    device = EBSBlockDeviceType()
    device.size = opts.ebs_vol_size
    device.delete_on_termination = True
    block_map["/dev/sdv"] = device
  launch_groups = opts.compute_groups + 1
  # Launch compute nodes
  if opts.spot_price != None:
    # Launch spot instances with the requested price
    print ("Requesting %d compute nodes as spot instances with price $%.3f" %
           (launch_groups * opts.slaves, opts.spot_price))
    zones = get_zones(conn, opts)
    num_zones = len(zones)
    i = 0
    my_req_ids = []
    for zone in zones:
      num_slaves_this_zone = get_partition(launch_groups * opts.slaves, num_zones, i)
      compute_reqs = conn.request_spot_instances(
          price = opts.spot_price,
          image_id = opts.ami,
          launch_group = "launch-group-%s" % cluster_name,
          placement = zone,
          count = num_slaves_this_zone,
          key_name = opts.key_pair,
          security_groups = [compute_group],
          instance_type = opts.instance_type,
          block_device_map = block_map)
      my_req_ids += [req.id for req in compute_reqs]
      i += 1
    
    print "Waiting for spot instances to be granted..."
    try:
      while True:
        time.sleep(10)
        reqs = conn.get_all_spot_instance_requests()
        id_to_req = {}
        for r in reqs:
          id_to_req[r.id] = r
        active_instance_ids = []
        for i in my_req_ids:
          if i in id_to_req and id_to_req[i].state == "active":
            active_instance_ids.append(id_to_req[i].instance_id)
        if len(active_instance_ids) == opts.slaves * launch_groups:
          print "All %d compute nodes granted" %(opts.slaves * launch_groups)
          reservations = conn.get_all_instances(active_instance_ids)
          compute_nodes = []
          for r in reservations:
            compute_nodes += r.instances
          break
        else:
          print "%d of %d compute nodes granted, waiting longer" % (
            len(active_instance_ids), opts.slaves * launch_groups)
    except:
      print "Canceling spot instance requests"
      conn.cancel_spot_instance_requests(my_req_ids)
      # Log a warning if any of these requests actually launched instances:
      (input_nodes, compute_nodes) = get_existing_cluster(
          conn, opts, cluster_name, die_on_error=False)
      running = len(input_nodes) + len(compute_nodes)
      if running:
        print >> stderr, ("WARNING: %d instances are still running" % running)
      sys.exit(0)
  else:
    # Launch non-spot instances
    zones = get_zones(conn, opts)
    num_zones = len(zones)
    i = 0
    compute_nodes = []
    for zone in zones:
      num_slaves_this_zone = get_partition(opts.slaves * launch_groups, num_zones, i)
      if num_slaves_this_zone > 0:
        compute_res = image.run(key_name = opts.key_pair,
                              security_groups = [compute_group],
                              instance_type = opts.instance_type,
                              placement = zone,
                              min_count = num_slaves_this_zone,
                              max_count = num_slaves_this_zone,
                              block_device_map = block_map)
        compute_nodes += compute_res.instances
        print "Launched %d compute nodes in %s, regid = %s" % (num_slaves_this_zone,
                                                        zone, compute_res.id)
      i += 1

  # Launch input nodes
  input_type = opts.instance_type
  if input_type == "":
    input_type = opts.instance_type
  if opts.zone == 'all':
    opts.zone = random.choice(conn.get_all_zones()).name
  input_res = image.run(key_name = opts.key_pair,
                         security_groups = [input_group],
                         instance_type = input_type,
                         placement = opts.zone,
                         min_count = 1,
                         max_count = 1,
                         block_device_map = block_map)
  input_nodes = input_res.instances
  print "Launched input in %s, regid = %s" % (zone, input_res.id)

  # Return all the instances
  return (input_nodes, compute_nodes)


# Get the EC2 instances in an existing cluster if available.
# Returns a tuple of lists of EC2 instance objects for the masters,
# slaves and zookeeper nodes (in that order).
def get_existing_cluster(conn, opts, cluster_name, die_on_error=True):
  print "Searching for existing cluster " + cluster_name + "..."
  reservations = conn.get_all_instances()
  input_nodes = []
  compute_nodes = []
  for res in reservations:
    active = [i for i in res.instances if is_active(i)]
    if len(active) > 0:
      group_names = [g.name for g in res.groups]
      if group_names == [cluster_name + "-input"]:
        input_nodes += res.instances
      elif group_names == [cluster_name + "-compute"]:
        compute_nodes += res.instances
  if any((input_nodes, compute_nodes)):
    print ("Found %d input(s), %d computes" %
           (len(input_nodes), len(compute_nodes)))
  if (input_nodes != [] and compute_nodes != []) or not die_on_error:
    return (input_nodes, compute_nodes)
  else:
    if input_nodes == [] and compute_nodes != []:
      print "ERROR: Could not find master in group " + cluster_name + "-input"
    elif input_nodes != [] and compute_nodes == []:
      print "ERROR: Could not find slaves in group " + cluster_name + "-compute"
    else:
      print "ERROR: Could not find any existing cluster"
    sys.exit(1)


# Deploy configuration files and run setup scripts on a newly launched
# or started EC2 cluster.
def setup_cluster(conn, input_nodes, compute_nodes, opts, deploy_ssh_key):
  master = input_nodes[0].public_dns_name
  if deploy_ssh_key:
    print "Copying SSH key %s to master..." % opts.identity_file
    ssh(master, opts, 'mkdir -p ~/.ssh')
    scp(master, opts, opts.identity_file, '~/.ssh/id_rsa')
    ssh(master, opts, 'chmod 600 ~/.ssh/id_rsa')

    #ssh(master, opts, 'sudo apt-get install git')
  ssh(master, opts, 'go get -u github.com/apanda/smpc/...') 
  print compute_nodes
  print input_nodes
  print compute_nodes[0].public_dns_name
  print len(compute_nodes)
  ssh(master, opts, str.format("""cat >~/run-smpc <<EOF
#!/bin/zsh 
export GOMAXPROCS=4
$GOPATH/bin/input --config="/home/ubuntu/input-config.json"
EOF
"""))
  ssh(master, opts, "chmod 755 ~/run-smpc")
  print compute_nodes
  print map(lambda c: c.private_ip_address, compute_nodes)
  ngroups = opts.compute_groups
  ncompute = opts.slaves
  print ngroups
  print ncompute
  groups = [[compute_nodes[group * ncompute + comp] for comp in xrange(0, opts.slaves)] for group in xrange(0, ngroups + 1)]
  print groups
  assert(len(groups) > 1) # make sure there is a redis group
  redis_group = groups[0]
  groups = groups[1:]
  redis_ips = ",".join(map(lambda c: str.format("{{\"Address\":\"{0}:6379\", \"Database\":1}}", c.private_ip_address), redis_group))
  print groups
  print str.format("Redis IPs: {0}", redis_ips)
  ssh(master, opts, str.format("""cat >~/hosts <<EOF
{0}
EOF
""", '\n'.join(map(lambda c: c.private_ip_address, filter(lambda n: n not in redis_group, compute_nodes)))))
  ssh(master, opts, str.format("""cat >~/redis-hosts <<EOF
{0}
EOF
""", '\n'.join(map(lambda c: c.private_ip_address, redis_group))))
  pub_port = 4000
  group_config = 0
  for i in xrange(0, len(redis_group)):
      ssh(master, opts, str.format("""ssh -o StrictHostKeyChecking=no ubuntu@{0} cat >~/launch-redis <<EOF
sudo redis-server /etc/redis/redis.conf
EOF
""", redis_group[i].private_ip_address))
  for group in groups:
      compute_nodes = group
      computes = ",\n".join(map(lambda c: str.format("\"tcp://{0}:5001\"", c.private_ip_address), compute_nodes))
      ssh(master, opts, str.format("""cat >~/input-config-{3}.json <<EOF
{{
  "PubAddress": "tcp://*:{1}",
  "ControlAddress" : "tcp://*:{2}",
  "Clients": {0},
  "Shell": true
}}
EOF
    """, ncompute, pub_port, pub_port + 1, group_config))
      for i in xrange(0, len(compute_nodes)):
        ssh(master, opts, str.format("ssh -o StrictHostKeyChecking=no ubuntu@{0} go get -u github.com/apanda/smpc/...", compute_nodes[i].private_ip_address))
        ssh(compute_nodes[i].public_dns_name, opts, str.format("""cat >~/compute-config.json <<EOF
{{
  "PubAddress": "tcp://{1}:{2}",
  "ControlAddress" : "tcp://{1}:{3}",
  "Clients" : [
  {0}
  ],
  "Databases" : [{4}]
}}
EOF
    """, computes, str(master), pub_port, pub_port + 1, redis_ips))
        ssh(compute_nodes[i].public_dns_name, opts, str.format("""cat >~/run-smpc <<EOF
#!/bin/zsh
export GOMAXPROCS=4
$GOPATH/bin/compute --config="/home/ubuntu/compute-config.json" --peer={0} > peer{0}.out &
EOF
""", i))
        ssh(compute_nodes[i].public_dns_name, opts, "chmod 755 ~/run-smpc")
      pub_port += 2
      group_config += 1

  
  configs = ' '.join(map(lambda c:"/home/ubuntu/input-config-%d.json"%c, xrange(0, group_config)))
  ssh(master, opts, str.format("""cat >~/test-smpc <<EOF
#!/bin/zsh 
export GOMAXPROCS=4
parallel-ssh -h ~/redis-hosts sudo ~/launch-redis
parallel-ssh -h ~/hosts ~/run-smpc
$GOPATH/bin/input --config="{0}" --topo=\$1 --dest=\$2
parallel-ssh -h ~/hosts killall compute
parallel-ssh -h ~/redis-hosts sudo killall redis-server
EOF
""", configs))
  ssh(master, opts, "chmod 755 ~/test-smpc")
  if opts.topo != "":
      scp_dir(master, opts, opts.topo, "~/") 

# Wait for a whole cluster (masters, slaves and ZooKeeper) to start up
def wait_for_cluster(conn, wait_secs, input_nodes, compute_nodes):
  print "Waiting for instances to start up..."
  time.sleep(5)
  wait_for_instances(conn, input_nodes)
  wait_for_instances(conn, compute_nodes)
  print "Waiting %d more seconds..." % wait_secs
  time.sleep(wait_secs)

# Get number of local disks available for a given EC2 instance type.
def get_num_disks(instance_type):
  # From http://docs.amazonwebservices.com/AWSEC2/latest/UserGuide/index.html?InstanceStorage.html
  disks_by_instance = {
    "m1.small":    1,
    "m1.medium":   1,
    "m1.large":    2,
    "m1.xlarge":   4,
    "t1.micro":    1,
    "c1.medium":   1,
    "c1.xlarge":   4,
    "m2.xlarge":   1,
    "m2.2xlarge":  1,
    "m2.4xlarge":  2,
    "cc1.4xlarge": 2,
    "cc2.8xlarge": 4,
    "cg1.4xlarge": 2
  }
  if instance_type in disks_by_instance:
    return disks_by_instance[instance_type]
  else:
    print >> stderr, ("WARNING: Don't know number of disks on instance type %s; assuming 1"
                      % instance_type)
    return 1


# Copy a file to a given host through scp, throwing an exception if scp fails
def scp(host, opts, local_file, dest_file):
  subprocess.check_call(
      "scp -q -o StrictHostKeyChecking=no -i %s '%s' '%s@%s:%s'" %
      (opts.identity_file, local_file, 'ubuntu', host, dest_file), shell=True)

# Copy a file to a given host through scp, throwing an exception if scp fails
def scp_dir(host, opts, local_file, dest_file):
  subprocess.check_call(
      "scp -q -o StrictHostKeyChecking=no -i %s -r '%s' '%s@%s:%s'" %
      (opts.identity_file, local_file, 'ubuntu', host, dest_file), shell=True)


# Run a command on a host through ssh, retrying up to two times
# and then throwing an exception if ssh continues to fail.
def ssh(host, opts, command):
  tries = 0
  while True:
    try:
      return subprocess.check_call(
        "ssh -t -o StrictHostKeyChecking=no -i %s %s@%s '%s'" %
        (opts.identity_file, 'ubuntu', host, command), shell=True)
    except subprocess.CalledProcessError as e:
      if (tries > 2):
        raise e
      print "Error connecting to host {0}, sleeping 30".format(e)
      time.sleep(30)
      tries = tries + 1

# Gets a list of zones to launch instances in
def get_zones(conn, opts):
  if opts.zone == 'all':
    zones = [z.name for z in conn.get_all_zones()]
  else:
    zones = [opts.zone]
  return zones


# Gets the number of items in a partition
def get_partition(total, num_partitions, current_partitions):
  num_slaves_this_zone = total / num_partitions
  if (total % num_partitions) - current_partitions > 0:
    num_slaves_this_zone += 1
  return num_slaves_this_zone


def main():
  (opts, action, cluster_name) = parse_args()
  try:
    conn = ec2.connect_to_region(opts.region)
  except Exception as e:
    print >> stderr, (e)
    sys.exit(1)

  # Select an AZ at random if it was not specified.
  if opts.zone == "":
    opts.zone = random.choice(conn.get_all_zones()).name

  if action == "launch":
    if opts.resume:
      (input_nodes, compute_nodes) = get_existing_cluster(
          conn, opts, cluster_name)
    else:
      (input_nodes, compute_nodes) = launch_cluster(
          conn, opts, cluster_name)
      wait_for_cluster(conn, opts.wait, input_nodes, compute_nodes)
    setup_cluster(conn, input_nodes, compute_nodes, opts, True)

  elif action == "destroy":
    response = raw_input("Are you sure you want to destroy the cluster " +
        cluster_name + "?\nALL DATA ON ALL NODES WILL BE LOST!!\n" +
        "Destroy cluster " + cluster_name + " (y/N): ")
    if response == "y":
      (input_nodes, compute_nodes) = get_existing_cluster(
          conn, opts, cluster_name, die_on_error=False)
      print "Terminating master..."
      for inst in input_nodes:
        inst.terminate()
      print "Terminating slaves..."
      for inst in compute_nodes:
        inst.terminate()
      
      # Delete security groups as well
      if opts.delete_groups:
        print "Deleting security groups (this will take some time)..."
        group_names = [cluster_name + "-input", cluster_name + "-compute"]
        
        attempt = 1;
        while attempt <= 3:
          print "Attempt %d" % attempt
          groups = [g for g in conn.get_all_security_groups() if g.name in group_names]
          success = True
          # Delete individual rules in all groups before deleting groups to
          # remove dependencies between them
          for group in groups:
            print "Deleting rules in security group " + group.name
            for rule in group.rules:
              for grant in rule.grants:
                  success &= group.revoke(ip_protocol=rule.ip_protocol,
                           from_port=rule.from_port,
                           to_port=rule.to_port,
                           src_group=grant)
          
          # Sleep for AWS eventual-consistency to catch up, and for instances
          # to terminate
          time.sleep(30)  # Yes, it does have to be this long :-(
          for group in groups:
            try:
              conn.delete_security_group(group.name)
              print "Deleted security group " + group.name
            except boto.exception.EC2ResponseError:
              success = False;
              print "Failed to delete security group " + group.name
          
          # Unfortunately, group.revoke() returns True even if a rule was not
          # deleted, so this needs to be rerun if something fails
          if success: break;
          
          attempt += 1
          
        if not success:
          print "Failed to delete all security groups after 3 tries."
          print "Try re-running in a few minutes."

  elif action == "login":
    (input_nodes, compute_nodes) = get_existing_cluster(
        conn, opts, cluster_name)
    master = input_nodes[0].public_dns_name
    print "Logging into master " + master + "..."
    proxy_opt = ""
    if opts.proxy_port != None:
      proxy_opt = "-D " + opts.proxy_port
    subprocess.check_call("ssh -o StrictHostKeyChecking=no -i %s %s %s@%s" %
        (opts.identity_file, proxy_opt, 'ubuntu', master), shell=True)

  elif action == "get-master":
    (input_nodes, compute_nodes) = get_existing_cluster(conn, opts, cluster_name)
    print input_nodes[0].public_dns_name

  elif action == "stop":
    response = raw_input("Are you sure you want to stop the cluster " +
        cluster_name + "?\nDATA ON EPHEMERAL DISKS WILL BE LOST, " +
        "BUT THE CLUSTER WILL KEEP USING SPACE ON\n" + 
        "AMAZON EBS IF IT IS EBS-BACKED!!\n" +
        "Stop cluster " + cluster_name + " (y/N): ")
    if response == "y":
      (input_nodes, compute_nodes) = get_existing_cluster(
          conn, opts, cluster_name, die_on_error=False)
      print "Stopping master..."
      for inst in input_nodes:
        if inst.state not in ["shutting-down", "terminated"]:
          inst.stop()
      print "Stopping slaves..."
      for inst in compute_nodes:
        if inst.state not in ["shutting-down", "terminated"]:
          inst.stop()

  elif action == "start":
    (input_nodes, compute_nodes) = get_existing_cluster(
        conn, opts, cluster_name)
    print "Starting slaves..."
    for inst in compute_nodes:
      if inst.state not in ["shutting-down", "terminated"]:
        inst.start()
    print "Starting master..."
    for inst in input_nodes:
      if inst.state not in ["shutting-down", "terminated"]:
        inst.start()
    wait_for_cluster(conn, opts.wait, input_nodes, compute_nodes)
    setup_cluster(conn, input_nodes, compute_nodes, opts, False)

  else:
    print >> stderr, "Invalid action: %s" % action
    sys.exit(1)


if __name__ == "__main__":
  logging.basicConfig()
  main()
