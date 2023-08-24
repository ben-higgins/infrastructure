import json
import pipes
from typing import Callable, Dict, Iterable, Optional

import docker
from docker.errors import APIError, DockerException

from .logger import logging


class DockerManager:
    __client: docker.DockerClient = None
    debug: bool = False

    @classmethod
    def __get_client(
        cls, version: str = "auto", base_url: Optional[str] = "unix://var/run/docker.sock", *args, **kwargs
    ) -> docker.DockerClient:
        if not cls.__client:
            if base_url:
                cls.__client = docker.DockerClient(base_url=base_url, version=version, *args, **kwargs)
                logging.info(f"Creating docker client from url {base_url}. Version info: [{cls.__client.version()}]")
            else:
                cls.__client = docker.from_env(version="auto", **kwargs)
                logging.info(f"Creating docker client from environment. Version info: [{cls.__client.version()}]")

        return cls.__client

    @classmethod
    def print_docker_build_log(cls, log: Iterable, print_callback: Callable = logging.info):
        while True:
            try:
                item = next(log)
                print_callback(item)
            except StopIteration:
                break

    @classmethod
    def push_image(cls, repository_name: str, auth_config: Dict[str, str]):
        docker_client = cls.__get_client()
        log = docker_client.images.push(repository_name, auth_config=auth_config)
        logging.info(log)

    @classmethod
    def login(cls, username: str, password: str, registry: str):
        docker_client = cls.__get_client()
        docker_client.login(username=username, password=password, registry=registry)

    @classmethod
    def build_image(
        cls,
        path: str,
        tag: str,
        buildargs: Dict[str, str] = {},
        rm: bool = True,
        *args,
        **kwargs,
    ):
        docker_client = cls.__get_client()

        # buildargs_scape_values = {
        #     secret_key: json.dumps(buildargs[secret_key]).strip('"') for secret_key in buildargs.keys()
        # }

        buildargs_scape_values = {secret_key: str(buildargs[secret_key]) for secret_key in buildargs.keys()}

        try:
            logging.info(f"Building image {tag} from path {path}")
            image, build_log = docker_client.images.build(
                path=path, tag=tag, rm=rm, buildargs=buildargs_scape_values, *args, **kwargs
            )
            if cls.debug:
                cls.print_docker_build_log(build_log, logging.info)
        except APIError as e:
            logging.critical(
                f"ApiError: {e.explanation}. Request: {e.request.request}. Buildargs: [{buildargs_scape_values}]"
            )
            raise e
        except DockerException as e:
            if hasattr(e, "build_log"):
                cls.print_docker_build_log(e.build_log, logging.critical)
            logging.critical(f"DockerException Buildargs: [{buildargs_scape_values}]")
            raise e
        except Exception as e:
            logging.critical(f"General error: {e}. Buildargs: [{buildargs_scape_values}]")
            raise e

        return image
