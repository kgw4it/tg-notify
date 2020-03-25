#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

SITE=${1:-"NOTSET"}

if [ ! -d "/omd/sites/$SITE" ]; then
  echo "Site '$SITE' does not exist. Aborting."
  exit 2
fi


cp $DIR/local/bin/tg_admin /omd/sites/$SITE/local/bin/tg_admin
cp $DIR/local/bin/tg_callback /omd/sites/$SITE/local/bin/tg_callback
cp $DIR/local/bin/tg_runner /omd/sites/$SITE/local/bin/tg_runner
cp $DIR/local/share/check_mk/notifications/tg_notification_with_callback.py /omd/sites/$SITE/share/check_mk/notifications/tg_notification_with_callback.py
