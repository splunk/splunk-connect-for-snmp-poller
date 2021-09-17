
# Development Instructions for Poller

> This file is used as a reference steps while working on development aspects of SNMP Poller component of Splunk Connect for SNMP!


### To add new python module (example)

```cmd
poetry add schedule
poetry add celery
```

### Setup Environment for poller

```
git clone https://github.com/splunk/splunk-connect-for-snmp-poller/
cd "splunk-connect-for-snmp-poller"
poetry install
poetry build
poetry run python sc4snmp-poller --help
```


### SNMP Agent Simulator

#### Install snmpsim

```bash
python3 -m virtualenv venv
source venv/bin/activate
pip3 install snmpsim
cd venv/bin/
snmpsimd.py --version
# or
python3 ./venv/bin/snmpsimd.py -h
```


Note: In case above steps doesn't help initiate "snmpsimd.py", tweak your $PATH to include absolute path of directory containing "snmpsimd.py".

```bash
export PATH="$HOME/bin:$PATH"
PATH="/home/splunker/snmpsim/venv/bin/:$PATH";
source /home/splunker/snmpsim/venv/bin/active
snmpsimd
snmpsimd.py -h
```

Example:
```bash
snmpsimd.py --data-dir=data --agent-udpv4-endpoint=0.0.0.0:1161
```


## Setup Docker Container Environment 📦


### Get started with Docker

- [Get-Docker](https://docs.docker.com/get-docker/)


### Run RabbitMQ

```docker run -d -p 5672:5672 rabbitmq```

### Run MongoDB

```docker run -d -p 27017:27017 -v ./data:/data/db mongo```


## Steps to run each component including poller scheduler and worker.

Note: 
- Ensure you follow the order of initialization to avoid connectivity issues!
- This assumes MongoDB and RabbitMQ are configured in config.yaml of respective component.

#### Run MIB / Translation Server

```poetry run sc4snmp-mib-server```

### Run SNMP Simulator
```snmpsimd.py --data-dir=data --agent-udpv4-endpoint=0.0.0.0:1161```

#### Run Poller / Scheduler:

```cmd
export CELERY_BROKER_URL="amqp://guest@rabbitmq-host:5672"
poetry run sc4snmp-poller -l debug
```

#### Run Celery Worker

```cmd
export CELERY_BROKER_URL="amqp://guest@rabbitmq-host:5672"
poetry run python -m celery -A "splunk_connect_for_snmp_poller.manager.celery_client" worker -l DEBUG -n worker1
```


### Inventory explained!

```csv
host,version,community,profile,freqinseconds
10.202.12.56,2c,public,1.3.6.1.2.1.1.9.1.2.3,10
#192.168.0.1,2c,passphrase1,router,10
```

#### Inventory Fields

- **host**: is IP address or FQDN of the SNMP Server

- **version**: SNMP server version (i.e. 1, 2c, 3)

- **community**: secret / passphrase used to enumerate SNMP device

- **profile**: 
  - Profile could be OID, OID tree, or MIB string
  - Examples:
    - 1.3.6.1.2.1.1.9.1.2.3,10
    - 1.3.6.1.2.1.1.9.1.2.*
    - SNMPv2-MIB::sysObjectID.0

- **freqinseconds**: seconds at which we want SNMP Poller to query SNMP Host.


## Contributors

- Ryan Faircloth
- Yuan Ling
- Luca Stoppa
- Wojciech Eliasz
- Ankit Bhagat
- Adam Ryznar
- Mayur Pipaliya
