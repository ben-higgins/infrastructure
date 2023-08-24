import os

def load_params_mem(envName, region):
    params = []
    dir = "./params/" + envName + "/" + region + "/"
    for filename in os.listdir(dir):
        try:
            file = open(dir + filename)
            for line in file:
                if line.strip() and not line.startswith('#'):
                    linesplit = line.split(':', 1)
                    #set env
                    os.environ[linesplit[0].strip()] = linesplit[1].strip()
        finally:
            file.close()

    params.append({'ParameterKey': 'Region', 'ParameterValue': region})

    os.environ["Name"] = envName
    os.environ["Region"] = region

def build_params(envName):
    params = []
    dir = "./params/" + envName + "/"
    for filename in os.listdir(dir):
        try:
            file = open(dir + filename)
            for line in file:
                if line.strip() and not line.startswith('#'):
                    linesplit = line.split(':', 1)
                    params.append({'ParameterKey': linesplit[0].strip(), 'ParameterValue': linesplit[1].strip()})
        finally:
            file.close()

    return params

def get_region_helm(jobName):
    param = ""
    dir = "../" + jobName +  "/.helm/deployment_chart/values.yaml"

    file = open(dir)
    for line in file:
        if line.strip() and not line.startswith('#'):
            linesplit = line.split(':', 1)
            if linesplit[0].strip() == "region":
                param = linesplit[1].strip()

    file.close()

    return param
