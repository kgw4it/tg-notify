#!/usr/bin/env python
# -*- encoding: utf-8; py-indent-offset: 4 -*-
# Telegram Notification Bot with Callback (Users must be created with tg_admin, follow instructions)

#
# TG Notification with Callback
# Version 0.1 beta
# Written by Maximilian Thoma 2017
# Visit https://lanbugs.de for further informations.
#
# tgnotify is free software;  you can redistribute it and/or modify it
# under the  terms of the  GNU General Public License  as published by
# the Free Software Foundation in version 2.  check_mk is  distributed
# in the hope that it will be useful, but WITHOUT ANY WARRANTY;  with-
# out even the implied warranty of  MERCHANTABILITY  or  FITNESS FOR A
# PARTICULAR PURPOSE. See the  GNU General Public License for more de-
# tails. You should have  received  a copy of the  GNU  General Public
# License along with GNU Make; see the file  COPYING.  If  not,  write
# to the Free Software Foundation, Inc., 51 Franklin St,  Fifth Floor,
# Boston, MA 02110-1301 USA.
#

import ConfigParser
import sqlite3
import os
import sys
import urllib
import urllib2
import requests
import json
import random
import string
import time
import logging
import base64
import subprocess

import cmk.utils.site as site

class TGnotification:

    def __init__(self):

        # Check if we are in an OMD_ENVIRONMENT
        try:
            self.path = os.environ['OMD_ROOT']
        except:
            sys.stderr.write("We are not in an OMD ENVIRONMENT, please go to OMD ROOT")
            sys.exit(2)

        # Load Telegram Config
        config = ConfigParser.ConfigParser()
        config.read(self.path + "/local/etc/tg.ini")

        # Define global parameters
        self.tg_url = config.get('Telegram', 'url') + "bot" + config.get('Telegram', 'token') + "/"
        self.db_path = self.path + "/" + config.get('Database', 'path')
        self.db_file = config.get('Database', 'file')

        # Start logging engine
        self.L = logging.getLogger("tg_notify")

        logging.basicConfig(filename=self.path + '/var/log/tg-notify.log',
                            level=logging.INFO,
                            format='%(asctime)s %(name)-16s %(levelname)-8s %(message)s',
                            datefmt='%d.%m.%Y %H:%M:%S')

        # Make an notification
        self.notify()
        #pprint(os.environ)

    ####################################################################################################################
    # Handler for Telegram communication
    ####################################################################################################################
    def tg_handler(self,command):
        try:
            handle = urllib.urlopen(self.tg_url + command)
            response = handle.read().strip()
            j = json.loads(response)
        except Exception:
            import traceback
            sys.stderr.write('generic exception: ' + traceback.format_exc())
            sys.exit(2)

        if j['ok'] is True:
            self.L.info("Message successful sent to telegram.")
            return j
        else:
            self.L.info("There was a problem with sending message to telegram: %s", j)
            return {}
        
    def tg_handler_post(self, command, postdata, files):
        try:
            response = requests.post(self.tg_url + command, data=postdata, files=files)
            j = json.loads(response.content)
        except Exception as e:
            self.L.info("There was a problem with sending data to telegram: %s", str(e))
            return

        if j['ok'] is True:
            self.L.info("Data successful sent to telegram.")
            return j
        else:
            self.L.info("There was a problem with sending data to telegram: %s", j)
            return {}

    ####################################################################################################################
    # Create notification
    ####################################################################################################################
    def get_graph(self, is_host):
        if site.get_omd_config("CONFIG_CORE") == "cmc":
            return self.get_cmc_graph(is_host)
        else:
            return self.get_pnp_graph(is_host)
        
    def fetch_pnp_data(self, params):
        try:
            # Autodetect the path in OMD environments
            path = "%s/share/pnp4nagios/htdocs/index.php" % os.environ['OMD_ROOT'].encode('utf-8')
            php_save_path = "-d session.save_path=%s/tmp/php/session" % os.environ['OMD_ROOT'].encode(
                'utf-8')
            env = {
                'REMOTE_USER': "check-mk",
                "SKIP_AUTHORIZATION": "1",
            }
        except:
            return ''

        if not os.path.exists(path):
            return ''

        return subprocess.check_output(["php", php_save_path, path, params], env=env)


    def fetch_num_sources(self, is_host):
        svc_desc = '_HOST_' if is_host else os.environ['NOTIFY_SERVICEDESC']
        infos = self.fetch_pnp_data(
            '/json?host=%s&srv=%s&view=0' %
            (os.environ['NOTIFY_HOSTNAME'].encode('utf-8'), svc_desc.encode('utf-8')))
        if not infos.startswith('[{'):
            return 0

        return infos.count('source=')


    def fetch_graph(self, is_host, source, view=1):
        svc_desc = '_HOST_' if is_host else os.environ['NOTIFY_SERVICEDESC']
        graph = self.fetch_pnp_data(
            '/image?host=%s&srv=%s&view=%d&source=%d' %
            (os.environ['NOTIFY_HOSTNAME'].encode('utf-8'), svc_desc.encode('utf-8'), view, source))

        if graph[:8] != '\x89PNG\r\n\x1a\n':
            return None

        return graph

    def get_pnp_graph(self, is_host):
        num_sources = self.fetch_num_sources(is_host)

        graph_list = []
        for source in range(0, num_sources):
            content = self.fetch_graph(is_host, source)
                
            if content is None:
                sys.stderr.write('Unable to fetch graph: %s\n' % e)
                continue

            graph_list.append(content)

        return graph_list

    def get_cmc_graph(self, is_host):
        url = ("http://localhost:%d/%s/check_mk/ajax_graph_images.py?host=%s&service=%s" %
           (site.get_apache_port(), os.environ["OMD_SITE"],
            urllib.quote(os.environ['NOTIFY_HOSTNAME']),
            urllib.quote("_HOST_" if is_host else os.environ['NOTIFY_SERVICEDESC'])))
        
        try:
            handle = urllib.urlopen(url)
            response = handle.read().strip()
            base64_strings = json.loads(response)
            return map(base64.b64decode, base64_strings)
        except Exception:
            return []
        
    def notify(self):

        # Step 0: Build DB Connection
        try:
            con = sqlite3.connect(self.db_path + self.db_file)
            cur = con.cursor()
            self.L.debug("Database connection established.")

        except:
            self.L.debug("Unable to establish database connection.")
            sys.stderr.write("Unable to open database. No notification is sent.")
            sys.exit(2)


        ################################################################################################################
        # Steps:
        ################################################################################################################

        # Step 1: Get Chat_ID from Database
        try:
            cur.execute("""SELECT * FROM users WHERE username='%s' LIMIT 1""" %(os.environ.get("NOTIFY_CONTACTNAME")))
            # Get Chat_ID
            username, chat_id = cur.fetchone()
            self.L.debug("Get username and chat_id from database %s", username)
            sys.stdout.write("Found Chat_ID for %s " % os.environ.get("NOTIFY_CONTACTNAME"))
        except:
            self.L.warning("Unable to locate Chat_ID in Database. No notification is sent for %s", os.environ.get("NOTIFY_CONTACTNAME"))
            sys.stderr.write("Unable to locate Chat_ID in Database. No notification is sent for %s" % os.environ.get("NOTIFY_CONTACTNAME"))
            sys.exit(2)

        # Step 2: Register Notification in Database
        callback_id = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(16))
        self.L.debug("Generated Callback_ID: %s", callback_id)

        timestamp = int(time.time())

        host = os.environ.get("NOTIFY_HOSTNAME")
        service = os.environ.get("NOTIFY_SERVICEDISPLAYNAME")

        cur.execute("""INSERT INTO notify (callback_ident, host, service, chat_id, datetime) VALUES ('%s', '%s', '%s',
                        '%s', %s) """ % (callback_id,
                                         host,
                                         service,
                                         chat_id,
                                         timestamp))

        con.commit()

        # Step 3: Build notification
        max_len = 300
        message = os.environ['NOTIFY_HOSTNAME'] + " "
        graph_data = None

        notification_type = os.environ["NOTIFY_NOTIFICATIONTYPE"]

        # Prepare Default information and Type PROBLEM, RECOVERY
        if os.environ['NOTIFY_WHAT'] == 'SERVICE':
            graph_data = self.get_graph(False)
            
            if notification_type in ["PROBLEM", "RECOVERY"]:
                message += os.environ['NOTIFY_SERVICESTATE'][:2] + " "
                avail_len = max_len - len(message)
                message += os.environ['NOTIFY_SERVICEDESC'][:avail_len] + " "
                avail_len = max_len - len(message)
                message += os.environ['NOTIFY_SERVICEOUTPUT'][:avail_len]
            else:
                message += os.environ['NOTIFY_SERVICEDESC']

        else:
            graph_data = self.get_graph(True)
            
            if notification_type in ["PROBLEM", "RECOVERY"]:
                message += "is " + os.environ['NOTIFY_HOSTSTATE']

        # Ouput the other State
        if notification_type.startswith("FLAP"):
            if "START" in notification_type:
                message += " Started Flapping"
            else:
                message += " Stopped Flapping"

        elif notification_type.startswith("DOWNTIME"):
            what = notification_type[8:].title()
            message += " Downtime " + what
            message += " " + os.environ['NOTIFY_NOTIFICATIONCOMMENT']

        elif notification_type == "ACKNOWLEDGEMENT":
            message += " Acknowledged"
            message += " " + os.environ['NOTIFY_NOTIFICATIONCOMMENT']
            
        elif notification_type.startswith("ALERTHANDLER"):
            message += " Alert Handler"
            message += " " + os.environ['NOTIFY_ALERTHANDLERSHORTSTATE']
            message += " - " + os.environ['NOTIFY_ALERTHANDLERNAME']
            if os.environ['NOTIFY_ALERTHANDLEROUTPUT']:
                message += ": " + os.environ['NOTIFY_ALERTHANDLEROUTPUT']
            
        elif notification_type == "CUSTOM":
            message += " Custom Notification"
            message += " " + os.environ['NOTIFY_NOTIFICATIONCOMMENT']

        # markup fuer callbacks
        markup = json.dumps({'inline_keyboard': [
            [
             {'text': 'Acknowledge', 'callback_data': '$$$CB$$$%s:ack' % callback_id },
             {'text': 'Downtime for 24h', 'callback_data': '$$$CB$$$%s:down24h' % callback_id }
            ]
                                                ]
                            }
                           )

        self.L.info("Message: %s", message)
        
        if graph_data is not None:
            for source, graph_png in enumerate(graph_data):
                self.tg_handler_post("sendPhoto", {
                    "chat_id": chat_id,
                    "caption": "%s" % (os.environ['NOTIFY_HOSTNAME'])
                }, {
                    "photo": ("%s-%s.png" % (os.environ['NOTIFY_HOSTNAME'], source), graph_png, 'image/png'),
                })

        if notification_type == "PROBLEM":
            self.L.debug("Notification Type is PROBLEM")
            # Step 4: Send notification
            self.tg_handler("sendMessage?" + urllib.urlencode([("chat_id", chat_id),
                                                               ("text", message),
                                                               ("reply_markup", markup)
                                                               ]))
        else:
            self.L.debug("Notification type is not PROBLEM, no MARKUPs")
            # Step 4: Send notification
            self.tg_handler("sendMessage?" + urllib.urlencode([("chat_id", chat_id),
                                                               ("text", message),
                                                               ]))

        # Step 5: Write to STDOUT
        sys.stdout.write("Notification send to %s (Chat_ID: %s)" % (username,chat_id))

        # Step 6: Close DB
        con.close()


def main():
    TGnotification()

if __name__ == "__main__":
    main()

