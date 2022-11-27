# snac - ActivityPub thing by grunfink

import os
import json
import re
import datetime
import SNAC
import SNAC.data

def initdb(basedir=None):
    """ initializes the database """

    server = SNAC._server

    if basedir is None:
        print("\nEnter the application base directory. All config files")
        print("and data will be stored here.\n")
        basedir = input("Base directory: ")
        print()

    if basedir == "":
        return False

    if basedir[-1] == "/":
        basedir = basedir[0:-1]

    try:
        print("Creating %s..." % basedir)
        os.mkdir(basedir)
        fn = "%s/user" % basedir
        print("Creating %s..." % fn)
        os.mkdir(fn)
        print("Done")
    except:
        print("\nERROR: cannot create base directory '%s'." % basedir)
        print("If it already exists, delete it and try again.")
        return False

    print("\nEnter the network and port address this server will be listening to.\n")

    s = input("Network address [%s]: " % server["address"])
    if s != "":
        server["address"] = s

    s = input("Network port [%d]: " % server["port"])
    if s != "":
        server["port"] = int(s)

    print("\nYou'll need to configure a real, TLS-based HTTP server to proxy to\n")
    print("    https://%s:%d" % (server["address"], server["port"]))

    print("\nEnter the host name of the computer that will serve snac.")
    print("It must be a TLS-protected host (don't type the https://).\n")
    server["host"] = input("Host name: ")

    if server["host"] == "":
        print("\nERROR: host name cannot be empty.")
        return False

    uid = "mike"

    print("\nIf you later create user %s," % uid)
    print("he will be known as @%s@%s in the Fediverse." % (uid, server["host"]))
    print("His 'actor' address will be https://%s/%s for the world." % (server["host"], uid))

    print("\nDo yo want/need a prefix in your path? So that, for example,")
    print("the URLs be https://%s/some_prefix/%s or similar." % (server["host"], uid))
    print("Leave it empty if you don't want a prefix.\n")
    server["prefix"] = input("Path prefix in URL: ")

    if server["prefix"] != "" and server["prefix"][0] != "/":
        server["prefix"] = "/" + server["prefix"]

    print("\nSo, user URLs will be https://%s%s/%s" % (
        server["host"], server["prefix"], uid))

    fn = "%s/server.json" % basedir
    print("\nThis host configuration will be saved into file '%s'." % fn)
    print("You may want to edit it for more configuration tweaks,")
    print("like queue retries, additional CSS pages and such.")

    try:
        with open(fn, "w") as f:
            f.write(json.dumps(server, indent=4))
    except:
        print("ERROR: cannot write %s server configuration" % fn)
        return False

    fn = "%s/greeting.html" % basedir

    try:
        with open(fn, "w") as f:
            f.write(greeting_html.replace("%host%", server["host"]))

    except:
        print("ERROR: cannot write file %s" % fn)
        return False

    fn = "%s/style.css" % basedir
    try:
        with open(fn, "w") as f:
            f.write(default_css)

    except:
        print("ERROR: cannot write file %s" % fn)
        return False

    print("\nThe snac database has been configured. run the server using")
    print("\n    snac httpd %s" % basedir)
    print("\nDon't forget to configure the web server according to documentation.")

    return True


def adduser(snacsrv, uid=None):
    """ adds a user """

    if uid is None:
        print("\nEnter your user id. It must be alphanumeric (a to z, numbers).\n")
        uid = input("User id: ")

    if uid == "":
        return False

    if re.match(".*[^a-zA-Z0-9_]+.*", uid):
        print("Invalid characters in uid")
        return False

    udir = "%s/%s" % (snacsrv.userdir, uid)

    try:
        os.stat(udir)
        print("ERROR: the directory %s already exists." % udir)
        print("Delete it and try again.")

    except:
        pass

    user = SNAC._user

    user["uid"] = uid

    import getpass

    print("\nEnter a password that doesn't suck.")
    print("You will need it to identify yourself in the web interface.\n")

    pw1 = getpass.getpass("User password: ")

    if pw1 == "":
        print("ERROR: password can't be empty")
        return False

    pw2 = getpass.getpass("Repeat password: ")

    if pw1 != pw2:
        print("ERROR: passwords don't match")
        return False

    user["passwd"] = SNAC.data.hash_password(uid, pw1)

    print("\nThe following data is optional and can be left empty.")

    print("\nEnter your real name (well, it doesn't have to be *that* real).\n")
    user["name"]      = input("User name: ")

    print("\nEnter the public URL to an image to use as an avatar.\n")
    user["avatar"]    = input("Avatar: ")

    print("\nEnter some text to let people know how awesome you are.\n")
    user["bio"]       = input("Brief biography: ")

    user["published"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    print("\nCreating directories...")

    try:
        os.mkdir(udir)
    except:
        print("ERROR: cannot create directory %s" % udir)
        return False

    for sd in ("actors", "archive", "followers", "following",
               "local", "muted", "queue", "static", "timeline", "history"):
        sd = "%s/%s" % (udir, sd)

        try:
            os.mkdir(sd)
        except:
            print("ERROR: cannot create directory %s" % sd)
            return False

    print("Done.")

    print("\nSaving data...")

    ok, error = SNAC.data.save_cfgfile("%s/user.json" % udir, user)

    if not ok:
        print(error)
        return False

    key = SNAC._key
    key = SNAC.data.create_keypair(key)

    ok, error = SNAC.data.save_cfgfile("%s/key.json" % udir, key)

    if not ok:
        print(error)
        return False

    fn = "%s/static/style.css" % udir

    try:
        f = open(fn, "w")

        # try to copy the server CSS
        try:
            i = open("%s/style.css" % snacsrv.basedir)
            f.write(i.read())

        except:
            f.write(default_css)

    except:
        print("ERROR: cannot write default CSS %s" % fn)
        return False


    print("Done.")

    # now open it
    snac = SNAC.snac(snacsrv, uid)

    if not snac.ok:
        print("ERROR: %s" % snac.error)
        return False

    print("\nSuccess!")

    print("\nYour actor base URL is %s" % snac.actor())
    print("You id in the Fediverse is @%s@%s" % (uid, snac.server["host"]))
 
    return True


default_css = """
body { max-width: 48em; margin: auto; line-height: 1.5; padding: 0.8em }
img { max-width: 100% }
.snac-origin { font-size: 85% }
.snac-top-user { text-align: center; padding-bottom: 2em }
.snac-top-user-name { font-size: 200% }
.snac-top-user-id { font-size: 150% }
.snac-avatar { float: left; height: 2.5em; padding: 0.25em }
.snac-author { font-size: 90% }
.snac-pubdate { color: #a0a0a0; font-size: 90% }
.snac-top-controls { padding-bottom: 1.5em }
.snac-post { border-top: 1px solid #a0a0a0; }
.snac-children { padding-left: 2em; border-left: 1px solid #a0a0a0; }
.snac-textarea { font-family: inherit; width: 100% }
.snac-history { border: 1px solid #606060; border-radius: 3px; margin: 2.5em 0; padding: 0 2em }
.snac-btn-mute { float: right; margin-left: 0.5em }
.snac-btn-follow { float: right; margin-left: 0.5em }
.snac-btn-unfollow { float: right; margin-left: 0.5em }
.snac-btn-delete { float: right; margin-left: 0.5em }
.snac-footer { margin-top: 2em; font-size: 75% }
"""

greeting_html = """
<!DOCTYPE html>
<html><head>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Welcome to %host%</title>
<body style="margin: auto; max-width: 50em">
<h1>Welcome to %host%</h1>
<p>This is a <a href="https://en.wikipedia.org/wiki/Fediverse">Fediverse</a> instance
that uses the <a href="https://en.wikipedia.org/wiki/ActivityPub">ActivityPub</a> protocol.
In other words, users at this host can communicate with people that use software like
Mastodon, Pleroma, Friendica, etc. all around the world.</p>

<p>There is no automatic sign up process for this server. If you want to be a part of
this community, please write an email to

the administrator of this instance

and ask politely indicating what is your preferred user id (alphanumeric characters
only) and the full name you want to appear as.</p>

<p>The following users are already part of this community:</p>

%userlist%

<p>This site is powered by <abbr title="Social Networks Are Crap">snac</abbr>.</p>
</body></html>
"""
