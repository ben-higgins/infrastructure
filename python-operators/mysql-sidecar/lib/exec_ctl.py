import subprocess

def sub_process(command):
    # check if command is a string
    if isinstance(command, str):
        command = command.split()
    print(command)

    process = subprocess.Popen(command, stdout=subprocess.PIPE, universal_newlines=True)
    process.wait()

    output, error = process.communicate()
    if error is not None:
        return error
    else:
        return output
