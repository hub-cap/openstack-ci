#!/usr/bin/env python

# Remove old devstack VMs that have been given to developers.

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

import os, sys, time
import getopt

from libcloud.compute.base import NodeImage, NodeSize, NodeLocation
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver

import vmdatabase

CLOUD_SERVERS_DRIVER = os.environ.get('CLOUD_SERVERS_DRIVER','rackspace')
CLOUD_SERVERS_USERNAME = os.environ['CLOUD_SERVERS_USERNAME']
CLOUD_SERVERS_API_KEY = os.environ['CLOUD_SERVERS_API_KEY']
MACHINE_LIFETIME = 24*60*60 # Amount of time after being used

db = vmdatabase.VMDatabase()

if '--all' in sys.argv:
    print "Reaping all known machines"
    REAP_ALL = True
else:
    REAP_ALL = False

print 'Known machines (start):'
for machine in db.getMachines():
    print machine

if CLOUD_SERVERS_DRIVER == 'rackspace':
    Driver = get_driver(Provider.RACKSPACE)
    conn = Driver(CLOUD_SERVERS_USERNAME, CLOUD_SERVERS_API_KEY)

def delete(machine):
    node = [n for n in conn.list_nodes() if n.id==str(machine['id'])]
    if not node:
        print '  Machine id %s not found' % machine['id']
        db.delMachine(machine['uuid'])
        return
    node = node[0]
    node.destroy()
    db.delMachine(machine['uuid'])

now = time.time()
for machine in db.getMachines():
    # Normally, reap machines that have sat in their current state
    # for 24 hours, unless that state is READY.
    if REAP_ALL or (machine['state']!=vmdatabase.READY and 
                    now-machine['state_time'] > MACHINE_LIFETIME):
        print 'Deleting', machine['name']
        delete(machine)
        
print
print 'Known machines (end):'
for machine in db.getMachines():
    print machine
