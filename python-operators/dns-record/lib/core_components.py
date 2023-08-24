import functools
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import boto3
from boto3.resources.base import ServiceResource

from .logger import logging


def decorator(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        logging.debug(f"{f.__name__}: [{args}] [{kwargs}]")
        return f(*args, **kwargs)

    return wrapper


class AwsClientFactory:
    __client: Dict[str, boto3.session.Session.client] = {}
    __resource: Dict[str, ServiceResource] = {}

    @classmethod
    def get_client(cls, region: str, service: str) -> boto3.session.Session.client:
        client_key = f"{region}-{service}"
        if client_key not in cls.__client:
            cls.__client[client_key] = boto3.client(service, region_name=region)
        return cls.__client[client_key]

    @classmethod
    def get_resource(cls, region: str, resource: str) -> ServiceResource:
        resource_key = f"{region}-{resource}"
        if resource_key not in cls.__resource:
            cls.__resource[resource_key] = boto3.resource(resource, region_name=region)
        return cls.__resource[resource_key]


class AwsServiceManager:
    __client: Dict[str, boto3.session.Session.client] = {}
    __resource: Dict[str, ServiceResource] = {}
    factory = AwsClientFactory
    service: str = None

    @classmethod
    def get_client(cls, region) -> boto3.session.Session.client:
        if not cls.service:
            raise Exception("Service not defined. Please set this property in your class")

        client_key = f"{region}-{cls.service}"
        if client_key not in cls.__client:
            cls.__client[client_key] = cls.factory.get_client(region, cls.service)
        return cls.__client[client_key]

    @classmethod
    def get_resource(cls, region) -> boto3.session.Session.client:
        if not cls.service:
            raise Exception("Service not defined. Please set this property in your class")

        client_key = f"{region}-{cls.service}"
        if client_key not in cls.__resource:
            cls.__resource[client_key] = cls.factory.get_resource(region, cls.service)
        return cls.__resource[client_key]


class AwsInfrastructureServiceDeployer(ABC):
    deployed: bool = False

    def __init__(self, environment_name: str, region: str, environment: Dict[str, str]):
        self.environment = environment
        self.environment_name = environment_name
        self.region = region

    def __getattribute__(self, item):
        value = object.__getattribute__(self, item)
        if callable(value):
            return decorator(value)
        return value

    @abstractmethod
    def build_params(self, cloudformation_parameters: Optional[List[Dict[str, str]]] = []):
        pass

    @abstractmethod
    def build_params_for_stack(self, stack_name: str, cloudformation_parameters: Optional[List[Dict[str, str]]] = []):
        pass

    @abstractmethod
    def pre_delete(self):
        pass

    @abstractmethod
    def post_delete(self):
        pass

    @abstractmethod
    def pre_build(self):
        pass

    @abstractmethod
    def post_build(self):
        pass

    @abstractmethod
    def pre_update(self):
        pass

    @abstractmethod
    def post_update(self):
        pass
