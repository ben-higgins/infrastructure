#
# Helper functions
#

determine_my_ip () {
  curl ipinfo.io/ip 2>/dev/null || wget -qO- ipinfo.io/ip 2>/dev/null || lynx -source ipinfo.io/ip
}

wrap_python () {
  which python
  if [ $? ]; then
    echo "python not found ... exiting "
    exit 1
  fi
  python $@
}

check_for_jq () {
  JQ=$( which jq )
  result=$?
  echo ${JQ}
  if ! [ -r "${JQ}" ]; then
    echo "============================================" > /dev/stderr
    echo "jq not found in path; installation is required to handle larger CF templates." > /dev/stderr
    echo "https://stedolan.github.io/jq/download/" > /dev/stderr
    echo "On Windows, rename the executable to jq.exe and place it in your %PATH%" > /dev/stderr
    echo "  For example, C:\\Users\\(username)\\bin\\" > /dev/stderr
    echo "============================================" > /dev/stderr
    false
  else
    echo "jq found at $JQ" > /dev/stderr
    true
  fi
}

get_cfn_url () {

  local NAME=$1
  CFN_FILE=$( find cfn -name ${NAME}.template.yaml | head -1 )

  # Bail if no CFN_FILE present
  if [ ! -r "${CFN_FILE}" ]; then
    echo "Cannot find suitable CF file: ${NAME}.template.yaml"
    echo "Please check for file and name provided."
    exit 0;
  fi

  CFN_URL="file://${CFN_FILE}"
  echo ${CFN_URL}
}

get_params_url () {

  local NAME=$1
  PARAMS_FILE="${PARAMS_DIR}/${NAME}.params"
  PARAMS_URL="file://${PARAMS_FILE}"
  echo ${PARAMS_URL}
}

maketemp () {
  local tmpfile=$( mktemp 2>/dev/null || mktemp -t tmp 2>/dev/null || echo ${RANDOM}${RANDOM}.tmp )
  touch $tmpfile
  echo $tmpfile
}

get_git_hash () {
    hash=$( git log -1 | head -1 | awk '{print $2}' )
    echo $hash
}

check_git_working_directory () {
    message=$( git status | grep "working directory clean" )
    if ! [ -n "$message" ]; then
        echo "Uncommitted changes or untracked files. Commit and run again."
        git status
        exit 1
    fi
}

#
# YAML parsing function from
#   http://stackoverflow.com/questions/5014632/how-can-i-parse-a-yaml-file-from-a-linux-shell-script
#

parse_yaml() {
   local prefix=$2
   local s='[[:space:]]*' w='[a-zA-Z0-9_]*' fs=$(echo @|tr @ '\034')
   sed -ne "s|^\($s\):|\1|" \
        -e "s|^\($s\)\($w\)$s:$s[\"']\(.*\)[\"']$s\$|\1$fs\2$fs\3|p" \
        -e "s|^\($s\)\($w\)$s:$s\(.*\)$s\$|\1$fs\2$fs\3|p"  \
        -e 's/[ \t]*$//' $1 | sed -E "s/[[:space:]]$//" |
   awk -F$fs '{
      indent = length($1)/2;
      vname[indent] = $2;
      for (i in vname) {if (i > indent) {delete vname[i]}}
      if (length($3) > 0) {
         vn=""; for (i=0; i<indent; i++) {vn=(vn)(vname[i])("_")}
         printf("%s%s%s='\''%s'\''\n", "'$prefix'",vn, $2, $3 );
      }
   }'
}

#
# Read list of params from CF template
#
find_cf_params() {
   aws cloudformation validate-template \
      --region ${Region} \
      --template-body file://$1 --query 'Parameters[].ParameterKey' | \
      sed 's/\[//' | sed ' s/\]//' | sed 's/\,//' | sed 's/\"//g'
}

#
# Read list of params from CF template
#
report_on_cf_params() {
  wrap_python -c 'import sys,json; ps=json.load(sys.stdin)["Parameters"]; print "\n".join( [ "%s: \"%s\" (Default: %s)" % (k, ps[k]["Description"], "TBD") for k in sorted(ps.keys()) ] )'
}

get_stack_outputs() { 

    local stack_name=${1}
    local result=$( aws cloudformation \
                     ${AWS_PROFILE} describe-stacks \
		     --region ${Region} \
                     --stack-name ${stack_name} --query 'Stacks[0].Outputs' | \
           wrap_python -c 'import sys,json; ds=json.load(sys.stdin); print "\n".join( [ "\"%s\"" % (k["OutputValue"]) for k in ds ] )' )
    echo ${result}
}


#
# 
#
to_params_json() {
  echo "["
  for kv in $1; do
    echo "{ }"
  done
  echo "]"
}
