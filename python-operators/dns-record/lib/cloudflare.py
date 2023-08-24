import CloudFlare

mapping = {
    "us-east-1": {
        "check_regions": "ENAM",
        "latitude": 39.4,
        "longitude": -80.04
    },
    "eu-west-1": {
        "check_regions": "WEU",
        "latitude": 53.34,
        "longitude": -6.26
    },
    "eu-central-1": {
        "check_regions": "EEU",
        "latitude": 52.07,
        "longitude": 16.28
    },
    "ap-southeast-2": {
        "check_regions": "SAS",
        "latitude": -29.19,
        "longitude": 147.78
    }
}


#######################################################################
# Interaction with simple DNS records
#######################################################################

def get_zone_id(cloudflareToken, zone_name):

    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    # query for the zone name and expect only one value back
    try:
        zones = cf.zones.get(params = {'name':zone_name,'per_page':1})
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit('/zones.get %d %s - api call failed' % (e, e))
    except Exception as e:
        exit('/zones.get - %s - api call failed' % (e))

    if len(zones) == 0:
        exit('No zones found')

    # extract and return the zone id
    zone = zones[0]
    return zone['id']


def get_dns_record_id(cloudflareToken, zone_name, zone_id, dns_record, record_type):

    cf = CloudFlare.CloudFlare(token=cloudflareToken)
    try:
        dns_records = cf.zones.dns_records.get(zone_id, params={'name':dns_record + '.' + zone_name, 'type':record_type, 'per_page':1})
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit('/zones/dns_records.get %d %s - api call failed' % (e, e))

    if len(dns_records) == 0:
        # print("No such DNS record found: " + record_type + " record " + dns_record + "." + zone_name)
        return None
    else:
        # extract and return the dns_record id
        dns_name = dns_records[0]
        return dns_name['id']


def create_dns_record(cloudflareToken, zone_name, zone_id, dns_record, record_type, points_to, record_proxied):

    dns_entry = {'name':dns_record, 'type':record_type, 'content':points_to, 'proxied':record_proxied}

    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    try:
        response = cf.zones.dns_records.post(zone_id, data=dns_entry)
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit('/zones.dns_records.post %s %s - %d %s' % (zone_name, dns_entry['name'], e, e))

    print("DNS record of " + response['name'] + " created successfully")


def update_dns_record(cloudflareToken, zone_id, dns_record, dns_record_id, record_type, points_to, record_proxied):

    if dns_record_id is not None:
        dns_entry = {'name':dns_record, 'type':record_type, 'content':points_to, 'proxied':record_proxied}

        cf = CloudFlare.CloudFlare(token=cloudflareToken)

        try:
            response = cf.zones.dns_records.put(zone_id, dns_record_id, data=dns_entry)
        except CloudFlare.exceptions.CloudFlareAPIError as e:
            exit('/zones/dns_records.put %d %s - api call failed' % (e, e))

        print("DNS record of " + response['name'] + " updated successfully")


#######################################################################
# Interaction with Load Balancer/Pools/Monitors
#######################################################################

# Return the Cloudflare account ID
def get_reptrak_account_id(cloudflareToken):

    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    try:
        response = cf.accounts()
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit('/accounts %d %s - api call failed' % (e, e))

    AccountID = None
    for account in response:
        if account['name'] == "RepTraks Account":
            AccountID = account['id']

    if AccountID is None:
        exit('No Account ID found')
    return AccountID

# Provided DNS Zone name and DNS Record, return the loadbalancer id and associated pool ids
def get_lb_id_pool_ids(cloudflareToken, dns_record, zone_name, zone_id):
    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    try:
        load_balancers = cf.zones.load_balancers.get(zone_id)
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit('/zones/load_balancers/get %d %s - api call failed' % (e, e))

    # There can be more then one LBs in one zone
    # So, from the list of load balancers, select the one who's name matches the current DNS Record and get it's ID and it's pool IDs
    lb_name = f"{dns_record}.{zone_name}"
    lb_id = None
    lb_pool_ids = None
    for lbs in load_balancers:
        if lbs['name'] == lb_name:
            lb_id = lbs['id']
            lb_pool_ids = lbs['default_pools']

    return lb_id, lb_pool_ids


# Provided the LB Monitor name, fetch accounts' loadbalancer monitor id
def get_lb_monitor_id(cloudflareToken, dns_record, account_id):
    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    # fetch the list of existing moitors
    try:
        monitors = cf.accounts.load_balancers.monitors.get(account_id)
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit('/accounts/load_balancers/monitors/get %d %s - api call failed' % (e, e))

    # Search for the monitor name in existing monitors
    lb_monitor_name = f"{dns_record}-monitor"
    monitor_id = None
    for item in monitors:
        # If pool is for the current region, then get it's iD
        if lb_monitor_name in item['description']:
            # print(f"Monitor already exists: {item}")
            monitor_id = item['id']

    return monitor_id


# To create the LoadBalancer Monitor, if monitor doesn't exists already
def create_lb_monitor(cloudflareToken, dns_record, account_id, healthcheck_type, healthcheck_port, healthcheck_path):
    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    monitor_name = f"{dns_record}-monitor"
    entry = {"type":healthcheck_type,"description":monitor_name,"method":"GET","path":healthcheck_path,"port":healthcheck_port,"timeout":5,"retries":2,"interval":60,"expected_codes":"200","follow_redirects":False,"allow_insecure":True}

    try:
        monitor = cf.accounts.load_balancers.monitors.post(account_id, data=entry)
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit('/accounts/load_balancers/monitors/post %d %s - api call failed' % (e, e))

    if monitor is not None:
        print(f"Load Balancer Monitor {monitor_name} has been created successfully")
        monitor_id = monitor['id']
        return monitor_id
    else:
        print(f"Unable to create Load Balancer Monitor {monitor_name}")
        return None


# To delete the LoadBalancer Monitor
def delete_lb_monitor(cloudflareToken, dns_record, account_id, monitor_id):
    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    monitor_name = f"{dns_record}-monitor"

    try:
        monitor = cf.accounts.load_balancers.monitors.delete(account_id, monitor_id)
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit('/accounts/load_balancers/monitors/delete %d %s - api call failed' % (e, e))

    if monitor is not None:
        print(f"Load Balancer Monitor {monitor_name} has been deleted successfully")
    else:
        print(f"Unable to delete Load Balancer Monitor {monitor_name}")


# def get_load_balancer_id(cloudflareToken, region, dns_record, account_id):
#     cf = CloudFlare.CloudFlare(token=cloudflareToken)

#     pool_name = f"{dns_record}-{region}"

#     try:
#         pools = cf.accounts.load_balancers.pools(account_id)
#     except CloudFlare.exceptions.CloudFlareAPIError as e:
#         exit('/accounts/load_balancers/pools %d %s - api call failed' % (e, e))

#     # Search for the pool in existing pools
#     pool_id = None
#     for item in pools:
#         if pool_name in item['name']:
#             pool_id = item['id']

#     # If pool is found in exisiting list of pools return it's id
#     if pool_id is None:
#         return None
#     else:
#         return pool_id


# Create the load balancer for the zone if it doesn't exists
def create_load_balancer(cloudflareToken, pool_id, pool_name, dns_record, zone_name, zone_id):
    default_pool = []
    default_pool.append(pool_id)
    fallback_pool = default_pool[0]
    lb_name = f"{dns_record}.{zone_name}"

    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    entry = {"description":lb_name,"name":lb_name,"default_pools":default_pool,"fallback_pool":fallback_pool,"proxied":True,"steering_policy":"proximity"}

    try:
        loadbalancer = cf.zones.load_balancers.post(zone_id, data=entry)
        print(f"Load Balancer {lb_name} with pool/origin {pool_name} has been created successfully")
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        print(f"Unable to create Load Balancer {lb_name} with pool/origin {pool_name}")
        exit('/zones/load_balancers %d %s - api call failed' % (e, e))


# Delete the load balancer for the zone if it doesn't exists
def delete_load_balancer(cloudflareToken, pool_name, dns_record, zone_name, zone_id, lb_id):
    lb_name = f"{dns_record}.{zone_name}"

    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    try:
        loadbalancer = cf.zones.load_balancers.delete(zone_id, lb_id)
        print(f"Load Balancer {lb_name} with pool/origin {pool_name} has been deleted successfully")
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        print(f"Unable to delete Load Balancer {lb_name} with pool/origin {pool_name}")
        exit('/zones/load_balancers/delete %d %s - api call failed' % (e, e))


# Add Pool to the load balancer for the zone with pools
def add_pool_to_load_balancer(cloudflareToken, lb_pool_ids, pool_id, pool_name, lb_id, dns_record, zone_name, zone_id):

    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    lb_name = f"{dns_record}.{zone_name}"
    default_pool = lb_pool_ids
    default_pool.append(pool_id)
    fallback_pool = default_pool[0]

    entry = {"description":lb_name,"name":lb_name,"default_pools":default_pool,"fallback_pool":fallback_pool,"proxied":True,"steering_policy":"proximity"}

    try:
        loadbalancer = cf.zones.load_balancers.patch(zone_id, lb_id, data=entry)
        print(f"Load Balancer pool {pool_name} has been successfully added to LB {loadbalancer['name']}")
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        print(f"Unable to add Load Balancer pool {pool_name} to LB {loadbalancer['name']}")
        exit('/zones/load_balancers %d %s - api call failed' % (e, e))


# Remove pool from the load balancer for the zone with pools
def remove_pool_from_load_balancer(cloudflareToken, lb_pool_ids, pool_id, pool_name, lb_id, dns_record, zone_name, zone_id):

    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    lb_name = f"{dns_record}.{zone_name}"
    default_pool = lb_pool_ids
    default_pool.remove(pool_id)
    fallback_pool = default_pool[0]

    entry = {"description":lb_name,"name":lb_name,"default_pools":default_pool,"fallback_pool":fallback_pool,"proxied":True,"steering_policy":"proximity"}

    try:
        loadbalancer = cf.zones.load_balancers.patch(zone_id, lb_id, data=entry)
        print(f"Load Balancer pool {pool_name} has been successfully removed from LB {loadbalancer['name']}")
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        print(f"Unable to remove Load Balancer pool {pool_name} from LB {loadbalancer['name']}")
        exit('/zones/load_balancers %d %s - api call failed' % (e, e))


# Fetch the load balancer pools provided the load balancer id
def get_load_balancer_pool(cloudflareToken, region, lb_pool_ids, account_id):
    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    pool_id = None
    pool_name = None
    if lb_pool_ids is not None:

        for item in lb_pool_ids:
            try:
                pool = cf.accounts.load_balancers.pools(account_id, item)
            except CloudFlare.exceptions.CloudFlareAPIError as e:
                exit('/accounts/load_balancers/pools %d %s - api call failed' % (e, e))

            # If pool is for the current region, then get it's iD
            if region in pool['name']:
                pool_id = pool['id']
                pool_name = pool['name']

    return pool_id, pool_name


# Create the load balancer pool if it doesn't exists already
def create_load_balancer_pool(cloudflareToken, region, dns_record, points_to, account_id, monitorid):
    check_regions = mapping[region]["check_regions"]
    latitude = mapping[region]["latitude"]
    longitude = mapping[region]["longitude"]
    pool_name = f"{dns_record}-{region}"

    pool_id = None
    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    # entry = {"description":pool_name,"name":pool_name,"enabled":True,"check_regions":[check_regions],"latitude":latitude,"longitude":longitude,"minimum_origins":1,"monitor":monitorid,"origins":[{"name": pool_name, "address":points_to, "enabled": True, "weight":1}],"origin_steering":{"policy":"random"},"notification_email":"RTGlobalEngineering@reptrak.com"}
    entry = {"description":pool_name,"name":pool_name,"enabled":True,"check_regions":[check_regions],"latitude":latitude,"longitude":longitude,"minimum_origins":1,"monitor":monitorid,"origins":[{"name": pool_name, "address":points_to, "enabled": True, "weight":1}],"origin_steering":{"policy":"random"}}

    try:
        pool = cf.accounts.load_balancers.pools.post(account_id, data=entry)
        pool_id = pool['id']
        print(f"Load Balancer Pool/Origin {pool_name} with origin address {points_to} has been created successfully")
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        print(f"Unable to create Load Balancer Pool/Origin {pool_name} with origin address {points_to}")
        exit('/accounts/load_balancers/pools %d %s - api call failed' % (e, e))

    return pool_id, pool_name


# Create the load balancer pool if it doesn't exists already
def delete_load_balancer_pool(cloudflareToken, region, dns_record, points_to, account_id, pool_id):
    pool_name = f"{dns_record}-{region}"

    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    try:
        pool = cf.accounts.load_balancers.pools.delete(account_id, pool_id)
        pool_id = pool['id']
        print(f"Load Balancer Pool/Origin {pool_name} with origin address {points_to} has been deleted successfully")
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        print(f"Unable to delete Load Balancer Pool/Origin {pool_name} with origin address {points_to}")
        exit('/accounts/load_balancers/pools/delete %d %s - api call failed' % (e, e))


# Update the load balancer pool's origin
def update_lb_pool_origin(cloudflareToken, account_id, pool_name, pool_id, points_to):
    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    entry = {'origins':[{"name": pool_name, "address":points_to, "enabled": True, "weight":1}]}

    try:
        pool = cf.accounts.load_balancers.pools.patch(account_id, pool_id, data=entry)
        print(f"Address {points_to} for Load Balancer pool/origin name {pool_name} has been updated successfully")
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        print(f"Unable to update address {points_to} for Load Balancer pool/origin name {pool_name}")
        exit('/accounts/load_balancers/pools %d %s - api call failed' % (e, e))


#######################################################################
# Main functions
#######################################################################

def create_or_update_dns_record(cloudflareToken, region, zone_name, dns_record, record_type, points_to, record_proxied, healthcheck_type, healthcheck_port, healthcheck_path):
    # ID of DNS Zone is needed for CNAME DNS entry as well as LoadBalancer DNS entry
    zone_id = get_zone_id(cloudflareToken, zone_name)

    if record_type == "CNAME":
        # If the DNS record id exists it means record already exists
        dns_record_id = get_dns_record_id(cloudflareToken, zone_name, zone_id, dns_record, record_type)

        if dns_record_id is None:
            create_dns_record(cloudflareToken, zone_name, zone_id, dns_record, record_type, points_to, record_proxied)
        else:
            update_dns_record(cloudflareToken, zone_id, dns_record, dns_record_id, record_type, points_to, record_proxied)

    elif record_type == "LB":
        # ID of Cloudflare account is needed for LoadBalancer DNS entry
        account_id = get_reptrak_account_id(cloudflareToken)

        # If the montior exists already, return it's ID
        monitor_id = get_lb_monitor_id(cloudflareToken, dns_record, account_id)

        # If the Load Balancer exists already, return loadbalancer id and associated pool ids
        lb_id, lb_pool_ids = get_lb_id_pool_ids(cloudflareToken, dns_record, zone_name, zone_id)

        # If the pool exists in pool IDs of Load Balancer, return it's ID
        pool_id, pool_name = get_load_balancer_pool(cloudflareToken, region, lb_pool_ids, account_id)


        # If the LB Pool, Monitor and Load Balancer exists already, just update the pool's origin address
        if monitor_id is not None and pool_id is not None and lb_id is not None:
            update_lb_pool_origin(cloudflareToken, account_id, pool_name, pool_id, points_to)

        # If the LB Pool Monitor doesn't exists, Create the Monitor
        if monitor_id is None:
            # Create LB Monitor
            monitor_id = create_lb_monitor(cloudflareToken, dns_record, account_id, healthcheck_type, healthcheck_port, healthcheck_path)

        # If the LB Pool doesn't exists, create the LoadBalancer Pool (with new origin address) and update the Load Balancer with the pool ID
        if pool_id is None:
            pool_id, pool_name = create_load_balancer_pool(cloudflareToken, region, dns_record, points_to, account_id, monitor_id)

            # If load Balancer exists already and the above created pool is the 2nd pool for LB
            if lb_id is not None:
                add_pool_to_load_balancer(cloudflareToken, lb_pool_ids, pool_id, pool_name, lb_id, dns_record, zone_name, zone_id)

        # If the LB Pool doesn't exists, Create the LoadBalancer
        if lb_id is None:
            create_load_balancer(cloudflareToken, pool_id, pool_name, dns_record, zone_name, zone_id)


def delete_dns_record(cloudflareToken, region, zone_name, dns_record, record_type, points_to):
    # ID of DNS Zone is needed for CNAME DNS entry as well as LoadBalancer DNS entry
    zone_id = get_zone_id(cloudflareToken, zone_name)

    if record_type == "CNAME":

        # DNS record id is required to delete a record
        dns_record_id = get_dns_record_id(cloudflareToken, zone_name, zone_id, dns_record, record_type)

        if dns_record_id is not None:
            cf = CloudFlare.CloudFlare(token=cloudflareToken)

            try:
                response = cf.zones.dns_records.delete(zone_id, dns_record_id)
            except CloudFlare.exceptions.CloudFlareAPIError as e:
                exit('/zones/dns_records/delete %d %s - api call failed' % (e, e))

            print("DNS record having id " + response['id'] + " has been delete successfully")

    elif record_type == "LB":
        # ID of Cloudflare account is needed for LoadBalancer DNS entry
        account_id = get_reptrak_account_id(cloudflareToken)

        # If the montior exists already, return it's ID
        monitor_id = get_lb_monitor_id(cloudflareToken, dns_record, account_id)

        # If the Load Balancer exists already, return loadbalancer id and associated pool ids
        lb_id, lb_pool_ids = get_lb_id_pool_ids(cloudflareToken, dns_record, zone_name, zone_id)

        # If the pool exists in pool IDs of Load Balancer, return it's ID
        pool_id, pool_name = get_load_balancer_pool(cloudflareToken, region, lb_pool_ids, account_id)

        if lb_pool_ids is not None and len(lb_pool_ids) == 1:
            # If the LB exists, delete the LoadBalancer
            if lb_id is not None:
                delete_load_balancer(cloudflareToken, pool_name, dns_record, zone_name, zone_id, lb_id)

            # If the LB Pool exists, delete the LoadBalancer Pool
            if pool_id is not None:
                delete_load_balancer_pool(cloudflareToken, region, dns_record, points_to, account_id, pool_id)

            # If the LB Pool Monitor exists, delete it
            if monitor_id is not None:
                delete_lb_monitor(cloudflareToken, dns_record, account_id, monitor_id)
        else:
            # If the LB Pool exists, delete the LoadBalancer Pool
            if pool_id is not None:
                remove_pool_from_load_balancer(cloudflareToken, lb_pool_ids, pool_id, pool_name, lb_id, dns_record, zone_name, zone_id)
                delete_load_balancer_pool(cloudflareToken, region, dns_record, points_to, account_id, pool_id)
