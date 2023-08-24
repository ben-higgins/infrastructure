#!/usr/bin/python

import argparse
import json
import os

import sqlalchemy

import lib.cloudformation as cloudformation
import lib.params as parameters
import lib.redshift as redshift
from lib.secrets_manager import get_secret, get_secrets_by_filters

ap = argparse.ArgumentParser()
ap.add_argument("--action", required=True,
                default='set-master-pw',
                help="Required: set the action to trigger")
ap.add_argument("--envName", required=True,
                help="Required: Environment name equals environment to deploy to")
ap.add_argument("--gitHash", required=True,
                help="Required: Git branch hash for deployment distinction")
ap.add_argument('--destRegion', help='Secrets manager destination region', default=None)

args = vars(ap.parse_args())


def do_action():
    os.environ["Name"] = args["envName"]
    dest_region = os.getenv("Region", default=None)
    if args["destRegion"] is not None:
        dest_region = args["destRegion"]
    # prepare params - need params from files
    params = parameters.load_params_mem(args["envName"], dest_region)

    # check if exists
    stackName = cloudformation.stack_exist(os.environ["Name"], os.environ["Region"])

    # build if stackName doesn't exist
    if stackName is None:
        print('Stack Not Exists!')
        exit(2)

    details = cloudformation.stack_details(os.environ["Name"], os.environ["Region"])

    if os.environ["DeployRedshift"] != 'true':
        print('Redshift is disabled in the config of the environment')
        exit(3)

    _stack = details['Stacks'][0]
    _stack_name = _stack['StackName']
    _secret_redshift_arn: str = '//'
    for _o, output in enumerate(_stack['Outputs']):
        if output['OutputKey'] == 'Redshift':
            _secret_redshift_arn = output['OutputValue']

    _secret_redshift_arn_parts = _secret_redshift_arn.split('/')

    if _secret_redshift_arn_parts[1] != '':
        _redshift_stack_name = _secret_redshift_arn_parts[1]
        _redshift_stack_details = cloudformation.stack_details(_redshift_stack_name, os.environ["Region"])
        _cluster_id = None
        redshift_cluster_endpoint = None
        _redshift_stack = _redshift_stack_details['Stacks'][0]
        for _o, output in enumerate(_redshift_stack['Outputs']):
            if output['OutputKey'] == 'ClusterName':
                _cluster_id = output['OutputValue']
            if output['OutputKey'] == 'RedshiftClusterEndpoint':
                redshift_cluster_endpoint = output['OutputValue']

        if args["action"] == "set-master-pw":
            _master_secret_key = f'database/redshift/{_redshift_stack_name}/rds'
            _secrets = json.loads(get_secret(_master_secret_key, os.environ.get('Region')))
            redshift.set_cluster_master_password(_cluster_id, os.environ.get('Region'), _secrets['password'])

        if args["action"] == "set-operational-users":
            _master_secret_key = f'database/redshift/{_redshift_stack_name}/rds'
            _secrets = json.loads(get_secret(_master_secret_key, os.environ.get('Region')))

            db_client = redshift.get_database_client(_secrets['username'], _secrets['password'], redshift_cluster_endpoint)

            with db_client.connect() as connection:
                resultproxy = connection.execute(redshift.QUERIES.get('get_users_and_groups'))

            users_in_db = [dict(row) for row in resultproxy]

            operational_users_secrets = get_secrets_by_filters([
                    {
                            'Key':    'tag-value',
                            'Values': [_redshift_stack_name]
                            },
                    {
                            'Key':    'tag-value',
                            'Values': ['operational-user']
                            },
                    {
                            'Key':    'tag-key',
                            'Values': ['aws:cloudformation:stack-name']
                            },
                    {
                            'Key':    'tag-key',
                            'Values': ['user-type']
                            },
                    ], os.environ.get('Region'))

            secrets_list = operational_users_secrets['SecretList']

            for secret_user_data in secrets_list:
                name_parts = secret_user_data['Name'].split('/')
                name_parts.reverse()
                set_operational_user(_redshift_stack_name, db_client, name_parts[0], users_in_db)

        exit(0)


def set_operational_user(_redshift_stack_name, db_client, operational_user, users_in_db):
    operation_secret_key = f'database/redshift/{_redshift_stack_name}/{operational_user}'
    _operation_secrets = json.loads(get_secret(operation_secret_key, os.environ.get('Region')))
    found = False
    for user in users_in_db:
        if user['username'] == operational_user:
            found = True
    if not found:
        with db_client.connect() as connection:
            try:
                print(f'Creating user "{_operation_secrets["username"]}"')
                connection.execute(
                        redshift.QUERIES.get('create_user').format(user=_operation_secrets['username'],
                                                                   passwd=_operation_secrets['password']))
            except sqlalchemy.exc.ProgrammingError as e:
                if f'user "{_operation_secrets["username"]}" already exists' in e.orig.__str__():
                    print('This user seems to exists but was created for another admin!')
                    print('Updating...')
                    connection.execute(
                            redshift.QUERIES.get('alter_user').format(user=_operation_secrets['username'],
                                                                      passwd=_operation_secrets['password']))
            print(f'Setting groups')
            user_groups = _operation_secrets['groups'].split(',')
            for user_group in user_groups:
                connection.execute(
                        redshift.QUERIES.get('add_user_to_group').format(user=_operation_secrets['username'], group=user_group))
    else:
        with db_client.connect() as connection:
            print(f'Updating user "{_operation_secrets["username"]}"')
            connection.execute(
                    redshift.QUERIES.get('alter_user').format(user=_operation_secrets['username'],
                                                              passwd=_operation_secrets['password']))
            print(f'Setting groups')
            user_groups = _operation_secrets['groups'].split(',')
            for user_group in user_groups:
                connection.execute(
                        redshift.QUERIES.get('add_user_to_group').format(user=_operation_secrets['username'], group=user_group))


do_action()
