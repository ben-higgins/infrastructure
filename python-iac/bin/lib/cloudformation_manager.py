from typing import Any, Dict, List

from .core_components import AwsServiceManager


class CloudformationManager(AwsServiceManager):
    service = "cloudformation"
    PROTECTED_ENVS = ["main"]

    @classmethod
    def stack_status(cls, region: str, stack_name: str):
        client = cls.get_client(region)
        try:
            response = client.describe_stacks(StackName=stack_name)
            results = response["Stacks"][0]["StackStatus"]
        except Exception:
            results = "DELETED"
        return results

    @classmethod
    def get_service_stack_name(cls, region, environment: str, service_name: str) -> str:
        response = cls.get_available_stacks(region)

        for key in response["StackSummaries"]:
            if f"{environment}-{service_name}" in key["StackName"]:
                return key["StackName"]

        raise Exception(f"No cloudformation stack found in {region} region for service {service_name}")

    @classmethod
    def describe_stacks(cls, region, stack_name: str) -> Dict[str, Any]:
        client = cls.get_client(region)
        return client.describe_stacks(StackName=stack_name)

    @classmethod
    def describe_stack(cls, region, stack_name: str) -> Dict[str, Any]:
        client = cls.get_client(region)
        return client.describe_stacks(StackName=stack_name)["Stacks"][0]

    @classmethod
    def get_stack_outputs(cls, region, stack_name: str) -> List[Dict[str, Any]]:
        response = cls.describe_stacks(region, stack_name)
        return response["Stacks"][0]["Outputs"]

    @classmethod
    def get_available_stacks(cls, region):
        client = cls.get_client(region)
        response = client.list_stacks(
            StackStatusFilter=[
                "CREATE_COMPLETE",
                "ROLLBACK_FAILED",
                "ROLLBACK_COMPLETE",
                "UPDATE_COMPLETE",
                "UPDATE_ROLLBACK_COMPLETE",
            ]
        )

        if len(response["StackSummaries"]) == 0:
            raise Exception("No cloudformation stack found in " + region + " region")

        return response

    @classmethod
    def stack_exist(cls, region, env_name):
        client = cls.get_client(region)
        response = client.list_stacks(
            StackStatusFilter=[
                "CREATE_COMPLETE",
                "ROLLBACK_IN_PROGRESS",
                "ROLLBACK_FAILED",
                "ROLLBACK_COMPLETE",
                "UPDATE_IN_PROGRESS",
                "UPDATE_COMPLETE",
                "UPDATE_ROLLBACK_FAILED",
                "UPDATE_ROLLBACK_COMPLETE",
            ]
        )

        stack_list = response["StackSummaries"]
        for item in stack_list:
            if env_name == item["StackName"]:
                return item["StackName"]

        return None

    @classmethod
    def create_stack(cls, region: str, env_name: str, template: str, params: List[Dict[str, str]], env_type: str):
        client = cls.get_client(region)

        # prevent main branch deployments from being deleted
        protect = False
        if env_name in cls.PROTECTED_ENVS:
            protect = True

        return client.create_stack(
            StackName=env_name,
            TemplateURL=template,
            Parameters=params,
            DisableRollback=True,
            Capabilities=["CAPABILITY_NAMED_IAM"],
            Tags=[{"Key": "Environment", "Value": env_type}],
            EnableTerminationProtection=protect,
        )

    @classmethod
    def update_stack(cls, region, env_name, template, params):
        client = cls.get_client(region)
        return client.update_stack(
            StackName=env_name,
            TemplateURL=template,
            UsePreviousTemplate=False,
            Parameters=params,
            Capabilities=["CAPABILITY_NAMED_IAM"],
        )

    @classmethod
    def create_change_set(cls, region: str, env_name: str, template: str, params: List[Dict[str, str]], env_type: str):
        client = cls.get_client(region)

        return client.create_change_set(
            StackName=env_name,
            ChangeSetName=env_name,
            TemplateURL=template,
            IncludeNestedStacks=True,
            Parameters=params,
            Capabilities=["CAPABILITY_NAMED_IAM"],
            Tags=[{"Key": "Environment", "Value": env_type}],
        )

    @classmethod
    def change_set_status(cls, region: str, stack_name: str, change_set_name: str):
        client = cls.get_client(region)
        try:
            response = client.describe_change_set(StackName=stack_name,ChangeSetName=change_set_name)
            results = response["Status"]
        except Exception:
            results = "N/A"
        return results

    @classmethod
    def change_set_status_reason(cls, region: str, stack_name: str, change_set_name: str):
        client = cls.get_client(region)
        try:
            response = client.describe_change_set(StackName=stack_name,ChangeSetName=change_set_name)
            results = response["StatusReason"]
        except Exception:
            results = "N/A"
        return results

    @classmethod
    def change_set_status_changes(cls, region: str, stack_name: str, change_set_name: str):
        client = cls.get_client(region)
        try:
            response = client.describe_change_set(StackName=stack_name,ChangeSetName=change_set_name)
            results = response["Changes"]
        except Exception:
            results = "N/A"
        return results

    @classmethod
    def execute_change_set(cls, region: str, stack_name: str, change_set_name: str):
        client = cls.get_client(region)

        return client.execute_change_set(StackName=stack_name,ChangeSetName=change_set_name)

    @classmethod
    def delete_change_set(cls, region: str, stack_name: str, change_set_name: str):
        client = cls.get_client(region)
        try:
            response = client.delete_change_set(StackName=stack_name,ChangeSetName=change_set_name)
            if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                 results = "DELETED"
        except Exception:
            results = "N/A"
            raise
        return results

    @classmethod
    def delete_stack(cls, region, env_name):
        client = cls.get_client(region)
        return client.delete_stack(StackName=env_name)
