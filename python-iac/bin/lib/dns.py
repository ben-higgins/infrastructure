
def dns_record_of_env(envName, region):
# For main and QA
    dnsEntryProxied = "True"
    dnsEntryZone = "reptrak.com"

    if envName == "main" and region == "eu-central-1":
        dnsEnvPrefix = ""
    elif envName == "main" and region == "eu-west-1":
        # Need to figure out what to do when (not the daily-infra-smoke-test but) the actual DR of main will be deployed in eu-west-1
        dnsEnvPrefix = "smoketest-"
    elif envName == "qa" and region == "eu-west-1":
        dnsEnvPrefix = envName + "-"
        dnsEntryZone = "reptrak.io"
    elif envName == "develop" and region == "eu-west-1":
        dnsEnvPrefix = envName + "-"
        dnsEntryZone = "reptrak.io"
        dnsEntryProxied = "False"
    elif envName == "testing" and region == "eu-west-1":
        dnsEnvPrefix = envName + "-"
        dnsEntryZone = "reptrak.io"
        dnsEntryProxied = "False"
    elif envName == "develop" and region == "us-east-1":
        dnsEnvPrefix = "test-" + envName + "-"
        dnsEntryZone = "reptrak.io"
        dnsEntryProxied = "False"
    elif envName == "testing" and region == "us-east-1":
        dnsEnvPrefix = "test-" + envName + "-"
        dnsEntryZone = "reptrak.io"
        dnsEntryProxied = "False"
    else:
        dnsEntryZone = ""
        dnsEnvPrefix = ""

    # print("Prefix: '" + dnsEnvPrefix + "', DNS Zone: '" + dnsEntryZone + "', DNS Proxied: '" + dnsEntryProxied + "'")
    return dnsEnvPrefix, dnsEntryZone, dnsEntryProxied
