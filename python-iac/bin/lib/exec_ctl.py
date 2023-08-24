import subprocess

def sub_process(command):
    # check if command is a string
    if isinstance(command, str):
        command = command.split()
    print(command)

    process = subprocess.Popen(command, stdout=subprocess.PIPE, universal_newlines=True)
    process.wait()

    output, error = process.communicate()
    if error:
        return error
    else:
        return output

# https://gist.github.com/jotaelesalinas/f809d702e4d3e24b19b77b83c9bf5d9e
def sub_process_rc(command):
    # check if command is a string
    if isinstance(command, str):
        command = command.split()
    print(command)

    process = subprocess.Popen(command, stdout=subprocess.PIPE, universal_newlines=True)
    process.wait()

    output, error = process.communicate()

    if error is not None:
        return process.returncode, error
    else:
        return process.returncode, output
