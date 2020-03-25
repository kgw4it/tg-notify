#!/bin/bash

SITE=$1

if [ ! -d "/omd/sites/$SIT" ]; then
  echo "Site '$SITE' does not exist. Aborting."
  exit 2
fi


cp local/bin/tg_admin /omd/sites/$SITE/local/bin/tg_admin
cp local/bin/tg_callback /omd/sites/$SITE/local/bin/tg_callback
cp local/bin/tg_runner /omd/sites/$SITE/local/bin/tg_runner
cp local/share/check_mk/notifications/tg_notification_with_callback.py /omd/sites/$SITE/share/check_mk/notifications/tg_notification_with_callback.py
