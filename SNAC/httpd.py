# snac - ActivityPub thing by grunfink

import SNAC
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
import threading
import time
import base64

class handler(BaseHTTPRequestHandler):
    """ main httpd handler """

    def _finish(self, status=200, body=None, ctype=None):
        if ctype is None:
            ctype = "text/html; charset=utf-8"

        self.send_response(status)

        self.send_header("Content-Type", ctype)

        if status == 303:
            # redirection
            self.send_header("Location", body)

        if status == 401:
            # auth required
            self.send_header("WWW-Authenticate", "Basic realm=\"IDENTIFY\"")

        self.end_headers()

        if body is not None:
            if isinstance(body, str):
                body = body.encode("utf-8")

            try:
                self.wfile.write(body)
            except:
                # protect from broken pipe exceptions
                pass

    def _init(self):
        # parse query string and vars
        qs     = self.path.split('?')
        q_path = qs[0]

        # convert %XX to char
        q_path = urllib.parse.unquote(q_path)

        if len(qs) == 2:
            q_vars = urllib.parse.parse_qs(qs[1])
        else:
            q_vars = {}

        return self.snacsrv, q_path, q_vars


    def do_HEAD(self):
        snacsrv, q_path, q_vars = self._init()

        self._finish()


    def do_GET(self):
        snacsrv, q_path, q_vars = self._init()

        acpt = self.headers["Accept"]

        snacsrv.debug(3, "get q_path %s" % q_path)

        status, body, ctype = 0, None, None

        if acpt is None:
            status, body, ctype = 400, "<h1>400 Bad Request</h1>", "text/html"

        # server global page?
        if q_path == "%s" % snacsrv.config["prefix"] or q_path == "%s/" % snacsrv.config["prefix"]:
            # try opening greeting.html
            try:
                f = open("%s/greeting.html" % snacsrv.basedir)
            except:
                f = None

            if f is not None:
                status, body, ctype = 200, f.read(), "text/html"

                if "%userlist%" in body:
                    # prepare a user list

                    ul = []
                    for snac in snacsrv.users():
                        ul.append("<li><a href=\"%s\">@%s@%s (%s)</a></li>\n" % (
                            snac.actor(), snac.user["uid"], snac.server["host"], snac.user["name"]))

                    s = "<ul class=\"snac-user-list\">\n%s</ul>\n" % "".join(sorted(ul))

                    body = body.replace("%userlist%", s)

        # do they ask for susie?
        if q_path == "%s/susie.png" % snacsrv.config["prefix"]:
            status, body, ctype = 200, base64.b64decode(SNAC.susie), "image/png"

        # try the webfinger
        if status == 0:
            status, body, ctype = snacsrv.webfinger.get_handler(snacsrv, q_path, q_vars, acpt)

        if status == 0:
            # if the path starts with the prefix, strip it
            if q_path.startswith(snacsrv.config["prefix"]):
                q_path = q_path[len(snacsrv.config["prefix"]):]

            # get the uid
            uid = q_path.split("/")[1]

            # get the snac
            snac = SNAC.snac(snacsrv, uid)

            if not snac.ok:
                snacsrv.debug(1, "bad user '%s' in get" % uid)
                status = 404

        # cascade all handlers
        if status == 0:
            status, body, ctype = snac.activitypub.get_handler(snac, q_path, q_vars, acpt)

        if status == 0:
            status, body, ctype = snac.html.get_handler(snac, q_path, q_vars, acpt, self.headers)

        # nobody handled this? notify error
        if status == 0:
            snacsrv.log("unattended get %s %s" % (q_path, acpt))
            status = 404

        # if 404, force body and content/type
        if status == 404:
            status, body, ctype = 404, "<h1>404 Not Found</h1>", "text/html"

        self._finish(status, body, ctype)


    def do_POST(self):
        snacsrv, q_path, q_vars = self._init()

        snacsrv.debug(3, "post headers '%s'" % self.headers)

        content_length = int(self.headers['Content-Length'])
        p_data = self.rfile.read(content_length).decode('utf-8')

        status, body, ctype = 0, None, self.headers["Content-Type"]

        # if the path starts with the prefix, strip it
        if q_path.startswith(snacsrv.config["prefix"]):
            q_path = q_path[len(snacsrv.config["prefix"]):]

        # get the uid
        uid = q_path.split("/")[1]

        # get the snac
        snac = SNAC.snac(snacsrv, uid)

        if not snac.ok:
            # it's probably some Delete crap
            snacsrv.debug(3, "bad user '%s' in post (q_path %s)" % (uid, q_path))
            status = 404

        # cascade all handlers
        if status == 0:
            status, body, ctype = snac.activitypub.post_handler(
                snac, q_path, q_vars, ctype, p_data, self.headers)

        if status == 0:
            status, body, ctype = snac.html.post_handler(
                snac, q_path, q_vars, ctype, p_data, self.headers)

        # nobody handled this? notify error
        if status == 0:
            snacsrv.log("unattended post %s %s" % (q_path, ctype))
            status = 404

        # if 404, force body and content/type
        if status == 404:
            status, body, ctype = 404, "<h1>404 Not Found</h1>", "text/html"

        self._finish(status, body, ctype)


    def log_message(self, format, *args):
        """ disable logging """
        return


def helper_thread(snacsrv):
    """ helper thread """

    snacsrv.log("subthread start")

    while snacsrv.server_on:
        # iterate all users and dispatch their queues
        for snac in snacsrv.users():
            snac.activitypub.queue(snac)

        time.sleep(3)

    snacsrv.log("subthread stop")


def run(snacsrv, address=None, port=0):
    """ starts the httpd server """

    if address is None:
        address = snacsrv.config["address"] or "localhost"

    if port == 0:
        port = snacsrv.config["port"]

    import signal, sys

    def sigterm_handler(sig, frame):
        snacsrv.log("httpd SIGTERM")
        # simulate Ctrl-C
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, sigterm_handler)
#    signal.signal(signal.SIGPIPE, sigterm_handler)

    snacsrv.server_on = True

    # create the helper thread
    ht = threading.Thread(target=helper_thread, args=(snacsrv,))
    ht.start()

    server = HTTPServer((address, port), handler)
    snacsrv.log("httpd start %s:%s [%s]" % (address, port, snacsrv.user_agent))

    # copy the snacsrv object into the handler
    server.RequestHandlerClass.snacsrv = snacsrv

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

    snacsrv.server_on = False

    server.server_close()
    snacsrv.log("httpd stop %s:%s" % (address, port))
