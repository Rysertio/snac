# snac - ActivityPub thing by grunfink

import os
import json
import SNAC
import OpenSSL
import time
import glob
import re
import hashlib
import random

# data layout version
layout_version = 1


""" helping functions """

def md5(string):
    m = hashlib.md5()
    m.update(string.encode())
    return m.hexdigest()

def sha1(string):
    m = hashlib.sha1()
    m.update(string.encode())
    return m.hexdigest()

def hash_password(uid, passwd, nonce=None):
    """ calculates the SHA1 of nonce:uid:passwd """
    if nonce == None:
        nonce = "%08x" % random.randint(0, 0xffffffff)

    return "%s:%s" % (nonce, sha1("%s:%s:%s" % (nonce, uid, passwd)))

def check_password(uid, passwd, hash):
    """ checks if the hashed password matches the uid:passwd pair """
    nonce, chk = hash.split(":", 1)

    n_hash = hash_password(uid, passwd, nonce)
    return bool(hash == n_hash)

def save_cfgfile(fn, content, error="OK"):
    """ saves a config file """

    ok = True

    try:
        # make a copy
        os.rename(fn, "%s.bak" % fn)
    except:
        pass

    try:
        f = open(fn, "w")
        f.write(json.dumps(content, indent=4))

    except:
        ok    = False
        error = "error saving %s" % fn

    return ok, error


def load_cfgfile(fn, default=None):
    """ loads and possibly updates a config file """

    content, error = None, ""

    try:
        f = open(fn)

        try:
            content = json.loads(f.read())
            error   = "OK"
            changes = 0

            if default is not None:
                for (k, v) in default.items():
                    try:
                        content[k]
                    except:
                        content[k] = v
                        changes += 1

                if changes:
                    ok, error = save_cfgfile(fn, content, "OK (%d changes)" % changes)

                    if ok is False:
                        content = None

        except:
            error = "error parsing %s" % fn

    except:
        error = "error opening %s" % fn

    return content, error


""" server """

def open_server(srv):
    """ opens a server configuration """

    fn = "%s/%s" % (srv.basedir, "server.json")

    config, error = load_cfgfile(fn, SNAC._server)

    if config is None:
        return False, error

    srv.config = config

    if config["layout"] > layout_version:
        return False, "unexpected future layout v.%d" % config["layout"]

    if config["layout"] < layout_version:
        return False, "unsupported old layout v.%d -- try upgrade tool" % config["layout"]

    return True, error


def users(srv):
    """ iterates the users """

    for uid in glob.glob("%s/*" % srv.userdir):
        uid = uid.split("/")[-1]

        snac = SNAC.snac(srv, uid)

        if snac.ok is True:
            yield snac


def open_user(snac):
    """ opens a user configuration """

    if re.match(".*[^a-zA-Z0-9_]+.*", snac.user["uid"]):
        return False, "Invalid characters in uid"

    fn = "%s/%s" % (snac.basedir, "key.json")

    config, error = load_cfgfile(fn, SNAC._key)

    if config is None:
        return False, error

    snac.key = config

    fn = "%s/%s" % (snac.basedir, "user.json")

    config, error = load_cfgfile(fn, SNAC._user)

    if config is None:
        return False, error

    snac.user = config

    return True, error


def update_user(snac):
    """ updates the user configuration """

    fn = "%s/%s" % (snac.basedir, "user.json")

    return save_cfgfile(fn, snac.user)


""" connection """

def request_object(snac, url):
    """ requests an object, local or otherwise """

    status, body = 404, None

    base_url = snac._server.base_url()

    # is this the very same user?
    if url == snac.actor() or url.startswith("%s/" % snac.actor()):
        source = "local"

        # get the appropriate snac
        q_path = url[len(base_url):]

        status, body, ctype = SNAC.activitypub.get_handler(
                                snac, q_path, {}, "application/ld+json")

    # is the object of another user of this instance?
    elif url.startswith(base_url):
        source = "this instance"

        # get the appropriate snac
        q_path = url[len(base_url):]

        # get the uid
        uid = q_path.split("/")[1]

        # get the snac
        n_snac = SNAC.snac(snac._server, uid)

        if n_snac.ok:
            status, body, ctype = SNAC.activitypub.get_handler(
                                n_snac, q_path, {}, "application/ld+json")

    else:
        source = "remote"

        t = time.time()

        # do an HTTP request
        status, body = snac.http.request_signed(snac, "GET", url)

        snac.debug(2, "request_signed %f seconds %s" % (time.time() - t, url))


    if status >= 200 and status <= 299:
        try:
            body = json.loads(body)

        except:
            snac.log("cannot parse JSON for object %s" % url)
            status, body = 404, None

    snac.debug(2, "request_object() [%s] %s %s" % (source, url, status))

    return status, body


def add_to_followers(snac, actor, msg):
    """ adds a follower """

    fn = "%s/followers/%s.json" % (snac.basedir, md5(actor))

    with open(fn, "w") as f:
        f.write(json.dumps(msg, indent=4))
        snac.debug(2, "saved into followers %s %s" % (actor, fn))

    return 201 # created


def delete_from_followers(snac, actor, msg):
    """ deletes a follower """

    fn = "%s/followers/%s.json" % (snac.basedir, md5(actor))

    try:
        os.unlink(fn)
        snac.debug(2, "deleted from followers %s %s" % (actor, fn))
        ret = 200

    except:
        snac.debug(1, "I/O error deleting from followers %s %s" % (actor, fn))
        ret = 200 # or 400 bad request?

    return ret


def is_follower(snac, actor):
    """ returns True if someone is a follower """

    fn = "%s/followers/%s.json" % (snac.basedir, md5(actor))
    ret = True

    try:
        open(fn)
    except:
        ret = False

    snac.debug(2, "check followers %s %s" % (actor, ret))

    return ret


def followers(snac):
    """ iterates the followers """

    for fn in glob.glob("%s/followers/*.json" % snac.basedir):
        with open(fn, "r") as f:
            msg = json.loads(f.read())

        yield msg


def timeline_mtime(snac):
    """ returns the modification time of the timeline """

    try:
        s = os.stat("%s/timeline" % snac.basedir)
        mtime = s.st_mtime
    except:
        mtime = 0

    return mtime


def timeline_file_name(snac, id):
    """ returns the timeline file name for an id """

    l = glob.glob("%s/timeline/*-%s.json" % (snac.basedir, md5(id)))

    if len(l) > 0:
        fn = l[0]
    else:
        fn = None

    return fn


def get_from_timeline(snac, id):
    """ returns a message from the timeline """

    fn = timeline_file_name(snac, id)

    if fn is not None:
        with open(fn) as f:
            msg = json.loads(f.read())

        status = 200

    else:
        status, msg = 404, None

    return status, msg


def delete_from_timeline(snac, id):
    """ deletes a message from the timeline """

    fn = timeline_file_name(snac, id)

    if fn is not None:
        try:
            os.unlink(fn)
            snac.debug(1, "deleted from timeline %s" % id)

        except:
            snac.debug(1, "I/O error deleting from timeline %s" % id)
            pass

        # try to delete also from the local timeline
        try:
            lfn = fn.replace("/timeline/", "/local/")
            os.unlink(lfn)
            snac.debug(1, "deleted from local %s" % id)

        except:
            pass

    return fn


def add_to_timeline(snac, msg, id, parent=None):
    """ adds a message to the public timeline """

    fn = "%s/timeline/%s-%s.json" % (snac.basedir, snac.tid(), md5(id))

    try:
        os.stat(fn)
        snac.debug(1, "refusing to rewrite timeline %s %s" % (id, fn))
        return
    except:
        pass

    # add the metadata
    msg["_snac"] = {
        "children":     [],
        "parent":       parent,
        "liked_by":     [],
        "announced_by": []
    }

    with open(fn, "w") as f:
        f.write(json.dumps(msg, indent=4))
        snac.debug(1, "added to timeline %s %s" % (id, fn))

    if id.startswith(snac.actor()) or (parent and parent.startswith(snac.actor())):
        try:
            lfn = fn.replace("/timeline/", "/local/")
            os.link(fn, lfn)
            snac.debug(1, "added to local %s %s" % (id, lfn))

        except:
            snac.debug(1, "I/O error linking %s %s" % (fn, lfn))

    if parent is not None:
        # do we have the parent stored here?
        pfn = timeline_file_name(snac, parent)

        if pfn is not None:
            with open(pfn) as f:
                p_msg = json.loads(f.read())

            if msg["type"] == "Like":
                if p_msg["_snac"].get("liked_by") is None:
                    p_msg["_snac"]["liked_by"] = []

                p_msg["_snac"]["liked_by"].append(msg["actor"]);

            if msg["type"] == "Announce":
                if p_msg["_snac"].get("announced_by") is None:
                    p_msg["_snac"]["announced_by"] = []

                p_msg["_snac"]["announced_by"].append(msg["actor"]);

            # append this message to the children list
            p_msg["_snac"]["children"].append(id)

            # now rename all tree up the timeline
            while parent is not None:
                # delete old file
                try:
                    os.unlink(pfn)

                except:
                    snac.debug(1, "I/O error deleting parent from timeline %s" % pfn)

                # now re-insert the parent with a new timestamp
                npfn = "%s/timeline/%s-%s.json" % (snac.basedir, snac.tid(), md5(parent))

                with open(npfn, "w") as f:
                    f.write(json.dumps(p_msg, indent=4))
                    snac.debug(1, "updated parent to timeline %s %s" % (parent, npfn))

                # repeat for the local timeline
                try:
                    olfn = pfn.replace("/timeline/", "/local/")
                    nlfn = npfn.replace("/timeline/", "/local/")

                    os.unlink(olfn)
                    os.link(npfn, nlfn)
                    snac.debug(1, "updated parent to local %s %s" % (parent, nlfn))

                except:
                    pass

                parent = p_msg["_snac"]["parent"]

                if parent is not None:
                    pfn = timeline_file_name(snac, parent)

                    if pfn is not None:
                        with open(pfn) as f:
                            p_msg = json.loads(f.read())

                    else:
                        parent = None


def timeline(snac):
    """ iterates the entries in the timeline """

    # maximum entries to return
    max = snac.server["max_timeline_entries"]

    for fn in sorted(glob.glob("%s/timeline/*.json" % snac.basedir), reverse=True)[:max]:
        with open(fn) as f:
            msg = json.loads(f.read())

            yield msg


def purge_timeline(snac):
    """ deletes old entries from the timeline """

    snac.debug(2, "purging timeline for %s" % snac.user["uid"])

    mt = time.time() - (snac.server["timeline_purge_days"] * 24 * 3600)

    for fn in glob.glob("%s/timeline/*.json" % snac.basedir):
        # get the basename
        bn = fn.split("/")[-1]
        tt = float(bn.split("-")[0])

        if tt < mt:
            try:
                os.unlink(fn)
                snac.debug(1, "purged from timeline %s" % fn)
            except:
                snac.log("error purging from timeline %s" % fn)


def add_to_following(snac, actor, msg):
    """ adds someone to the following list """

    fn = "%s/following/%s.json" % (snac.basedir, md5(actor))

    with open(fn, "w") as f:
        f.write(json.dumps(msg, indent=4))
        snac.debug(2, "added to following %s %s" % (actor, fn))

    return 201 # created


def following(snac, actor):
    """ returns someone we're following or None """

    fn = "%s/following/%s.json" % (snac.basedir, md5(actor))

    try:
        with open(fn) as f:
            obj    = json.loads(f.read())
            status = 200

    except:
        status, obj = 404, None

    snac.debug(3, "get from following %s %s" % (actor, status))

    return status, obj


def delete_from_following(snac, actor):
    """ deletes from following """

    fn = "%s/following/%s.json" % (snac.basedir, md5(actor))

    try:
        os.unlink(fn)
        snac.debug(2, "deleted from following %s %s" % (actor, fn))
        ret = 200

    except:
        snac.debug(1, "I/O error deleting from following %s %s" % (actor, fn))
        ret = 200 # or 400 bad request?

    return ret


def mute(snac, actor):
    """ mutes an actor """

    fn = "%s/muted/%s" % (snac.basedir, md5(actor))

    with open(fn, "w") as f:
        f.write(actor)
        snac.debug(2, "added to muted %s %s" % (actor, fn))

    return 201 # created


def unmute(snac, actor):
    """ unmutes an actor """

    fn = "%s/muted/%s" % (snac.basedir, md5(actor))

    try:
        os.unlink(fn)
        snac.debug(2, "deleted from muted %s %s" % (actor, fn))
    except:
        snac.debug(1, "I/O error trying to delete from muted %s %s" % (actor, fn))

    return 200 # created


def is_muted(snac, actor):
    """ returns True if an actor is muted """

    fn = "%s/muted/%s" % (snac.basedir, md5(actor))

    try:
        open(fn)
        ret = True
    except:
        ret = False

    snac.debug(2, "check muted %s %s" % (actor, ret))

    return ret


def add_to_actors(snac, actor, msg):
    """ stores an actor """

    fn = "%s/actors/%s.json" % (snac.basedir, md5(actor))

    with open(fn, "w") as f:
        f.write(json.dumps(msg, indent=4))
        snac.debug(2, "added to actors %s %s" % (actor, fn))


def request_actor(snac, actor):
    """ requests an actor using the cache """

    fn = "%s/actors/%s.json" % (snac.basedir, md5(actor))

    try:
        s = os.stat(fn)
        mtime = s.st_mtime
    except:
        mtime = 0

    # seconds to consider a cached entry to be rotten
    max_time = 3600 * 36

    if mtime + max_time < time.time():
        # stale or new? request it
        snac.debug(2, "actor cache miss for %s %s" % (actor, fn))

        status, body = snac.data.request_object(snac, actor)

        if status >= 200 and status <= 299:
            add_to_actors(snac, actor, body)

        else:
            if mtime:
                # touch the file to change its mtime by adding an
                # innocuous blank at the end, so we don't hammer the site
                with open(fn, "a") as f:
                    f.write(" ")

                snac.debug(1, "serving stale actor %s %s" % (actor, status))
            else:
                snac.debug(1, "cannot retrieve actor %s %s" % (actor, status))

    else:
        # still valid
        snac.debug(2, "actor cache hit for %s %s" % (actor, fn))

    if mtime != 0:
        with open(fn, "r") as f:
            body = json.loads(f.read())

        status = 200

    return status, body


def enqueue_output(snac, actor, msg, retries=0):
    """ enqueue a message to be sent """

    if actor == snac.actor():
        snac.debug(1, "refusing to enqueue a message to ourselves")
        return

    fn = "%s/queue/%s.json" % (snac.basedir,
        snac.tid(retries * 60 * snac.server["queue_retry_minutes"]))

    with open(fn + ".tmp", "w") as f:
        r = {
            "type":    "output",
            "actor":   actor,
            "object":  msg,
            "retries": retries
        }

        f.write(json.dumps(r, indent=4))

    try:
        os.rename(fn + ".tmp", fn)
        snac.debug(2, "enqueue message for %s %s %d" % (actor, fn, retries))
    except:
        snac.log("I/O error enqueueing message for %s %s" % (actor, fn))


def queue(snac):
    """ iterates the queue """

    dir = "%s/queue" % snac.basedir
    t   = time.time()

    for fn in glob.glob(dir + "/*.json"):
        # get the basename
        bn = fn[0:-5].split("/")[-1]

        if float(bn) > t:
            snac.debug(2, "queue not yet time for %s" % fn)
        else:
            with open(fn, "r") as f:
                m = json.loads(f.read())

            # dequeue
            os.unlink(fn)

            snac.debug(2, "dequeued %s" % fn)

            yield m


def local_mtime(snac):
    """ returns the modification time of the local timeline """

    try:
        s = os.stat("%s/local" % snac.basedir)
        mtime = s.st_mtime
    except:
        mtime = 0

    return mtime


def locals(snac):
    """ iterates the entries in local """

    # maximum entries to return
    max = 256

    for fn in sorted(glob.glob("%s/local/*.json" % snac.basedir), reverse=True):
        max -= 1

        if max == 0:
            break

        with open(fn) as f:
            msg = json.loads(f.read())

            yield msg


def static(snac, url):
    """ serves an static file """

    id = url.split("/")[-1]
    fn = "%s/static/%s" % (snac.basedir, id)

    try:
        with open(fn) as f:
            body   = f.read()
            status = 200
    except:
        status, body = 404, None

    snac.debug(2, "get static %s %s" % (fn, status))

    return status, body


def purge(snac):
    """ purges all purgeable things """

    purge_timeline(snac)


def history_put(snac, content, basename):
    """ puts content to the history """

    fn = "%s/history/%s" % (snac.basedir, basename)

    try:
        f = open(fn, "w")
        f.write(content)
        snac.debug(2, "history put %s" % fn)

    except:
        snac.log("I/O error in history put %s" % fn)


def history_get(snac, basename):
    """ returns content from the history """

    fn = "%s/history/%s" % (snac.basedir, basename)

    try:
        s = os.stat(fn)
        mtime = s.st_mtime

        f = open(fn)
        return mtime, f.read()

        snac.debug(2, "history get hit %s %s" % (fn, mtime))

    except:
        snac.debug(2, "history get miss %s" % fn)
        return 0, None


def history_delete(snac, basename):
    """ deleted something from the history """

    fn = "%s/history/%s" % (snac.basedir, basename)

    try:
        os.unlink(fn)
        snac.debug(2, "history delete %s" % fn)

    except:
        pass


def history(snac):
    """ iterates the history """

    for hf in glob.glob("%s/history/*" % snac.basedir):
        yield hf.split("/")[-1]


#####################################

def create_keypair(key):
    """ creates a keypair if it's needed """

    if key["secret"] == "" or key["public"] == "":
        # do your magic thing
        pk = OpenSSL.crypto.PKey()
        pk.generate_key(OpenSSL.crypto.TYPE_RSA, 4096)

        pem = OpenSSL.crypto.dump_privatekey(
            OpenSSL.crypto.FILETYPE_PEM, pk)

        key["secret"] = pem.decode("ascii")

        pem = OpenSSL.crypto.dump_publickey(
            OpenSSL.crypto.FILETYPE_PEM, pk)

        key["public"] = pem.decode("ascii")

    return key


def archive(snac, dir, method, actor, msg, status=0, body=None):
    """ archives a message """
    if snac._server.dbglevel >= 1:
        fn = snac.basedir + "/archive/" + time.strftime("%Y-%m-%d") + ".log"

        with open(fn, "a") as f:
            f.write("%s (%f)\n" % (time.asctime(), time.time()))
            f.write("%s %s %s\n" % (dir, method, actor))
            f.write("%s\n" % json.dumps(msg, indent=4))

            if status != 0:
                f.write("status: %d\n" % status)

            if body is not None:
                f.write("body:\n")

                if isinstance(body, bytes):
                    body = body.decode("utf-8")

                    try:
                        body = json.loads(body)
                    except:
                        pass

                if isinstance(body, dict):
                    body = json.dumps(body, indent=4)

                f.write(body)

            f.write("---------------------------------------\n")

