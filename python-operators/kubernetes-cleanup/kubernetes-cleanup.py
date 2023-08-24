from kubernetes import client, config
from kubernetes.client.rest import ApiException
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import lib.secrets_manager as secrets
from lib.cloudformation_manager import CloudformationManager
import boto3
import time
import argparse
import json
import datetime
import logging

parser = argparse.ArgumentParser()
parser.add_argument("--envName", required=True, help="environment name")
parser.add_argument("--region", required=True, help="eks deployed region")
parser.add_argument("--secret", required=True, help="secret name")
args = parser.parse_args()

# get AWS secret token for Slack
response = json.loads(secrets.get_secret(args.envName + "/" + args.secret, args.region))

# Parse SlackToken and SlackChannel from the AWS Secret
for key in response:
    if key == "SlackToken":
        SLACK_BOT_TOKEN = response[key].strip()
    if key == "SlackChannel":
        SLACK_CHANNEL = response[key].strip()

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

k8s_client = client.CoreV1Api()

# WebClient instantiates a slack client that can call API methods
slack_client = WebClient(token=SLACK_BOT_TOKEN)

def send_slack_message(slack_message):
    channel_id = SLACK_CHANNEL

    try:
        # Call the conversations.list method using the WebClient
        result = slack_client.chat_postMessage(
            channel=channel_id,
            icon_emoji=':Kubernetes:',
            username=args.envName + " (" + args.region + ")",
            text="\n".join(slack_message)
        )
        # print(result)

    except SlackApiError as e:
        print(f"Error: {e}")

# Re-notify about unhealthy pods and nodes daily at 9am Eastern Time
def renotify():
    if datetime.datetime.utcnow().time().strftime("%H:%M") == datetime.time(14,0).strftime("%H:%M"):
        return True
    else:
        return False

    # # Re-notify about unhealthy pods and nodes every 6 hours. I now think that it will be too noisy so commenting it for now
    # if datetime.datetime.utcnow().time().strftime("%H:%M") == datetime.time(0,0).strftime("%H:%M"):
    #     return True
    # elif datetime.datetime.utcnow().time().strftime("%H:%M") == datetime.time(6,0).strftime("%H:%M"):
    #     return True
    # elif datetime.datetime.utcnow().time().strftime("%H:%M") == datetime.time(12,0).strftime("%H:%M"):
    #     return True
    # elif datetime.datetime.utcnow().time().strftime("%H:%M") == datetime.time(18,0).strftime("%H:%M"):
    #     return True
    # else:
    #     return False

# dictionary to store unscheduled Pods data
unscheduled_pods = {}

# dictionary to store unhealthy Pods data
unhealthy_pods = {}

# dictionary to store evicted pods data
evicted_pods = {}

# dictionary to store list of nodes in nodegroups
nodes_in_nodegroups = {}

# List to store unique list of tainsts of all nodegroups
nodegroups_taints_list = []

# dictionary to store max and desired nodegroups sized based on taints category
nodegroups_taints_dict = {}

# dictionary to store catagorized nodegroups that must be notified about based on taints
nodegroups_taints_notify = {}

# dictionary to store unhealthy nodes data
unhealthy_nodes = {}

# Set the threshold here to notify about the pod that is crashing again and again
restart_count_threshold = 10

# Unschedulable pods and Unhealthy nodes must not be notified immedietly bcz usually thats a temporary issue
notify_delay_seconds = 300

# Cluster Name will be used in nodegroups capacity calculation
cluster_name = CloudformationManager.get_service_stack_name(args.region, args.envName, "Eks")

# ---------------------------------------------------------
# Main logic starts here
# ---------------------------------------------------------
while True:
    # will be used to send message to slack
    slack_message = []

    # will be used to store list of current unhealthy pods/nodes for each loop
    evicted_pod_names = []
    unscheduled_pod_names = []
    unhealthy_pod_names = []
    unhealthy_node_names = []

    # ---------------------------------------------------------
    # List down all unhealthy pods
    # ---------------------------------------------------------

    # Fetching pods from default namespace
    # namespace = "default"
    # pods = k8s_client.list_namespaced_pod(namespace)

    # Fetching pods from all namespaces
    pods = k8s_client.list_pod_for_all_namespaces(watch=False)

    for pod in pods.items:
        # ---------------------------------------------------------
        # List down the Evicted pods
        # ---------------------------------------------------------
        if pod.status.reason == 'Evicted':
            evicted_pod_names.append(pod.metadata.name)

            if pod.metadata.name not in evicted_pods:
                evicted_pods[pod.metadata.name] = {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "message": pod.status.message,
                    "reason": pod.status.reason,
                    "phase": pod.status.phase,
                    "removed": False,
                }

        else:
            if pod.status.conditions is not None:
                for condition in pod.status.conditions:
                    # ---------------------------------------------------------
                    # List down the Unscheduled pods
                    # ---------------------------------------------------------
                    if condition.type == "PodScheduled":
                        if condition.status == "False":
                            unscheduled_pod_names.append(pod.metadata.name)
                            message = None
                            reason = None
                            last_transition_time = 0

                            # Try to get the reason and detail of unscheduled pod from the container state
                            if pod.status.container_statuses is not None:
                                for container in pod.status.container_statuses:
                                    if container.state.waiting is not None:
                                        message = container.state.waiting.message
                                        reason = container.state.waiting.reason
                                    elif container.state.terminated is not None:
                                        message = container.state.terminated.message
                                        reason = container.state.terminated.reason

                            # If couldn't get the reason and detail from above method then fall back to pod's condition
                            if message is None:
                                message = condition.message

                            if reason is None:
                                reason = condition.reason

                            if condition.last_transition_time is not None:
                                last_transition_time = int(condition.last_transition_time.timestamp())

                            # If pod is not already in the unscheduled_pods dict and delay time has passed, add it
                            if pod.metadata.name not in unscheduled_pods and time.time() > last_transition_time + notify_delay_seconds:
                                unscheduled_pods[pod.metadata.name] = {
                                    "name": pod.metadata.name,
                                    "namespace": pod.metadata.namespace,
                                    "message": message,
                                    "reason": reason,
                                    "phase": pod.status.phase,
                                    "notified": False,
                                }

                    # ---------------------------------------------------------
                    # List down the Unhealthy pods
                    # ---------------------------------------------------------
                    if condition.type == "Ready":
                        if condition.status == "False":

                            unhealthy_pod_names.append(pod.metadata.name)

                            message = None
                            reason = None
                            pod_running = False
                            restart_count = 0

                            # Try to get the reason and detail of unhealthy pod from the container state
                            if pod.status.container_statuses is not None:
                                for container in pod.status.container_statuses:
                                    if container.state.waiting is not None:
                                        message = container.state.waiting.message
                                        reason = container.state.waiting.reason
                                        pod_running = False
                                    elif container.state.terminated is not None:
                                        message = container.state.terminated.message
                                        reason = container.state.terminated.reason
                                        pod_running = False
                                    elif container.state.running is not None:
                                        pod_running = True

                                    if container.restart_count is not None:
                                        restart_count = container.restart_count

                            # If couldn't get the reason and detail from above method then fall back to pod's condition
                            if message is None:
                                message = condition.message

                            if reason is None:
                                reason = condition.reason

                            # pod_running is False -> To skip the pods that are running on nodes who's kubelet has stopped
                            # pod.status.phase != "Succeeded" -> to exclude completed jobs' pods
                            # reason != "Completed" -> to exclude pods that have successfully completed their execution (pod replacement phase)
                            # reason != "Error" -> to exclude pods that have successfully completed their execution (pod replacement phase)
                            # reason != "ErrImagePull" -> to exclude multiple notifications for pods that are unable to pull image
                            # reason != "ContainerCreating" -> to exclude pods that have just started execution
                            # reason != "ContainersNotReady" -> to exclude pods that have just started execution
                            # reason != "PodInitializing" -> to exclude pods that have just started execution
                            if pod_running is False and pod.status.phase != "Succeeded" and reason != "Completed" and reason != "Error" and reason != "ErrImagePull" and reason != "ContainerCreating" and reason != "ContainersNotReady" and reason != "PodInitializing":

                                # If a new unhealhy pod is found, add that pod's data in unhealthy_pods dict so that it's notification can be sent
                                if pod.metadata.name not in unhealthy_pods:
                                    unhealthy_pods[pod.metadata.name] = {
                                        "name": pod.metadata.name,
                                        "namespace": pod.metadata.namespace,
                                        "message": message,
                                        "reason": reason,
                                        "phase": pod.status.phase,
                                        "notified": False,
                                        "restart_count": restart_count
                                    }

                                # When restart count threshold is met, update that pod's data in unhealthy_pods dict so that it's notification can be sent
                                if pod.metadata.name in unhealthy_pods and restart_count > restart_count_threshold and unhealthy_pods[pod.metadata.name]['restart_count'] <= restart_count_threshold:
                                    unhealthy_pods[pod.metadata.name] = {
                                        "name": pod.metadata.name,
                                        "namespace": pod.metadata.namespace,
                                        "message": message,
                                        "reason": reason,
                                        "phase": pod.status.phase,
                                        "notified": False,
                                        "restart_count": restart_count
                                    }

                        # This logic take's care of the multiple crashloopbackoff pod's notifications
                        # Even if a pod looks like health, check if it's reason of last termination state
                        if condition.status == "True":

                            message = None
                            reason = None
                            restart_count = 0

                            # Try to get the reason and detail of unhealthy pod from the container last state
                            if pod.status.container_statuses is not None:
                                for container in pod.status.container_statuses:
                                    if container.state.running is not None:
                                        if container.last_state.terminated is not None:
                                            message = container.last_state.terminated.message
                                            reason = container.last_state.terminated.reason

                                    if container.restart_count is not None:
                                        restart_count = container.restart_count


                            # If couldn't get the reason and detail from above method then fall back to pod's condition
                            if message is None:
                                message = condition.message

                            if reason is None:
                                reason = condition.reason

                            # If a container is running right now but there was a last termincation state is associated to it, most probably it's a pod that is in crashloopbackoff state
                            if reason is not None:
                                unhealthy_pod_names.append(pod.metadata.name)

    # ---------------------------------------------------------
    # Notify about the evicted pods
    # ---------------------------------------------------------
    # If there are evicted pods
    if len(evicted_pods) > 0:

        # See if there are pods for which notification hasn't been sent before
        notify_evicted_pods = False
        count_evicted_pods = 0
        for pod in evicted_pods:
            if evicted_pods[pod]['removed'] == False:
                notify_evicted_pods = True
                count_evicted_pods += 1

        # Only notify if there is any evicted pod for which notification hasn't been sent before
        if notify_evicted_pods == True:

            if count_evicted_pods == 1:
                slack_message.append("*Following pod in evicted state has been removed*")
            else:
                slack_message.append("*Following pods in evicted state have been removed*")

            for pod in evicted_pods:
                if evicted_pods[pod]['removed'] == False:

                    # Other then notifying on slack, delete the evicted pods
                    try:
                        k8s_client.delete_namespaced_pod(evicted_pods[pod]['name'], evicted_pods[pod]['namespace'])
                        evicted_pods[pod]['removed'] = True
                    except ApiException as e:
                        print("Exception when calling CoreV1Api->delete_namespaced_pod: %s\n" % e)

                    # At-times reason and details can't be fetched from the pods/nodes, if that's the case, mention it as Unknown
                    if evicted_pods[pod]['reason'] is None:
                        evicted_pods_reason = "Unknown"
                    else:
                        evicted_pods_reason = evicted_pods[pod]['reason']

                    # At-times reason and details can't be fetched from the pods/nodes, if that's the case, mention it as Unknown
                    if evicted_pods[pod]['message'] is None:
                        evicted_pods_detail = "Unknown"
                    else:
                        evicted_pods_detail = evicted_pods[pod]['message']

                    # Append the name of evicted pods to list so that it must be notified on console and on slack as well
                    slack_message.append(f"  - {evicted_pods[pod]['name']} (Reason: {evicted_pods_reason}, Detail: {evicted_pods_detail})")

            slack_message.append("")
        else:
            # Notify on console if there is any evicted pods
            evicted_pods_list = [f"{pod} ({evicted_pods[pod]['reason']})" for pod in evicted_pods]
            logging.warning(f"Evicted pods: {', '.join(evicted_pods_list)}")

    # Remove pods from the dictionary that are now removed
    for pod in list(evicted_pods):
        if pod not in evicted_pod_names:
            evicted_pods.pop(pod)

    # ---------------------------------------------------------
    # Notify about the unscheduled pods
    # ---------------------------------------------------------
    # If there are unscheduled pods
    if len(unscheduled_pods) > 0:

        # Re-send the alert for unscheduled pods
        if renotify() is True:
            for pod in unscheduled_pods:
                if unscheduled_pods[pod]['notified'] == True:
                    unscheduled_pods[pod]['notified'] = False

        # See if there are pods for which notification hasn't been sent before
        notify_unscheduled_pods = False
        count_unscheduled_pods = 0
        for pod in unscheduled_pods:
            if unscheduled_pods[pod]['notified'] == False:
                notify_unscheduled_pods = True
                count_unscheduled_pods += 1

        # Only notify if there is any unscheduled pod for which notification hasn't been sent before
        if notify_unscheduled_pods == True:

            if count_unscheduled_pods == 1:
                slack_message.append("*Following pod can't be scheduled to any node*")
            else:
                slack_message.append("*Following pods can't be scheduled to any node*")

            for pod in unscheduled_pods:
                if unscheduled_pods[pod]['notified'] == False:
                    unscheduled_pods[pod]['notified'] = True

                    # At-times reason and details can't be fetched from the pods/nodes, if that's the case, mention it as Unknown
                    if unscheduled_pods[pod]['reason'] is None:
                        unscheduled_pods_reason = "Unknown"
                    else:
                        unscheduled_pods_reason = unscheduled_pods[pod]['reason']

                    # At-times reason and details can't be fetched from the pods/nodes, if that's the case, mention it as Unknown
                    if unscheduled_pods[pod]['message'] is None:
                        unscheduled_pods_detail = "Unknown"
                    else:
                        unscheduled_pods_detail = unscheduled_pods[pod]['message']

                    # Append the name of unscheduled pods to list so that it must be notified on console and on slack as well
                    slack_message.append(f"  - {unscheduled_pods[pod]['name']} (Reason: {unscheduled_pods_reason}, Detail: {unscheduled_pods_detail})")
            slack_message.append("")

        else:
            # Notify on console if there is any unscheduled pods
            unscheduled_pods_list = [f"{pod} ({unscheduled_pods[pod]['reason']})" for pod in unscheduled_pods]
            logging.warning(f"Unscheduled pods: {', '.join(unscheduled_pods_list)}")

    # Remove pods from the dictionary that are now scheduled
    for pod in list(unscheduled_pods):
        if pod not in unscheduled_pod_names:
            unscheduled_pods.pop(pod)

    # ---------------------------------------------------------
    # Notify about the Unhealthy pods
    # ---------------------------------------------------------
    # Temporary lists to store unhealthey and crashing pod's data that will be added to slack_message (notification message)
    slack_message_unhealthy = []
    slack_message_crashing = []

    # If there are Unhealthy state pods
    if len(unhealthy_pods) > 0:

        # Re-send the alert for unhealthy pods
        if renotify() is True:
            for pod in unhealthy_pods:
                if unhealthy_pods[pod]['notified'] == True:
                    unhealthy_pods[pod]['notified'] = False

        # See if there are pods for which notification hasn't been sent before
        notify_unhealthy_pods = False
        count_unhealthy_pods = 0
        for pod in unhealthy_pods:
            if unhealthy_pods[pod]['notified'] == False:
                notify_unhealthy_pods = True
                count_unhealthy_pods += 1

        # Only notify if there is any Unhealthy state pod for which notification hasn't been sent before
        if notify_unhealthy_pods == True:
                slack_message_crashing_header = 0
                slack_message_unhealthy_header = 0

                for pod in unhealthy_pods:
                    if unhealthy_pods[pod]['notified'] == False:

                        # At-times reason and details can't be fetched from the pods/nodes, if that's the case, mention it as Unknown
                        if unhealthy_pods[pod]['reason'] is None:
                            unhealthy_pods_reason = "Unknown"
                        else:
                            unhealthy_pods_reason = unhealthy_pods[pod]['reason']

                        # At-times reason and details can't be fetched from the pods/nodes, if that's the case, mention it as Unknown
                        if unhealthy_pods[pod]['message'] is None:
                            unhealthy_pods_detail = "Unknown"
                        else:
                            unhealthy_pods_detail = unhealthy_pods[pod]['message']

                        # If the restart count has exceded the threshold, report it seperately
                        if unhealthy_pods[pod]['restart_count'] > restart_count_threshold:
                            if slack_message_crashing_header == 0:
                                slack_message_crashing_header = 1

                                if count_unhealthy_pods == 1:
                                    slack_message_crashing.append(f"*Following pod has crashed more then {restart_count_threshold} times*")
                                else:
                                    slack_message_crashing.append(f"*Following pods have crashed more then {restart_count_threshold} times*")

                            unhealthy_pods[pod]['notified'] = True
                            slack_message_crashing.append(f"  - {unhealthy_pods[pod]['name']} (Crash Count: {unhealthy_pods[pod]['restart_count']}, Reason: {unhealthy_pods_reason}, Detail: {unhealthy_pods_detail})")

                        # If the restart count is less then the threshold, report it just an unhealthy pod
                        if unhealthy_pods[pod]['restart_count'] <= restart_count_threshold:
                            if slack_message_unhealthy_header == 0:
                                slack_message_unhealthy_header = 1

                                if count_unhealthy_pods == 1:
                                    slack_message_unhealthy.append("*Following pod is unhealthy*")
                                else:
                                    slack_message_unhealthy.append("*Following pods are unhealthy*")

                            for pod in unhealthy_pods:
                                if unhealthy_pods[pod]['notified'] == False:
                                    unhealthy_pods[pod]['notified'] = True
                                    slack_message_unhealthy.append(f"  - {unhealthy_pods[pod]['name']} (Reason: {unhealthy_pods_reason}, Detail: {unhealthy_pods_detail})")

                if len(slack_message_crashing) != 0:
                    slack_message.extend(slack_message_crashing)
                    slack_message.append("")

                if len(slack_message_unhealthy) != 0:
                    slack_message.extend(slack_message_unhealthy)
                    slack_message.append("")

        else:
            # Notify on console if there is any unhealthy pods
            unhealthy_pods_list = [f"{pod} ({unhealthy_pods[pod]['reason']})" for pod in unhealthy_pods]
            logging.warning(f"Unhealthy pods: {', '.join(unhealthy_pods_list)}")

    # Remove pods from the dictionary that are now healthy
    for pod in list(unhealthy_pods):
        if pod not in unhealthy_pod_names:
            unhealthy_pods.pop(pod)

    # if all pods are healthy, print the status on console
    if len(evicted_pods) == 0 and len(unhealthy_pods) == 0 and len(unscheduled_pods) == 0:
        logging.info("All pods are healthy")

    # ---------------------------------------------------------
    # List down the unhealthy nodes
    # ---------------------------------------------------------
    nodes = k8s_client.list_node(watch=False)
    ec2_client = boto3.client('eks', region_name = 'eu-west-1')

    for node in nodes.items:
        unhealthy_node_names.append(node.metadata.name)

        for nodeStatus in node.status.conditions:

            # if ready condition of node is has a status that depicts that node is unhealthy, consider the node unhealthy
            if nodeStatus.type == 'Ready':
                if nodeStatus.status == ('Unknown' or 'NotReady'):

                    last_transition_time = 0
                    if nodeStatus.last_transition_time is not None:
                        last_transition_time = int(nodeStatus.last_transition_time.timestamp())

                    if node.metadata.name not in unhealthy_nodes and time.time() > last_transition_time + notify_delay_seconds:
                        unhealthy_nodes[node.metadata.name] = {
                            "instance_id": node.spec.provider_id.split('/')[-1],
                            "name": node.metadata.name,
                            "status": nodeStatus.status,
                            "reason": nodeStatus.reason,
                            "message": nodeStatus.message,
                            "notified": False,
                        }
                else:
                    if node.metadata.name in unhealthy_nodes:
                        unhealthy_nodes.pop(node.metadata.name)

    # ---------------------------------------------------------
    # Notify about the unhealthy nodes
    # ---------------------------------------------------------
    # If there are unhealthy nodes
    if len(unhealthy_nodes) > 0:

        # Re-send the alert for unhealthy nodes
        if renotify() is True:
            for node in unhealthy_nodes:
                if unhealthy_nodes[node]['notified'] == True:
                    unhealthy_nodes[node]['notified'] = False

        # See if there are nodes for which notification hasn't been sent before
        notify_unhealthy_nodes = False
        count_notify_unhealthy_nodes = 0
        for node in unhealthy_nodes:
            if unhealthy_nodes[node]['notified'] == False:
                notify_unhealthy_nodes = True
                count_notify_unhealthy_nodes += 1

        # Only notify if there is any unscheduled node for which notification hasn't been sent before
        if notify_unhealthy_nodes == True:

            # At-times reason and details can't be fetched from the pods/nodes, if that's the case, mention it as Unknown
            if unhealthy_nodes[node]['reason'] is None:
                unhealthy_nodes_reason = "Unknown"
            else:
                unhealthy_nodes_reason = unhealthy_nodes[node]['reason']

            # At-times reason and details can't be fetched from the pods/nodes, if that's the case, mention it as Unknown
            if unhealthy_nodes[node]['message'] is None:
                unhealthy_nodes_detail = "Unknown"
            else:
                unhealthy_nodes_detail = unhealthy_nodes[node]['message']

            if count_notify_unhealthy_nodes == 1:
                slack_message.append("*Following EKS node is unhealthy*")
            else:
                slack_message.append("*Following EKS nodes are unhealthy*")

            for node in unhealthy_nodes:
                if unhealthy_nodes[node]['notified'] == False:
                    unhealthy_nodes[node]['notified'] = True
                    slack_message.append(f"  - {unhealthy_nodes[node]['name']} (Instance ID: {unhealthy_nodes[node]['instance_id']}, Reason: {unhealthy_nodes_reason}, Detail: {unhealthy_nodes_detail})")
            slack_message.append("")

        else:
            # Notify on console if there is any unhealthy pods
            unhealthy_nodes_notify_list = [f"{unhealthy_nodes[node]['name']} (Instance ID: {unhealthy_nodes[node]['instance_id']}, Reason: {unhealthy_nodes_reason}, Detail: {unhealthy_nodes_detail})" for node in unhealthy_nodes]
            logging.warning(f"Unhealthy nodes: {', '.join(unhealthy_nodes_notify_list)}")

    else:
        logging.info("All EKS nodes are healthy")

    # Remove nodes from the dictionary that are now healthy
    for node in list(unhealthy_nodes):
        if node not in unhealthy_node_names:
            unhealthy_nodes.pop(node)

    # ---------------------------------------------------------
    # List down difference between maximum and current nodes
    # ---------------------------------------------------------
    # Get the list of all nodegroups
    eks_client = boto3.client('eks', region_name = args.region)
    list_nodegroups_resp = eks_client.list_nodegroups(
        clusterName=cluster_name,
    )

    # Parse the name, taints, maxSize and desiredSize of all nodegroups
    for nodegroup in list_nodegroups_resp['nodegroups']:
        taints = []
        maxSize = None
        desiredSize = None

        describe_nodegroup_resp = eks_client.describe_nodegroup(
            clusterName=cluster_name,
            nodegroupName=nodegroup
        )

        for key in describe_nodegroup_resp['nodegroup']['scalingConfig']:
            if key == 'maxSize':
                maxSize = describe_nodegroup_resp['nodegroup']['scalingConfig'][key]

            if key == 'desiredSize':
                desiredSize = describe_nodegroup_resp['nodegroup']['scalingConfig'][key]

        if 'taints' in describe_nodegroup_resp['nodegroup'].keys():
            for taint in describe_nodegroup_resp['nodegroup']['taints']:
                # taints.append(f"{taint['key']}:{taint['value']}")

                if taint['key'] == 'SpotInstance' and taint['value'] == 'true':
                    taints.append("None")
                    break
                else:
                    taints.append(f"{taint['key']}:{taint['value']}")
        else:
            taints.append("None")

        nodes_in_nodegroups[nodegroup] = {
            "name": nodegroup,
            "taints": ', '.join(taints),
            "maxSize": maxSize,
            "desiredSize": desiredSize
        }

    # Get the unique list of tainsts of all nodegroups
    for nodegroup in nodes_in_nodegroups:
        taints = nodes_in_nodegroups[nodegroup]['taints']
        if taints not in nodegroups_taints_list:
            nodegroups_taints_list.append(taints)

    # For each unique taint, calculate the max and desired nodegroup size
    for taint in nodegroups_taints_list:
        nodegroups_taints_dict[taint] = {}
        desiredSize = 0
        maxSize = 0
        name = []
        for nodegroup in nodes_in_nodegroups:
            if nodes_in_nodegroups[nodegroup]['taints'] == taint:
                desiredSize += nodes_in_nodegroups[nodegroup]['desiredSize']
                maxSize += nodes_in_nodegroups[nodegroup]['maxSize']
                name.append(nodes_in_nodegroups[nodegroup]['name'])

                nodegroups_taints_dict[taint] = {
                    "desiredSize": desiredSize,
                    "maxSize": maxSize,
                    "name": ', '.join(name),
                }

    # Logic to see if the category of nodegroup (based on taints) is at full capacity or not
    for taint in nodegroups_taints_dict:
        if nodegroups_taints_dict[taint]['desiredSize'] == nodegroups_taints_dict[taint]['maxSize']:
            if taint not in nodegroups_taints_notify:
                nodegroups_taints_notify[taint] = {
                    "name": nodegroups_taints_dict[taint]['name'],
                    "desiredSize": nodegroups_taints_dict[taint]['desiredSize'],
                    "maxSize": nodegroups_taints_dict[taint]['maxSize'],
                    "notified": False
                }
        elif nodegroups_taints_dict[taint]['desiredSize'] < nodegroups_taints_dict[taint]['maxSize']:
            if taint in nodegroups_taints_notify:
                nodegroups_taints_notify.pop(taint)

    # ---------------------------------------------------------
    # Notify about the nodegroups
    # ---------------------------------------------------------
    # If there are nodegroups at full capacity
    if len(nodegroups_taints_notify) > 0:

        # Re-send the alert for unhealthy nodegroups
        if renotify() is True:
            for nodegroup in nodegroups_taints_notify:
                if nodegroups_taints_notify[nodegroup]['notified'] == True:
                    nodegroups_taints_notify[nodegroup]['notified'] = False

        # See if there are nodegroups for which notification hasn't been sent before
        notify_full_capacity_nodegroups = False
        count_full_capacity_nodegroups = 0
        for nodegroup in nodegroups_taints_notify:
            if nodegroups_taints_notify[nodegroup]['notified'] == False:
                notify_full_capacity_nodegroups = True
                count_full_capacity_nodegroups += 1

        # Only notify if there is any full capacity nodegroups for which notification hasn't been sent before
        if notify_full_capacity_nodegroups == True:

            if count_full_capacity_nodegroups == 1:
                slack_message.append("*Following EKS nodegroup is at full capacity*")
            else:
                slack_message.append("*Following EKS nodegroups are at full capacity*")

            for nodegroup in nodegroups_taints_notify:
                if nodegroups_taints_notify[nodegroup]['notified'] == False:
                    nodegroups_taints_notify[nodegroup]['notified'] = True
                    slack_message.append(f"  - {nodegroups_taints_notify[nodegroup]['name']} (Maximum allowed EC2 nodes: {nodegroups_taints_notify[nodegroup]['maxSize']}, Current EC2 nodes: {nodegroups_taints_notify[nodegroup]['desiredSize']})")
            slack_message.append("")

        else:
            # Notify on console if there is any unhealthy pods
            nodegroups_taints_notify_list = [f"{nodegroups_taints_notify[nodegroup]['name']} ({nodegroups_taints_notify[nodegroup]['desiredSize']}/{nodegroups_taints_notify[nodegroup]['maxSize']})" for nodegroup in nodegroups_taints_notify]
            logging.warning(f"Full capacity nodegroups: {', '.join(nodegroups_taints_notify_list)}")

    else:
        logging.info("All EKS nodegroups are healthy")

    # If there are unhealthy pods/nodes, the send the notification to slack and console
    if len(slack_message) != 0:
        print("")
        logging.warning("\n".join(slack_message))
        send_slack_message(slack_message)
    else:
        print("")

    # Repeat the process. Decreasing it below 60 sec will send 2 notifications at re-notification time
    time.sleep(60)
