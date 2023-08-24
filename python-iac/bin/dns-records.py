import lib.cloudflare as cloudflare

zone_name = 'reptrak.io'
dns_record = 'test-platform'
record_type = 'CNAME'
record_proxied = True
points_to = 'internal-k8s-default-reactcom-9e38b4fee5-1802733037.us-east-1.elb.amazonaws.com'
cloudflareToken = "only-while-testing"

# print("Creating " + dns_record + " CNAME record for " + points_to + " in " + zone_name)
# cloudflare.create_dns_record(cloudflareToken, dns_record, zone_name, record_type, points_to, record_proxied)

# Just to change something related to the DNS record
# record_proxied = False

# print("Updating " + dns_record + " CNAME record for " + points_to + " in " + zone_name)
# cloudflare.update_dns_record(cloudflareToken, dns_record, zone_name, record_type, points_to, record_proxied)

print("Creating/Updating " + record_type + " record " + dns_record + "." + zone_name + " pointing to " + points_to)
cloudflare.create_or_update_dns_record(cloudflareToken, dns_record, zone_name, record_type, points_to, record_proxied)

print("Removing " + record_type + " record " + dns_record + "." + zone_name)
cloudflare.delete_dns_record(cloudflareToken, dns_record, zone_name, record_type)
