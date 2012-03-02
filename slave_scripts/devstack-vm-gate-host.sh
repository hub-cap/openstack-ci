#!/bin/bash -x

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
sudo crontab -u jenkins -r || /bin/true

cd workspace

DEST=/opt/stack
# create the destination directory and ensure it is writable by the user
sudo mkdir -p $DEST
if [ ! -w $DEST ]; then
    sudo chown `whoami` $DEST
fi

# The workspace has been copied over here by devstack-vm-gate.sh
mv * /opt/stack
cd /opt/stack/devstack

cat <<EOF >localrc
ACTIVE_TIMEOUT=60
BOOT_TIMEOUT=90
ASSOCIATE_TIMEOUT=60
MYSQL_PASSWORD=secret
RABBIT_PASSWORD=secret
ADMIN_PASSWORD=secret
SERVICE_TOKEN=111222333444
ROOTSLEEP=0
ENABLED_SERVICES=g-api,g-reg,key,n-api,n-crt,n-obj,n-cpu,n-net,n-vol,n-sch,horizon,mysql,rabbit
SKIP_EXERCISES=boot_from_volume,client-env,swift
SERVICE_HOST=127.0.0.1
SYSLOG=True
EOF

# The vm template update job should cache some images in ~/files.
# Move them to where devstack expects:
if ls ~/cache/files/*; then
    mv ~/cache/files/* /opt/stack/devstack/files
fi

# Move the PIP cache into position:
sudo mkdir -p /var/cache/pip
sudo mv ~/cache/pip/* /var/cache/pip

# Start with a fresh syslog
sudo stop rsyslog
sudo mv /var/log/syslog /var/log/syslog-pre-devstack
sudo touch /var/log/syslog
sudo chown /var/log/syslog --ref /var/log/syslog-pre-devstack
sudo chmod /var/log/syslog --ref /var/log/syslog-pre-devstack
sudo chmod a+r /var/log/syslog
sudo start rsyslog

./stack.sh
./exercise.sh
