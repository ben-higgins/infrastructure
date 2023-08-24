import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--envName", required = False, nargs='?', const='', help = "Environment name equals environment to deploy to")
parser.add_argument("--branchName", required = True, nargs='?', const='', help="Service branch name")
args = parser.parse_args()

def read_gittag_param(parsedEnvName):
    paramFile = "./params/" + parsedEnvName + "/gittag.params"

    with open(paramFile, "r") as file:
        for line in file:
            if line.strip() and not line.startswith('#'):
                linesplit = line.split(':', 1)
                gittag = linesplit[1].strip()
    return gittag

def parse_branch_name(branch_raw):
    # value might come in with a prefix
    if branch_raw.find("/") != -1:
        branch = branch_raw.split("/")[-1]
    else:
        branch = branch_raw
    return branch

if args.envName:
    # environment override triggered
    response = read_gittag_param(args.envName)
else:
    branch_name = parse_branch_name(args.branchName)
    response = read_gittag_param(branch_name)


print(response)
