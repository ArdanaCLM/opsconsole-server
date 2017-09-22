#!/bin/bash
# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

function usage {
    echo
    echo "Usage: $0 [OPTION]..."
    echo "Run BLL's test suite(s)"
    echo ""
    echo "  -V, --virtual-env          Always use virtualenv.  Install automatically"
    echo "                             if not present"
    echo "  -N, --no-virtual-env       Don't use virtualenv.  Run tests in local"
    echo "                             environment"
    echo "  -f, --functional=s1[,s2..] Functional Tests that require services s1,s2.."
    echo "  -c, --coverage             Generate reports using Coverage"
    echo "  -y, --pylint               Just run pylint"
    echo "  -p, --pep8                 Run Pep8 syntax checker"
    echo "  -q, --quiet                Run non-interactively. (Relatively) quiet."
    echo "                             Implies -V if -N is not set."
    echo "  --runserver                Run the development server"
    echo "  --docs                     Just build the documentation"
    echo "  --destroy-environment      Destroy the environment and exit"
    echo "  -h, --help                 Print this usage message"
    echo ""
    echo "Note: with no options specified, the script will try to run the tests in"
    echo "  a virtual environment,  If no virtualenv is found, the script will ask"
    echo "  if you would like to create one.  If you prefer to run tests NOT in a"
    echo "  virtual environment, simply pass the -N option."
    exit
}

#
# DEFAULTS FOR RUN_TESTS.SH
#
root=`pwd -P`

# To run functional tests against keystone when its endpoint runs over https,
# do the following as sudo
# 1. download the appropriate certificate from the deployer system into the
#    /usr/local/share/ca-certificates dir on your system.
#    This certificate is normally static, so you only have to do that once.
#
# 2. update-ca-certificates

# Direct the Requests library to use the installed ssl standard certs
REQUESTS_CA_BUNDLE=${REQUESTS_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}
export REQUESTS_CA_BUNDLE

# Avoid a bunch of unnecessary warnings about bad ssl certs
export PYTHONWARNINGS=ignore::Warning

set -o errexit

venv=$root/.venv
venv_env_version=$venv/environment
with_venv=tools/with_venv.sh
included_dirs="bll"
mkdir -p log

always_venv=0
command_wrapper=""
destroy=0
just_pylint=0
just_docs=0
just_pep8=0
never_venv=0
quiet=0
runserver=0
testargs=""
with_coverage=0


function process_options {

    # Verify, normalize, sanitize arguments
    ARGS=$(getopt -o hVNf:cypq -l help,virtual-env,no-virtual-env,functional:,coverage,pylint,pep8,quiet,runserver,docs,destroy-environment -- "$@") || usage
    eval set -- "$ARGS"

    while true ; do
        case "$1" in
            -h|--help) usage;;
            -V|--virtual-env) always_venv=1; never_venv=0;;
            -N|--no-virtual-env) always_venv=0; never_venv=1;;
            -f|--functional) shift; export functional=$1 ;;
            -c|--coverage) with_coverage=1;;
            -y|--pylint) just_pylint=1;;
            -p|--pep8) just_pep8=1;;
            -q|--quiet) quiet=1;;
            --runserver) runserver=1;;
            --docs) just_docs=1;;
            --destroy-environment) destroy=1;;
            --) shift; break;;
        esac
        shift
    done
    testargs="$@"
}


function run_server {
    cd ${root}
    echo "Starting pecan development server ..."
    ${command_wrapper} python ${root}/setup.py develop
    if [[ $testargs && -f $testargs ]] ; then
       conf_file=$testargs
    elif [[ $BLL_CONF_OVERRIDE ]] ; then
       conf_file=$BLL_CONF_OVERRIDE
    else
       conf_file=${root}/tests/config.py
    fi
    ${command_wrapper} pecan serve ${conf_file}
    echo "Server stopped."
}

function destroy_venv {
    echo "Cleaning environment..."
    echo "Removing virtualenv..."
    rm -rf $venv
    echo "Virtualenv removed."
    echo "Environment cleaned."
}

# Determine the version of the environment programatically.  For
# simplicity, it is the concatenation of the requiments files
function get_version {
    cat requirements.txt test-requirements.txt
}

function environment_check {
    echo "Checking environment."
    if get_version | diff -q $venv_env_version - &> /dev/null ; then
        # If the environment exists and is up-to-date then set our variables
        command_wrapper="${root}/${with_venv}"
        echo "Environment is up to date."
        return 0
    fi

    if [ $always_venv -eq 1 ]; then
        install_venv --venv=${venv}
    else
        if [ ! -e ${venv}/bin ]; then
            echo -e "Environment not found. Install? (Y/n) \c"
        else
            echo -e "Your environment appears to be out of date. Update? (Y/n) \c"
        fi
        read update_env
        if [ "x$update_env" = "xY" -o "x$update_env" = "x" -o "x$update_env" = "xy" ]; then
            install_venv --venv=${venv}
        else
            # Set our command wrapper anyway.
            command_wrapper="${root}/${with_venv}"
        fi
    fi
}

function sanity_check {
    # Anything that should be determined prior to running the tests, server, etc.
    # Don't sanity-check anything environment-related in -N flag is set
    if [ $never_venv -eq 0 ]; then
        if [ ! -e ${venv} ]; then
            echo "Virtualenv not found at $venv. Did install_venv.py succeed?"
            exit 1
        fi
    fi
    # Remove .pyc files. This is sanity checking because they can linger
    # after old files are deleted.
    find . -name "*.pyc" -exec rm -rf {} \;
}

function install_venv {
    # Install with install_venv.py
    export PIP_DOWNLOAD_CACHE=${PIP_DOWNLOAD_CACHE-/tmp/.pip_download_cache}
    export PIP_USE_MIRRORS=${PIP_USE_MIRRORS:=true}
    if [ $quiet -eq 1 ]; then
      export PIP_NO_INPUT=${PIP_NO_INPUT:=true}
    fi
    echo "Fetching new src packages..."
    rm -rf $venv/src
    python tools/install_venv.py --venv=${venv}
    command_wrapper="$root/${with_venv}"
    # Make sure it worked and record the environment version
    # sanity_check
    chmod -R 754 $venv
    get_version > $venv_env_version
}

function run_pep8 {
    sanity_check
    ${command_wrapper} flake8 bll tests
}

function run_pylint {
    echo "Running pylint ..."
    PYTHONPATH=$root ${command_wrapper} pylint --rcfile=.pylintrc $included_dirs > pylint.txt || true
    CODE=$?
    grep Global -A2 pylint.txt
    if [ $CODE -lt 32 ]; then
        echo "Completed successfully."
        exit 0
    else
        echo "Completed with problems."
        exit $CODE
    fi
}

function run_sphinx {
    echo "Building sphinx..."
    ${command_wrapper} sphinx-build -b html doc/source doc/build
    echo "Build complete."
}

function run_tests {
    sanity_check
    cd ${root}

    local q=""
    if [ $quiet -eq 1 ]; then
       q=-q
    fi

    if [ -n "$testargs" ] ; then
       s=-s
    fi

    if [ $with_coverage -eq 1 ]; then
       ${command_wrapper} coverage2 erase
       ${command_wrapper} coverage2 run $root/setup.py test $q $s $testargs
    else
        ${command_wrapper} python $root/setup.py test $q $s $testargs
    fi
    API_RESULT=$?

    if [ $with_coverage -eq 1 ]; then
    echo "Generating coverage reports"
        ${command_wrapper} coverage2 xml -i --omit="/usr*,setup.py,*egg*,${venv}/*,tests/*,examples/*"
        ${command_wrapper} coverage2 html -i --omit="/usr*,setup.py,*egg*,${venv}/*,tests/*,examples/*" -d reports
    fi

    if [ $API_RESULT -eq 0 ]; then
        echo "Tests completed successfully."
    else
        echo "Tests failed."
    fi
    exit $API_RESULT
}


# ---------PREPARE THE ENVIRONMENT------------ #


# PROCESS ARGUMENTS, OVERRIDE DEFAULTS
process_options "$@"

# If destroy is set, just blow it away and exit.
if [ $destroy -eq 1 ]; then
    destroy_venv
    exit 0
fi

if [ $quiet -eq 1 ] && [ $never_venv -eq 0 ] && [ $always_venv -eq 0 ]
then
  always_venv=1
fi

# Ignore all of this if the -N flag was set
if [ $never_venv -eq 0 ]; then
    environment_check
fi

# ---------EXERCISE THE CODE------------ #

# Pylint
if [ $just_pylint -eq 1 ]; then
    run_pylint
    exit $?
fi

# Build the docs
if [ $just_docs -eq 1 ]; then
    run_sphinx
    exit $?
fi

# Pep8
if [ $just_pep8 -eq 1 ]; then
    run_pep8
    exit $?
fi


# pecan development server
if [ $runserver -eq 1 ]; then
    run_server
    exit $?
fi


# Full test suite
run_tests || exit
