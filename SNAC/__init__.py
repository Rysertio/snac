# snac - ActivityPub thing by grunfink

import os
import sys
import time
import json
import hashlib
import SNAC.data
import SNAC.http
import SNAC.webfinger
import SNAC.activitypub
import SNAC.httpd
import SNAC.html

__version__ = "1.01"

_user = {
    "uid":       "",
    "passwd":    "",
    "name":      "",
    "avatar":    "",
    "bio":       "",
    "published": ""
}

_server = {
    "host":                 "",
    "prefix":               "",
    "address":              "0.0.0.0",
    "port":                 10000,
    "layout":               SNAC.data.layout_version,
    "dbglevel":             0,
    "queue_retry_minutes":  2,
    "queue_retry_max":      10,
    "cssurls":              [""],
    "max_timeline_entries": 256,
    "timeline_purge_days":  120
}

_key = {
    "secret": "",
    "public": ""
}

class server:
    def __init__(self, basedir):
        if basedir.endswith("/"):
            basedir = basedir[:-1]

        self.basedir    = basedir
        self.userdir    = "%s/user" % basedir
        self.config     = _server

        self.data       = SNAC.data
        self.webfinger  = SNAC.webfinger

        self.ok, self.error = self.data.open_server(self)

        self.server_on  = False
        self.dbglevel   = self.config["dbglevel"]

        self.user_agent = "snac/%s; %s" % (__version__, self.config["host"])

        if self.ok:
            # debug level
            try:
                self.dbglevel = int(os.environ["DEBUG"])
                self.log("DEBUG level set to %d from environment" % self.dbglevel)
            except:
                pass

    def base_url(self):
        return "https://%s%s" % (self.config["host"], self.config["prefix"])

    def log(self, string):
        """ logs something """
        print(time.strftime("%H:%M:%S"), string, file=sys.stderr)

    def debug(self, level, string):
        """ logs something """
        if self.dbglevel >= level:
            self.log(string)

    def users(self):
        """ iterates the users in this server """
        for u in self.data.users(self):
            yield u

    def run(self, address, port):
        """ runs as the httpd daemon """

        SNAC.httpd.run(self, address, port)


class snac:
    def __init__(self, server, uid):
        self._server    = server

        self.basedir    = "%s/%s" % (server.userdir, uid)

        self.server     = server.config
        self.user       = _user
        self.key        = _key

        self.data           = SNAC.data
        self.http           = SNAC.http
        self.webfinger      = SNAC.webfinger
        self.activitypub    = SNAC.activitypub
        self.html           = SNAC.html

        self.ok, self.error = self.data.open_user(self)

        self.user_agent = server.user_agent

    def log(self, string):
        string = string.replace(self.basedir, "~")
        self._server.log("[%s] %s" % (self.user["uid"], string))

    def debug(self, level, string):
        string = string.replace(self.basedir, "~")
        self._server.debug(level, "[%s] %s" % (self.user["uid"], string))

    def actor(self, postfix=""):
        """ returns the actor URL, with an optional prefix """
        return "%s/%s%s" % (self._server.base_url(), self.user["uid"], postfix)

    def tid(self, offset=0.0):
        return "%17.6f" % (time.time() + offset)

    def L(self, string):
        """ returns a translated string """
        return string

# default avatar (png)
susie = """
iVBORw0KGgoAAAANSUhEUgAAAEAAAABAAQAAAAC
CEkxzAAAAUUlEQVQoz43R0QkAMQwCUDdw/y3dwE
vsvzlL4X1IoQkAisKmwfAFT3RgJHbQezpSRoXEq
eqCL9BJBf7h3QbOCCxV5EVWMEMwG7K1/WODtlvx
AYTtEsDU9F34AAAAAElFTkSuQmCC
"""
