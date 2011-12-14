#!/bin/bash

# Script that is run on the devstack vm; configures and 
# invokes devstack.

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

set -o errexit

# Remove any crontabs left over from the image
sudo crontab -u root -r || /bin/true

cd workspace

DEST=/opt/reddwarf
# create the destination directory and ensure it is writable by the user
sudo mkdir -p $DEST
if [ ! -w $DEST ]; then
    sudo chown `whoami` $DEST
fi

# The workspace has been copied over here by devstack-vm-gate.sh
mv * /opt/reddwarf
mv .git* /opt/reddwarf/
ln -s /opt/reddwarf/ /src
ln -s /opt/reddwarf/integration/vagrant /
cd /opt/reddwarf/integration/vagrant

# Add network stuffs since cloud servers whacks the images bridge
echo '
auto br100
iface br100 inet static
    bridge_ports eth1
    address 172.16.2.15
    netmask 255.255.255.0
' >> /etc/network/interfaces
/etc/init.d/networking restart
ifconfig eth1:0 33.33.33.11 netmask 255.255.255.255
ifconfig eth1:1 10.0.4.15 netmask 255.255.255.255

echo '10.0.4.15	apt.rackspace.com
127.0.1.1	host host vagrant' >> /etc/hosts
hostname host

# Chown manually since the whoami isint correct above yet
chown -R vagrant /opt/reddwarf/

# Run the CI tests
sudo -u vagrant ./reddwarf-ci run