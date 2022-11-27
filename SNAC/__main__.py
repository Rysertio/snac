# snac - ActivityPub thing by grunfink

import sys
import os
import time
import json

def usage():
    print("snac - A simple, minimalistic ActivityPub instance")
    print("Copyright (c) 2022 grunfink - MIT license")
    print()
    print("Commands:")
    print()
    print("init {basedir} {host}               Initializes the database") 
    print("check {basedir} [{uid}]          Checks the database")
    print("purge {basedir} [{uid}]          Purges old data")
    print("adduser {basedir} [{uid}]        Adds a new user")
    print("httpd {basedir} [[host:]port]    Starts the HTTPD daemon")

    print("queue {basedir} {uid}            Processes the output queue")
    print("update {basedir} {uid}           Sends a user update to followers")
    print("passwd {basedir} {uid}           Sets the password for {uid}")
    print("follow {basedir} {uid} {actor}   Follows an actor")
    print("unfollow {basedir} {uid} {actor} Unfollows an actor")
    print("mute {basedir} {uid} {actor}     Mutes an actor")
    print("unmute {basedir} {uid} {actor}   Unmutes an actor")
#    print("webfinger {basedir} {@user@host} Queries about a user")
    print("like {basedir} {uid} {url}       Likes an url")
    print("announce {basedir} {uid} {url}   Announces (boosts) an url")
    print("request {basedir} {uid} {url}    Requests an object")
    print("note {basedir} {uid} {'text'}    Sends a note to followers")

    return 1


def main():
    import SNAC

    args = sys.argv
    args.reverse()
    args.pop()

    if len(args) < 1:
        return usage()

    cmd = args.pop()

    if cmd == "init":
        import SNAC.utils

        if len(args) > 0:
            ok = SNAC.utils.initdb(args.pop(), args.pop())
        else:
            ok = SNAC.utils.initdb()

        return 0 if ok else 2

    # get the basedir
    if len(args) < 1:
        return usage()

    basedir = args.pop()
    srv     = SNAC.server(basedir)

    if not srv.ok:
        print("server error:", srv.error)
        return 2

    if cmd == "check":
        print("server:", srv.error)

        if len(args) > 0:
            uid = args.pop()

            snac = SNAC.snac(srv, uid)

            print("user:", snac.error)

        else:
            for snac in srv.users():
                print("%s %s" % (snac.user["uid"], snac.user["name"]))

        return 0

    if cmd == "purge":

        if len(args) > 0:
            uid = args.pop()

            snac = SNAC.snac(srv, uid)

            snac.data.purge(snac)

        else:
            for snac in srv.users():
                snac.data.purge(snac)

        return 0

    if cmd == "adduser":
        import SNAC.utils

        if len(args) > 0:
            uid = args.pop()
        else:
            uid = None

        SNAC.utils.adduser(srv, uid)

        return 0

    if cmd == "httpd":
        host = None
        port = 0

        # parse argument
        if len(args):
            a = args.pop()

            if ":" in a:
                host, port = a.split(":")
            else:
                port = a

            port = int(port)

        srv.run(host, port)

        return 0

    # get the uid
    if len(args) < 1:
        return usage()

    uid  = args.pop()
    snac = SNAC.snac(srv, uid)

    if not snac.ok:
        print("user error:", snac.error)
        return 2

    if cmd == "queue":
        snac.activitypub.queue(snac)
        return 0

    if cmd == "update":
        msg = snac.activitypub.msg_update(snac, snac.activitypub.msg_actor(snac))

        snac.activitypub.post(snac, msg)
        return 0

    if cmd == "passwd":
        import getpass

        passwd = getpass.getpass("Password for %s: " % snac.user["uid"])

        if passwd == "":
            print("empty password")
            return 1

        passwd2 = getpass.getpass("Password again: ")

        if passwd != passwd2:
            print("passwords don't match")
            return 1

        snac.user["passwd"] = SNAC.data.hash_password(snac.user["uid"], passwd)

        ok, error = snac.data.update_user(snac)
        print(error)

        return 0

    # get the actor
    if len(args) < 1:
        return usage()

    actor = args.pop()

    if cmd == "follow":
        msg = snac.activitypub.msg_follow(snac, actor)
        snac.data.add_to_following(snac, actor, msg)
        snac.data.enqueue_output(snac, actor, msg)

        return 0

    if cmd == "unfollow":
        status, object = snac.data.following(snac, actor)

        if status == 200:
            msg = snac.activitypub.msg_undo(snac, object["object"])
            snac.data.enqueue_output(snac, actor, msg)
            snac.data.delete_from_following(snac, actor)

        else:
            print("ERROR: %s is not being followed" % actor)

        return 0

    if cmd == "mute":
        snac.data.mute(snac, actor)
        return 0

    if cmd == "unmute":
        snac.data.unmute(snac, actor)
        return 0

    if cmd == "like" or cmd == "announce":
        object = actor

        if cmd == "like":
            like = True
        else:
            like = False

        msg = snac.activitypub.msg_admiration(snac, object, like)

        snac.data.add_to_timeline(snac, msg, msg["id"], object)

        snac.activitypub.post(snac, msg)
        return 0

    if cmd == "request":

        object = actor

        status, body = snac.data.request_object(snac, object)

        if status >= 200 and status <= 299:
            print(json.dumps(body, indent=4))
        else:
            print("ERROR: %s" % status)

        return 0

#    elif cmd == "webfinger":
#        snac = SNAC.new(basedir)

#        user = args.pop()

#        status, body = snac.webfinger.request(snac, user)

#        print(status, body)

    if cmd == "note":
        content = actor

        if content == "-" or content == "-e":
            tmpfile = "/tmp/snac.msg"
            os.system("$EDITOR %s" % tmpfile)

            try:
                with open(tmpfile) as f:
                    content = f.read()
                os.unlink(tmpfile)

            except:
                print("No message to send -- exit")
                return 1

        if len(args):
            irt = args.pop()
        else:
            irt = None

        msg = snac.activitypub.msg_create(
            snac, snac.activitypub.msg_note(snac, content, irt=irt))

        snac.data.add_to_timeline(snac, msg, msg["object"]["id"], irt)

        snac.activitypub.post(snac, msg)

        return 0

    return usage()


if __name__ == "__main__":
    sys.exit(main())

