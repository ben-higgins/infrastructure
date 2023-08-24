import boto3
import lib.exec_ctl as exe
import time

def update_kubeconfig(clusterName, region):
    client = boto3.client('cloudformation', region_name=region)

    response = client.describe_stacks(StackName=clusterName)
    outputs = response["Stacks"][0]["Outputs"]
    for output in outputs:
        if output["OutputKey"] == "EKSConfig":
            print("updating local kube config file: " + output["OutputValue"])
            command = output["OutputValue"]
            exe.sub_process(command)
            time.sleep(10)