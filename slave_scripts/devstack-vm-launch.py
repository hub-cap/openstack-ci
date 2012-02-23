#!/usr/bin/env python

# Make sure there are always a certain number of VMs launched and
# ready for use by devstack.

# Copyright (C) 2011 OpenStack LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
#
# See the License for the specific language governing permissions and
# limitations under the License.

from libcloud.compute.base import NodeImage, NodeSize, NodeLocation
from libcloud.compute.types import Provider, NodeState
from libcloud.compute.providers import get_driver
from libcloud.compute.deployment import MultiStepDeployment, ScriptDeployment, SSHKeyDeployment

import libcloud
import os, sys
import getopt
import time
import paramiko
import traceback

import vmdatabase

CLOUD_SERVERS_DRIVER = os.environ.get('CLOUD_SERVERS_DRIVER','rackspace')
CLOUD_SERVERS_USERNAME = os.environ['CLOUD_SERVERS_USERNAME']
CLOUD_SERVERS_API_KEY = os.environ['CLOUD_SERVERS_API_KEY']
CLOUD_SERVERS_HOST = os.environ.get('CLOUD_SERVERS_HOST', None)
CLOUD_SERVERS_PATH = os.environ.get('CLOUD_SERVERS_PATH', None)
IMAGE_NAME = os.environ.get('IMAGE_NAME', 'devstack-oneiric')
MIN_RAM = 1024
IMAGE_NAME = os.environ.get('IMAGE_NAME', 'devstack-oneiric')

MIN_RAM = 1024
MIN_READY_MACHINES = 10 # keep this number of machine in the pool
ABANDON_TIMEOUT = 900   # assume a machine will never boot if it hasn't
                        # after this amount of time

db = vmdatabase.VMDatabase()

ready_machines = [x for x in db.getMachines() 
                  if x['state'] == vmdatabase.READY]
building_machines = [x for x in db.getMachines() 
                     if x['state'] == vmdatabase.BUILDING]

# Count machines that are ready and machines that are building,
# so that if the provider is very slow, we aren't queueing up tons
# of machines to be built.
num_to_launch = MIN_READY_MACHINES - (len(ready_machines) + 
                                      len(building_machines))

print "%s ready, %s building, need to launch %s" % (len(ready_machines), 
                                                    len(building_machines), 
                                                    num_to_launch)

if num_to_launch <= 0 and len(building_machines) == 0:
    sys.exit(0)

if CLOUD_SERVERS_DRIVER == 'rackspace':
    Driver = get_driver(Provider.RACKSPACE)
    conn = Driver(CLOUD_SERVERS_USERNAME, CLOUD_SERVERS_API_KEY)

    sizes = [sz for sz in conn.list_sizes() if sz.ram >= MIN_RAM]
    sizes.sort(lambda a,b: cmp(a.ram, b.ram))
    size = sizes[0]
    images = [img for img in conn.list_images() 
              if img.name.startswith(IMAGE_NAME)]
    images.sort()
    if not len(images):
        raise Exception("No images found")
    image = images[-1]
else:
    raise Exception ("Driver not supported")

def check_ssh(ip):
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.WarningPolicy())
    client.connect(ip, timeout=10)

    stdin, stdout, stderr = client.exec_command("echo SSH check succeeded")
    print stdout.read()
    print stderr.read()
    ret = stdout.channel.recv_exit_status()
    if ret:
        raise Exception("Echo command failed")
    return True

if CLOUD_SERVERS_DRIVER == 'rackspace':
    last_name = ''
    error_counts = {}
    for i in range(num_to_launch):
        while True:
            node_name = 'devstack-%s.slave.openstack.org' % int(time.time())
            if node_name != last_name: break
            time.sleep(1)
        node = conn.create_node(name=node_name, image=image, size=size)
        db.addMachine(CLOUD_SERVERS_DRIVER, node.id, IMAGE_NAME, 
                      node_name, node.public_ip[0], node.uuid)
        print "Started building node %s:" % node.id
        print "  name: %s [%s]" % (node_name, node.public_ip[0])
        print "  uuid: %s" % (node.uuid)
        print

    # Wait for nodes
    # TODO: The vmdatabase is (probably) ready, but this needs reworking to 
    # actually support multiple providers
    start = time.time()
    to_ignore = []
    error = False
    while True:
        building_machines = [x for x in db.getMachines() 
                             if x['state'] == vmdatabase.BUILDING]
        if not building_machines:
            print "Finished"
            break
        try:
            provider_nodes = conn.list_nodes()
        except Exception, e:
            traceback.print_exc()
            print "Unable to list nodes"
            continue
        print "Waiting on %s machines" % len(building_machines)
        for my_node in building_machines:
            if my_node['uuid'] in to_ignore: continue
            p_nodes = [x for x in provider_nodes if x.uuid == my_node['uuid']]
            if len(p_nodes) != 1:
                print "Incorrect number of nodes (%s) from provider matching UUID %s" % (len(p_nodes), my_node['uuid'])
                to_ignore.append(my_node)
            else:
                p_node = p_nodes[0]
                if (p_node.public_ips and p_node.state == NodeState.RUNNING):
                    print "Node %s is running, testing ssh" % my_node['id']
                    try:
                        if check_ssh(p_node.public_ip[0]):
                            print "Node %s is ready" % my_node['id']
                            db.setMachineState(my_node['uuid'], vmdatabase.READY)
                    except Exception, e:
                        traceback.print_exc()
                        print "Abandoning node %s due to ssh failure" % (my_node['id'])
                        db.setMachineState(my_node['uuid'], vmdatabase.ERROR)
                        error = True
                elif (p_node.public_ips and p_node.state in 
                    [NodeState.UNKNOWN,
                     NodeState.REBOOTING,
                     NodeState.TERMINATED]):
                    count = error_counts.get(my_node['id'], 0)
                    count += 1
                    error_counts[my_node['id']] = count
                    print "Node %s is in error %s (%s/5)" % (my_node['id'], 
                                                             p_node.state,
                                                             count)
                    if count >= 5:
                        print "Abandoning node %s due to too many errors" % (my_node['id'])
                        db.setMachineState(my_node['uuid'], vmdatabase.ERROR)
                        error = True
                else:
                    if time.time()-my_node['state_time'] >= ABANDON_TIMEOUT:
                        print "Abandoning node %s due to timeout" % (my_node['id'])
                        db.setMachineState(my_node['uuid'], vmdatabase.ERROR)
                        error = True
        time.sleep(3)
if error:
    sys.exit(1)
