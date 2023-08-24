import CloudFlare

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


def get_dns_record_id(cloudflareToken, dns_record, zone_name, record_type):

    # get the zone id first
    zone_id = get_zone_id(cloudflareToken, zone_name)

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


def create_dns_record(cloudflareToken, dns_record, zone_name, record_type, points_to, record_proxied):

    # get the zone id first
    zone_id = get_zone_id(cloudflareToken, zone_name)

    dns_entry = {'name':dns_record, 'type':record_type, 'content':points_to, 'proxied':record_proxied}

    cf = CloudFlare.CloudFlare(token=cloudflareToken)

    try:
        response = cf.zones.dns_records.post(zone_id, data=dns_entry)
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit('/zones.dns_records.post %s %s - %d %s' % (zone_name, dns_entry['name'], e, e))

    print("DNS record of " + response['name'] + " created successfully")


def update_dns_record(cloudflareToken, dns_record, zone_name, record_type, points_to, record_proxied):

    # get the zone id first
    zone_id = get_zone_id(cloudflareToken, zone_name)

    # DNS record id is also required to update an existing record
    dns_record_id = get_dns_record_id(cloudflareToken, dns_record, zone_name, record_type)

    if dns_record_id is not None:
        dns_entry = {'name':dns_record, 'type':record_type, 'content':points_to, 'proxied':record_proxied}

        cf = CloudFlare.CloudFlare(token=cloudflareToken)

        try:
            response = cf.zones.dns_records.put(zone_id, dns_record_id, data=dns_entry)
        except CloudFlare.exceptions.CloudFlareAPIError as e:
            exit('/zones/dns_records.put %d %s - api call failed' % (e, e))

        print("DNS record of " + response['name'] + " updated successfully")


def delete_dns_record(cloudflareToken, dns_record, zone_name, record_type):

    # get the zone id first
    zone_id = get_zone_id(cloudflareToken, zone_name)

    # DNS record id is required to delete a record
    dns_record_id = get_dns_record_id(cloudflareToken, dns_record, zone_name, record_type)

    if dns_record_id is not None:
        cf = CloudFlare.CloudFlare(token=cloudflareToken)

        try:
            response = cf.zones.dns_records.delete(zone_id, dns_record_id)
        except CloudFlare.exceptions.CloudFlareAPIError as e:
            exit('/zones/dns_records.delete %d %s - api call failed' % (e, e))

        print("DNS record having id " + response['id'] + " has been delete successfully")


def create_or_update_dns_record(cloudflareToken, dns_record, zone_name, record_type, points_to, record_proxied):

    # If the DNS record id exists it means record already exists
    dns_record_id = get_dns_record_id(cloudflareToken, dns_record, zone_name, record_type)

    if dns_record_id is None:
        create_dns_record(cloudflareToken, dns_record, zone_name, record_type, points_to, record_proxied)
    else:
        update_dns_record(cloudflareToken, dns_record, zone_name, record_type, points_to, record_proxied)
