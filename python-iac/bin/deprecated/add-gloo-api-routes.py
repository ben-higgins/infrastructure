#!/usr/bin/python

# todo: compare updated routes and see if a route was removed from upstream service then remove from virtualservice
from subprocess import Popen, PIPE
import os
import json
import argparse
import lib.exec_ctl as exe
import time
import boto3
from bson import json_util
from lib.region_manager import RegionManager


parser = argparse.ArgumentParser()
parser.add_argument('--action', required=True, choices=["Deploy", "Rollback", "Delete"], help='Deploy, Delete, Rollback routes')
parser.add_argument('--service', required=True, help='Name of the service to add routes for')
parser.add_argument("--deployRegion", required=False, help="AWS region EKS was deployed to")
parser.add_argument("--branchName", required=False, help="Branch equals environment to deploy to")
args = parser.parse_args()

def set_envtype(branch_raw):
    # value might come in with a prefix
    try:
        branch = branch_raw.split('/')[1]
    except:
        branch = branch_raw

    #TODO temporary workaround to assign an environment type of develop if deploying a feature branch
    if branch not in "develop qa main":
        envType = "testing"
    else:
        envType = branch

    return envType

def get_cluster(branchName, region):
    client = boto3.client('cloudformation', region_name=region)
    #get stack name from cloudformation
    response = client.list_stacks(StackStatusFilter=[
        'CREATE_COMPLETE', 'ROLLBACK_FAILED', 'ROLLBACK_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE'
    ])

    if len(response['StackSummaries']) == 0:
        print("No cloudformation stack found in " + region + " region")
        exit(1)

    for key in response['StackSummaries']:
        if branchName + "-Eks" in key['StackName']:
            clusterName = key['StackName']
            print("EKS cluster name: " + clusterName)
            return clusterName

def update_kubeconfig(clusterName, region):
    client = boto3.client('cloudformation', region_name=region)

    response = client.describe_stacks(StackName=clusterName)
    outputs = response["Stacks"][0]["Outputs"]
    for output in outputs:
        if output["OutputKey"] == "EKSConfig":
            print("updating local kube config file: " + output["OutputValue"])
            command = output["OutputValue"]
            exe.sub_process(command.split())
            time.sleep(10)

def get_index(route):
    # get current routes from virtualservice
    kubectl = os.popen("kubectl get virtualservice default -n default --output json")
    gloo = kubectl.read()
    p = json.loads(gloo)
    routes = p['spec']['virtualHost']['routes']

    route_list = {}
    index = 0
    for path in routes:
        route_list[path['matchers'][0]['exact']] = index
        index = index + 1

    return route_list[route]

def get_upstream_name(service):
    # get upstreams to get upstream service names
    kubectl = os.popen("kubectl get upstream -n default --output json")
    gloo = kubectl.read()

    r = json.loads(gloo)
    items = r['items']

    for key in items:
        if service in key['metadata']['name']:
            service = key['metadata']['name']

    return service

def get_all_routes():
    # get current routes from virtualservice
    kubectl = os.popen("kubectl get virtualservice default -n default --output json")
    gloo = kubectl.read()
    return gloo

def action(branchName, region, service, action):
    print("Get EKS Cluster Name")
    clusterName = get_cluster(branchName, region)

    # Exit the build if no EKS cluster is found
    if not clusterName:
        print("No EKS cluster named " + branchName + " found in " + region + " region")
        exit(1)

    # update-kubeconfig to connect to right cluster
    print("Update kubectl config with EKS Cluster Details")
    update_kubeconfig(clusterName, region)

    #before updating routes, the gloo discovery has to be restarted
    p1 = Popen(["kubectl", "get", "pods"], stdout=PIPE)
    p2 = Popen(["grep", "discovery-"], stdin=p1.stdout, stdout=PIPE)
    p3 = Popen(["awk", "{print $1}"], stdin=p2.stdout, stdout=PIPE)
    p4 = Popen(["xargs", "kubectl", "delete", "--force", "--grace-period", "0", "pod"], stdin=p3.stdout, stdout=PIPE)
    print(p4.stdout.read())
    time.sleep(30)

    if action == 'Deploy' or action == 'Rollback':
        # check if there's a virtualservice called default
        kubectl = os.popen("kubectl get virtualservice default -n default --output json")
        status = kubectl.read()

        try:
            json.loads(status)
            print("Virtualservice default already exists. Skipping creation")
        except:
            print("No virtualservice default. Creating now")
            virtualservice = """\
apiVersion: gateway.solo.io/v1
kind: VirtualService
metadata:
    name: default
    namespace: default
spec:
    displayName: default
    virtualHost:
        options:
            cors:
                allowCredentials: true
                allowHeaders:
                    - origin
                allowOriginRegex:
                    - 'https://[a-zA-Z0-9]*-apigateway.reptrak.io/'
                    - 'https://[a-zA-Z0-9]*-apigateway.reptrak.com/'
                    - 'https://[a-zA-Z0-9]*.reptrak.io/'
                    - 'https://[a-zA-Z0-9]*.reptrak.com/'
                    - 'https://[a-zA-Z0-9]*-platform.reptrak.io/'
                    - 'https://[a-zA-Z0-9]*-platform.reptrak.com/'
                exposeHeaders:
                    - origin
                maxAge: 1d
        domains:
            - '*'
"""
            f = open("/tmp/virtualservice.yaml", "w")
            f.write(virtualservice)
            f.close()

            kubectl = os.popen("kubectl apply -f /tmp/virtualservice.yaml")
            print(json.dumps(kubectl.read(), sort_keys=False, indent=4, default=json_util.default))


        upstreamService = get_upstream_name(service)

        # call upstream service to get routes
        print("Retrieving upstream for: " + upstreamService)
        kubectl = os.popen("kubectl get upstream " + upstreamService + " -n default --output json")
        gloo = kubectl.read()

        r = json.loads(gloo)
        try:
            transformations = r["spec"]["kube"]["serviceSpec"]["rest"]["transformations"]
        except:
            print("Failed to retrieve routes from upstream. Possible reason is that gloo was not able to read swagger.json from service")
            print(json.dumps(r, sort_keys = False, indent = 4, default = json_util.default))
            exit(1)

        # create json for paths with multiple methods
        custom_paths = {}
        for key, subdict in transformations.items():
            # remove any uri from path
            url_raw = subdict['headers'][':path']['text'].replace("//", "/")
            trailString = url_raw.split("?", 1)
            substring = trailString[0]
            # remove bug with flask
            url = substring.replace("//", "/")


            if url not in custom_paths.keys():
                custom_paths[url] = {
                    'methods': [],
                    'service': upstreamService,
                }

            custom_paths[url]['methods'].append(subdict['headers'][':method']['text'])

        # json shouldn't be empty because default should always exist at this point
        p = json.loads(get_all_routes())

        # use try to evaluate if these are the first routes being added. If not, then check if paths already exist
        try:
            routes = p['spec']['virtualHost']['routes']
        except:
            routes = None

        if routes is not None:
            # create list of paths to evaluate, The len might be needed for if path already exists and we don't want to delete the wrong path
            route_list = {}
            for path in routes:
                route_list[path['matchers'][0]['exact']] = len(path['matchers'][0]['exact'])

            print(route_list)

            # if does not routes exist add new routes
            for key in custom_paths:
                # format methods into string
                verbs = str(custom_paths[key]['methods'])
                for c in "'[] ":
                    verbs = verbs.replace(c, "")

                if key not in route_list:

                    print("Create route " + key)
                    command = "glooctl add route  --dest-name " + custom_paths[key]['service'] + " --path-exact " + key + " --prefix-rewrite " + key +  " --method " + verbs + " --dest-namespace default --namespace default"
                    print(command)
                    exe.sub_process(command)
                    time.sleep(3)

                else:
                    # remove route and re-add
                    # Not sure yet but this might be a bug. If /Dashboards is the route it might retrieve something like /Dashboards/last-updated
                    print("The route " + key + " exist but will be recreated")
                    command = "glooctl rm route --name default --namespace default --index " + str(get_index(key))
                    print(command)
                    exe.sub_process(command)
                    time.sleep(3)

                    command = "glooctl add route  --dest-name " + custom_paths[key]['service'] + " --path-exact " + key + " --prefix-rewrite " + key +  " --method " + verbs + " --dest-namespace default --namespace default"
                    print(command)
                    exe.sub_process(command)
                    time.sleep(3)

        else:
            # no routes exist yet, create first routes
            for key in custom_paths:
                # format methods into string
                verbs = str(custom_paths[key]['methods'])
                for c in "'[] ":
                    verbs = verbs.replace(c, "")

                command = "glooctl add route  --dest-name " + custom_paths[key]['service'] + " --path-exact " + key + " --prefix-rewrite " + key +  " --method " + verbs + " --dest-namespace default --namespace default"
                print(command)
                exe.sub_process(command)
                time.sleep(3)

    elif action == 'Delete':
        p = json.loads(get_all_routes())

        try:
            routes = p['spec']['virtualHost']['routes']
        except:
            print("No routes in virtualservice")
            exit(1)

        print(routes)
        for path in routes:
            # don't like this logic but the service name has already been removed from upstream so have to compare to existing routes now
            if service in path['routeAction']['single']['upstream']['name']:
                # get index and delete
                command = "glooctl rm route --name default --namespace default --index " + str(get_index(path['matchers'][0]['exact']))
                print(command)
                exe.sub_process(command)
                time.sleep(3)

    # print out virtualservice
    print("\n\nVirtualservice config:\n\n")
    kubectl = os.popen("kubectl get virtualservice default -n default --output yaml")
    gloo = kubectl.read()
    print(gloo)




if args.branchName and args.deployRegion:
    # check overrides
    print("Select branch")
    branchName = set_envtype(args.branchName)

    # set region
    if args.deployRegion == "None":
        # Create a list of all regions of the env
        regions = RegionManager.get_regions(
            environment=branchName,
            region=args.deployRegion
        )

        print("")
        print("For " + branchName + " env, selected regions are " + ", ".join(regions))

        # Loop through the list of regions and perform the selected action on every region
        for region in regions:
            print("")
            print("Performing " + args.action + " operation for " + branchName + " env in " + region + " region")
            print("")
            action(branchName, region, args.service, args.action)
    else:
        region = args.deployRegion

        #stop deployment if no region set
        if not region:
            print("No region was supplied", flush=True)
            exit(1)

        action(branchName, region, args.service, args.action)

