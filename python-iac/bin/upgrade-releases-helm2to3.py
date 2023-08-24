from subprocess import Popen, PIPE
import lib.exec_ctl as exe

command = "helm3 2to3 move config --skip-confirmation"
output = exe.sub_process(command)
print(output)

# Bash alternate for pipe command "helm list --short --all | grep -v alb-ingress-controller"
p1 = Popen(["helm", "list", "--short", "--all"], stdout=PIPE)
p2 = Popen(["grep", "-v", "alb-ingress-controller"], stdin=p1.stdout, stdout=PIPE)
helm_charts = p2.stdout.read().decode('UTF-8')
print(helm_charts)

print("Upgrading all helm charts")
for chart in helm_charts.split():
    command = "helm3 2to3 convert " + chart + " --delete-v2-releases --ignore-already-migrated"
    output = exe.sub_process(command)
    print(output)

command = "helm3 2to3 convert alb-ingress-controller --delete-v2-releases --ignore-already-migrated"
output = exe.sub_process(command)
print(output)

command = "helm3 2to3 cleanup --skip-confirmation"
output = exe.sub_process(command)
print(output)
