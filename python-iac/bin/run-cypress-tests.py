#!/usr/bin/python
"""
Tool to get secrets from a jenkins job

Example:
python3 -u ./tools/jenkins/run-cypress-tests.py
    --envName ${ENVIRONMENT}
    --serviceName "cypress.io/${CYPRESS_PROJECT_ID}"
    --region ${AWS_REGION}

Where the Jenkins config specifies the:
 ENVIRONMENT [develop/main]
 AWS_REGION

 Used in this job: @link http://jenkins.reptrak.io:8080/job/cypress.io-tests/

"""
import argparse
import json
import os
import re
from subprocess import PIPE, Popen, STDOUT

import lib.exec_ctl as exe
import lib.params as params
import lib.secrets_manager as secrets

parser = argparse.ArgumentParser()
parser.add_argument('--region', help='Secrets manager destination region')
parser.add_argument('--serviceName', help='Service name in Secrets Manager')
parser.add_argument('--envName', help='Destination environment prefix name')
args = parser.parse_args()

if args.region is None:
    params.load_params_mem(args.envName)
    region = os.environ["Region"]
else:
    region = args.region

secretName = args.envName + '/' + args.serviceName
print(f'Fetching secrets for {secretName}', flush=True)

# get_secrets_list[Dict] Values: {
#   'CYPRESS_PROJECT_KEY': 'xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
#   'AWS_DOWNSTREAM_SECRET_KEY': 'react-communications',
#   'TESTS_SOURCE_CODE': 'git@github.com:RepTrak/react-communications.git'
# }
try:
    cypress_suite_secrets = json.loads(secrets.get_secret(secretName, region))
except Exception as error:
    print(f"Err fetching secrets. Please re-run aws-azure-login and try again.", flush=True)
    print(error)
    exit(1)
# print(cypress_suite_secrets, flush = True)

downstream_secrets_list_aws_value = args.envName + '/' + cypress_suite_secrets[
    'AWS_DOWNSTREAM_SECRET_KEY']
# Now we fetch the service under-test's Secrets

downstream_secrets_list = json.loads(secrets.get_secret(downstream_secrets_list_aws_value, region))
if not re.match('(?:https)://', downstream_secrets_list['CYPRESS_TESTING_HOST']):
    print(f"ERROR: Protocol missing from the downstream projects secrets, in AWS Secrets: " +
          downstream_secrets_list_aws_value +
          "\n\nPlease update the project to "
          "use a fully qualified URL (including protocol: HTTPS)")
    exit(9)

# print(downstream_secrets_list, flush = True)

# Clean up / make this locally idempotent
if os.path.exists('repo-under-test/'):
    import shutil

    shutil.rmtree('repo-under-test/')

# git-clone the repo-under-test
exe.sub_process(
    f"git clone --progress  {cypress_suite_secrets['TESTS_SOURCE_CODE']} repo-under-test/")

# In the checked out code -- do some sanity checking ✅
#   we should require a cypress.json to be
#   present for project level overrides at the project root path
if not os.path.exists('repo-under-test/cypress.json'):
    print(
        f"The repository being tested {cypress_suite_secrets['TESTS_SOURCE_CODE']} doesn't have a "
        f"cypress.config in it. Please create one and re-run the testing pipeline. "
        f"@Link https://docs.cypress.io/guides/references/configuration ", flush=True)

os.chdir('./repo-under-test')

# Check cypress support in repo
if os.path.exists('cypress.json'):
    print("Setting cypress config", flush=True)
    cy_conf = json.load(open('cypress.json', 'r'))
    cy_conf['projectId'] = (args.serviceName.split('/'))[1]
    cy_conf['baseUrl'] = f'{downstream_secrets_list["CYPRESS_TESTING_HOST"]}'
    print("Cypress config set to: " + json.dumps(cy_conf))
    json.dump(cy_conf, open('cypress.json', 'w'))

    if "CYPRESS_FIXTURE_DATA" in cypress_suite_secrets:
        print('Secret ('+secretName+') contain CYPRESS_FIXTURE_DATA, writing to the '
                                    'repo-under-test')
        json.dump(cypress_suite_secrets["CYPRESS_FIXTURE_DATA"],
                  open('cypress/fixtures/user.json', 'w'))
    else:
        print('Project Secrets ('+secretName+') does not have CYPRESS_FIXTURE_DATA\n')
        print('Create a JSON object with the key CYPRESS_FIXTURE_DATA, and this will be injected')
        print('into the repo-under-test/cypress/fixtures/data.json path to enable testing '
              'sensitive data')
else:
    print("Unknown repo to test -- PR's Welcome 🎉 to add support!")
    exit(9)


# RUN + Record the tests 🎥
# This runs from the react-comms path
cmd = f"docker run -v $PWD:/e2e -w /e2e " \
      f"-e CYPRESS_baseUrl='{downstream_secrets_list['CYPRESS_TESTING_HOST']}' "\
      f"-e CYPRESS_RECORD_KEY={cypress_suite_secrets['CYPRESS_PROJECT_KEY']} " \
      f"cypress/included:3.2.0 --record"
print(cmd)
npx_runner = os.popen(cmd)
print(npx_runner.read(), flush=True)

# TODO Slack message with failed screen recording/images?

exit(0)