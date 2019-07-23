#!/usr/bin/env bash
# Initialise the project

set -e

SCRIPTDIR=$(dirname $0)
CONFIG_FILE_PATH="$SCRIPTDIR/chalicelib/config.ini"

echo "* Initialising project..."

# Check we're in a venv before we initialise
if [ -z "$VIRTUAL_ENV" ]; then
    echo "ERROR: You're not currently in a virtual environment, are you in the project directory? Did you run 'direnv allow' yet?"
    exit 1
fi

echo "* Installing/upgrading python packages..."
pip3 install -r "$SCRIPTDIR/requirements.txt" --upgrade

if [ ! -e "$CONFIG_FILE_PATH" ]; then
    echo "* Creating a fresh copy of config.ini, please configure this file before you attempt to deploy."
    cp "$CONFIG_FILE_PATH.dist" "$CONFIG_FILE_PATH"
else
    echo "* You already have a config.ini file, please review and configure if necessary before you attempt to deploy."
fi

echo "Initialisation complete."
