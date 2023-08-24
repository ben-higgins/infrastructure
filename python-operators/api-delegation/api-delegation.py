import time
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from pprint import pprint

# To read all the routes from the route table
def read_routetable(k8s_client):
    try:
        routeTable = k8s_client.list_cluster_custom_object(group="gateway.solo.io", version="v1", plural="routetables")

        allRoutes = {}
        for route in routeTable['items']:
            # pprint(route, indent=2)
            for i in range(len(route['spec']['routes'])):

                if 'regex' in route['spec']['routes'][i]['matchers'][0].keys():
                    prefix = f"{route['spec']['routes'][i]['matchers'][0]['regex'].rsplit('/',1)[0]}/"
                elif 'prefix' in route['spec']['routes'][i]['matchers'][0].keys():
                    prefix = f"{route['spec']['routes'][i]['matchers'][0]['prefix'].rsplit('/',1)[0]}/"

                name = f"{route['metadata']['name']}"
                namespace = f"{route['metadata']['namespace']}"
                if 'routeAction' in route['spec']['routes'][i].keys():
                    upstream = f"{route['spec']['routes'][i]['routeAction']['single']['upstream']['name']}"
                else:
                    upstream = None

                if prefix not in allRoutes and upstream is not None:
                    allRoutes[prefix] = {
                        'name': name,
                        'namespace': namespace,
                        'prefix': prefix,
                        'upstream': upstream,
                    }

        return allRoutes
    except Exception as e:
        print(f"Exception when reading all route tables: {e}")
        raise


# To search for the existance of a Virtual Service
def search_virtualservice(k8s_client, virtualServiceName):
    try:
        virtualService = k8s_client.list_cluster_custom_object(group="gateway.solo.io", version="v1", plural="virtualservices")

        virtualServiceFound = False

        for i in range(len(virtualService['items'])):
            if virtualService['items'][i]['metadata']['name'] == virtualServiceName:
                virtualServiceFound = True
                break

        return virtualServiceFound
    except Exception as e:
        print(f"Exception when searching for Virtual Service {virtualServiceName}: {e}")
        raise


# To create a Virtual Service
def create_virtualservice(k8s_client, virtualServiceName):
    # definition of custom resource
    create_resource = {
        "apiVersion":"gateway.solo.io/v1",
        "kind":"VirtualService",
        "metadata":{
            "name":virtualServiceName
        },
        "spec":{
            "name":virtualServiceName,
            "namespace":"default",
            "virtualHost":{
                "domains":[
                    "*"
                ],
                "routes":[
                ]
            }
        }
    }

    # for route in routesTables:
    #     create_resource['spec']['virtualHost']['routes'].append(routesTables[route])

    try:
        print(f"Virtual Service {virtualServiceName} doesn't exists already, so creating it")
        k8s_client.create_namespaced_custom_object(
            group="gateway.solo.io",
            version="v1",
            namespace="default",
            plural="virtualservices",
            body=create_resource,
        )
        print(f"Virtual Service {virtualServiceName} created successfully\n")
    except Exception as e:
        print(f"Exception when creating Virtual Service {virtualServiceName}: {e}")
        raise


# To create or delete a route in Virtual Service
def patch_virtualservice(k8s_client, virtualServiceName, routesTables):
    # definition of custom resource
    patch_resource = {
        "spec":{
            "name":virtualServiceName,
            "namespace":"default",
            "virtualHost":{
                "domains":[
                    "*"
                ],
                "routes":[
                ]
            }
        }
    }

    for route in routesTables:
        patch_resource['spec']['virtualHost']['routes'].append(routesTables[route])

    try:
        k8s_client.patch_namespaced_custom_object(
            group="gateway.solo.io",
            version="v1",
            name=virtualServiceName,
            namespace="default",
            plural="virtualservices",
            body=patch_resource,
        )
        # delete_gloo_gateway_pod(k8s_client)
        print(f"Route change applied successfully\n")
    except Exception as e:
        print(f"Exception when patching virtual service {virtualServiceName}: {e}")
        raise


def check_upstream_status(k8s_client, upstreamName):
    try:
        resource = k8s_client.get_namespaced_custom_object(
            group="gloo.solo.io",
            version="v1",
            name=upstreamName,
            namespace="default",
            plural="upstreams",
        )
        # print("\nResource details:")
        # pprint(resource)

        if 'statuses' in resource['status'].keys():
            return resource['status']['statuses']['default']['state']
        else:
            return 0
    except Exception as e:
        print(f"Exception when getting {upstreamName} upstream's status: {e}")
        raise


def get_upstream_service_and_port(k8s_client, upstreamName):
    try:
        resource = k8s_client.get_namespaced_custom_object(
            group="gloo.solo.io",
            version="v1",
            name=upstreamName,
            namespace="default",
            plural="upstreams",
        )

        upstream = {}
        # print("Resource details:")
        appName = resource['spec']['kube']['selector']['app']
        serviceName = resource['spec']['kube']['serviceName']
        servicePort = resource['spec']['kube']['servicePort']
        upstream = {
            'appName': appName,
            'serviceName': serviceName,
            'servicePort': servicePort
        }

        return upstream
    except Exception as e:
        print(f"Exception when getting {upstreamName} upstream's app name, service name and port: {e}")
        raise


def is_service_alive(k8s_client, serviceName):
    k8s_client = client.CoreV1Api()
    serviceAlive = False
    # Creation of the Deployment in specified namespace
    # (Can replace "default" with a namespace you may have created)

    try:
        resource = k8s_client.read_namespaced_service(namespace="default", name=serviceName)
        # pprint(resource)
        # print(f"Type of resource is: {type(resource)}")

        if resource.spec.cluster_ip is not None and resource.spec.ports[0].port is not None:
            serviceAlive = True

        return serviceAlive

    except Exception as e:
        print(f"Exception when looking for {serviceName} service status: {e}")
        raise


def is_application_alive(k8s_client, appName):
    k8s_client = client.CoreV1Api()
    appAlive = False
    labelSelector=f"app={appName}"

    try:
        resource = k8s_client.list_namespaced_pod(namespace="default", label_selector=labelSelector)
        for condition in resource.items[0].status.conditions:
            #print(f"{condition.type} is {condition.status}")
            #print()
            if condition.type == "ContainersReady" and condition.status == "True":
                appAlive = True

        return appAlive

    except Exception as e:
        print(f"Exception when searching for {appName} application pod: {e}")
        raise


def delete_gloo_gateway_pod(k8s_client):
    k8s_client = client.CoreV1Api()
    appName = "gateway"
    labelSelector=f"gloo={appName}"

    try:
        resource = k8s_client.list_namespaced_pod(namespace="default", label_selector=labelSelector)
        for pods in range(len(resource.items)):
            podName = resource.items[pods].metadata.name
            k8s_client.delete_namespaced_pod(namespace="default", name=podName)
            print(f"To restart gloo gateway pod, {podName} pod has been removed successfully")
    except Exception as e:
        print(f"Exception when deleting {appName} pod: {e}")
        raise


# Authentication to K8s cluster
try:
    # If running the python script from the pod
    config.load_incluster_config()
except config.ConfigException:
    try:
        #If not in pod, try loading the kubeconfig
        config.load_kube_config()
    except config.ConfigException:
        raise ApiException("Could not configure kubernetes python client")

k8s_client = client.CustomObjectsApi()
virtualServiceName = "api-delegation"


# dictionary to store routes
routesTables = {}

while True:
    # list to store prefix names that will be used to remove stale/deleted prefixes
    routePrefixsList = []
    addRoute = False

    # Fetch route table records from EKS API server
    allRoutes = read_routetable(k8s_client)

    # If Virtual Service doesn't exists already, create it
    if not search_virtualservice(k8s_client, virtualServiceName):
        create_virtualservice(k8s_client, virtualServiceName)

    # Loop through all the routestables and add valid ones in virtual service
    for item in allRoutes:

        # Push each prefix to list (this list will later be used to remove stale/deleted prefixes)
        routePrefixsList.append(item)

        # If route is not already in the virtual service, only then create it
        if item not in routesTables:

            # Get the upstream name, it's service, port and app name of routetable entry
            upstreamName = allRoutes[item]['upstream']
            upstreamDict = get_upstream_service_and_port(k8s_client, upstreamName)
            appName = upstreamDict['appName']

            # Make sure the route prefix we got from route table is valid, otherwise Virtual Service goes into "Pending State"
            if check_upstream_status(k8s_client, upstreamName) == 1 and is_application_alive(k8s_client, appName) == True:
                addRoute = True
                print (f"{item} is a new route prefix to {allRoutes[item]['name']}, so adding it")

                routesTables[item] = {
                    "matchers":[
                        {
                            "prefix": allRoutes[item]['prefix']
                        }
                    ],
                    "delegateAction": {
                        "ref": {
                            'name': allRoutes[item]['name'],
                            'namespace': allRoutes[item]['namespace'],
                        }
                    }
                }

    # If a new route is found in this loop that needs to be added, apply the route patch to virtual service
    if addRoute:
        patch_virtualservice(k8s_client, virtualServiceName, routesTables)

    # If the route doesn't exists anymore, remove it from the dict and it from virtual service
    # https://stackoverflow.com/a/11941855
    removeRoute = False
    for route in list(routesTables):
        if route not in routePrefixsList:
            removeRoute = True
            print (f"Microservice for {route} is deleted, so deleting route from virtual service")
            routesTables.pop(route)

    # If a new route is found in this loop that needs to be deleted, apply the route patch to virtual service
    if removeRoute:
        patch_virtualservice(k8s_client, virtualServiceName, routesTables)

    time.sleep(10)
