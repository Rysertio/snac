# snac - ActivityPub thing by grunfink

import SNAC
import json
import time
import datetime
import re

public_address = "https://www.w3.org/ns/activitystreams#Public"

def request_actor(snac, actor):
    """ gets the actor object """

    status, body = snac.http.request_signed(snac, "GET", actor)

    if status == 200:
        try:
            body  = json.loads(body)
            inbox = body["inbox"]      # force existence of "inbox"
        except:
            status = 400
            body   = "<h1>400 Bad Request</h1>"

    return status, body


def send_to_inbox(snac, inbox, msg):
    """ sends a message to an inbox """

    status, body = snac.http.request_signed(snac, "POST", inbox, msg)

    snac.log("post to inbox %s %s" % (inbox, status))

    return status, body


def send_to_actor(snac, actor, msg):
    """ sends a message to an actor """

    # resolve the actor first
    status, body = snac.data.request_actor(snac, actor)

    if status == 200:
        try:
            status, body = send_to_inbox(snac, body["inbox"], msg)

        except:
            status, body = 400, None

    return status, body


def queue(snac):
    """ processes the output queue """

    for q_elem in snac.data.queue(snac):

        if q_elem["type"] != "output":
            snac.debug(1, "ignored q_elem type '%s'" % q_elem["type"])
            continue

        actor   = q_elem["actor"]
        msg     = q_elem["object"]
        retries = q_elem["retries"]

        # strip snac metadata
        try:
            del(msg["_snac"])
        except:
            pass

        # send
        status, body = send_to_actor(snac, actor, msg)

        if status < 200 or status >= 300:
            # failed; too much tries?
            if retries > snac.server["queue_retry_max"]:
                snac.log("giving up for %s %s" % (actor, status))
            else:
                snac.log("requeueing for %s %s" % (actor, status))

                # reenqueue
                snac.data.enqueue_output(snac, actor, msg, retries + 1)


def post_to_followers(snac, msg):
    """ post a message to all followers """

    for fo in snac.data.followers(snac):
        snac.data.enqueue_output(snac, fo["actor"], msg)


def msg_rcpts(snac, msg, expand_public=False):
    """ returns a set with all recipients of a message """

    rcpts = set()

    for lor in (msg.get("to"), msg.get("cc")):
        if lor is not None:
            if isinstance(lor, str):
                lor = [lor]

            for r in lor:
                # public? add all followers
                if expand_public and r == public_address:
                    for fo in snac.data.followers(snac):
                        rcpts.add(fo["actor"])
                else:
                    rcpts.add(r)

    return rcpts


def is_msg_public(snac, msg):
    """ checks if this message is public """

    if public_address in msg_rcpts(snac, msg, False):
        return True
    else:
        return False


def post(snac, msg):
    """ enqueue a message to all recipients """

    for r in msg_rcpts(snac, msg, True):
        snac.data.enqueue_output(snac, r, msg)


def process_mentions(snac, content):
    """ finds the mentions in the content """

    tag = []

    for m in set(re.findall("(@[A-Za-z0-9_]+@[a-z0-9-\.]+)", content)):
        # query the webfinger about this fellow
        status, body = snac.webfinger.request(snac, m)

        snac.debug(2, "mentioning %s %s" % (m, status))

        if status >= 200 and status <= 299:
            # found!

            href = ""

            # now find the type we're interested in
            for l in body["links"]:
                try:
                    if l["type"] == "application/activity+json":
                        href = l["href"]
                except:
                    pass

            if href != "":
                # add a tag
                tag.append({
                    "type":     "Mention",
                    "href":     href,
                    "name":     m
                })

                # replace the content with a link
                content = content.replace(m, "<a href=\"%s\">%s</a>" % (href, m))

            else:
                snac.debug(2, "cannot find an href in webfinger for %s" % m)

    return content, tag


""" messages """

def msg_follow(snac, actor):
    """ creates a Follow message """

    # the actor can be an alias and not the canonical one,
    # so request the actor object and use the value there
    status, actor_o = snac.data.request_actor(snac, actor)

    if status >= 200 and status <= 299:
        if actor_o["id"] != actor:
            snac.log("actor to follow is an alias -- canonicalized %s %s" % (
                actor, actor_o["id"]))
            actor = actor_o["id"]

        msg = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id":       "%s/f/%s" % (snac.actor(), snac.tid()),
            "type":     "Follow",
            "actor":    snac.actor(),
            "object":   actor
        }

    else:
        snac.log("cannot create a follow message for %s" % actor)
        msg = None

    return msg


def msg_actor(snac):
    """ creates our actor message """

    avatar = snac.user["avatar"]
    if avatar == "":
        avatar = "%s%s" % (snac._server.base_url(), "/susie.png")

    icon_ctype = "image/jpeg"

    if avatar.endswith(".gif"):
        icon_ctype = "image/gif"
    elif avatar.endswith(".png"):
        icon_ctype = "image/png"

    msg = {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            "https://w3id.org/security/v1"
            ],
        "id":                snac.actor(),
        "url":               snac.actor(),
        "type":              "Person",
        "preferredUsername": snac.user["uid"],
        "name":              snac.user["name"],
        "inbox":             snac.actor("/inbox"),
        "outbox":            snac.actor("/outbox"),
        "followers":         snac.actor("/followers"),
        "following":         snac.actor("/following"),
        "summary":           snac.html.not_really_markdown(snac.user["bio"]),
        "published":         snac.user["published"],
        "icon": {
            "mediaType":     icon_ctype,
            "type":          "Image",
            "url":           avatar
        },
        "publicKey": {
            "id":            snac.actor() + "#main-key",
            "owner":         snac.actor(),
            "publicKeyPem":  snac.key["public"]
        }
    }

    return msg


def msg_note(snac, content, rcpts=None, irt=None):
    """ creates a Note message """

    id      = snac.actor("/p/%s" % snac.tid())
    context = id + "#ctxt"

    if rcpts is None:
        rcpts = set()
    else:
        rcpts = set(rcpts)

    cc    = set()
    tag   = []

    # format content
    f_content = snac.html.not_really_markdown(content)

    f_content, tag = process_mentions(snac, f_content)

    if irt is not None:
        # if there is an inReplyTo, resolve the object and add its actor
        status, irt_msg = snac.data.request_object(snac, irt)

        if status >= 200 and status <= 299:
            if irt_msg["type"] == "Create":
                irt_msg = irt_msg["object"]

            try:
                # get the context
                context = irt_msg["context"]
            except:
                pass

            try:
                rcpts.add(irt_msg["attributedTo"])

            except:
                snac.log("inReplyTo '%s' lacks an attributedTo %s %s" % (
                    irt_msg["type"], irt, status))

            # if the message to be answered is public, so be this one
            if is_msg_public(snac, irt_msg):
                rcpts.add(public_address)

        else:
            snac.log("error getting inReplyTo object %s %s" % (irt, status))

    # iterate all mentions in tags and add them to cc
    for t in tag:
        if t["type"] == "Mention":
            cc.add(t["href"])

    if len(rcpts) == 0:
        rcpts.add(public_address)

    msg = {
        "@context":     "https://www.w3.org/ns/activitystreams",
        "type":         "Note",
        "attributedTo": snac.actor(),
        "summary":      "",
        "content":      f_content,
        "context":      context,
        "id":           id,
        "url":          id,
        "to":           list(rcpts),
        "cc":           list(cc),
        "published":    datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inReplyTo":    irt,
        "tag":          tag
    }

    return msg


def msg_create(snac, object):
    """ creates a Create message """

    msg = {
        "@context":     "https://www.w3.org/ns/activitystreams",
        "type":         "Create",
        "actor":        snac.actor(),
        "id":           object["id"] + "/Create",
        "to":           object["to"],
        "cc":           object["cc"],
        "published":    datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "object":       object,
        "attributedTo": snac.actor()
    }

    return msg


def msg_update(snac, object):
    """ creates an Update message """

    msg = {
        "@context":     "https://www.w3.org/ns/activitystreams",
        "type":         "Update",
        "actor":        snac.actor(),
        "id":           object["id"] + "/Update",
        "to":           public_address,
        "published":    datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "object":       object
    }

    return msg


def msg_delete(snac, id):
    """ creates an Delete message """

    msg = {
        "@context":     "https://www.w3.org/ns/activitystreams",
        "type":         "Delete",
        "actor":        snac.actor(),
        "id":           id + "/Delete",
        "to":           public_address,
        "published":    datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "object":       {
            "type":     "Tombstone",
            "id":       id
        }
    }

    return msg


def msg_admiration(snac, object, like):
    """ creates a Like or Announce message """

    id = snac.actor("/p/%s" % snac.tid())

    if like is True:
        type = "Like"
    else:
        type = "Announce"

    if isinstance(object, str):
        # resolve the object
        object_id = object
        status, object = snac.data.request_object(snac, object_id)

        if status < 200 or status > 299:
            snac.log("cannot resolve object to admire %s %s" % (object_id, status))
            object = None

    if object is not None:
        rcpts = [
            public_address,
            object["attributedTo"]
        ]

        msg = {
            "@context":     "https://www.w3.org/ns/activitystreams",
            "type":         type,
            "actor":        snac.actor(),
            "id":           id + "/" + type,
            "to":           rcpts,
            "published":    datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "object":       object
        }

    else:
        msg = None

    return msg


def msg_undo(snac, object):
    """ creates an Undo message for an object """

    msg = {
        "@context":     "https://www.w3.org/ns/activitystreams",
        "type":         "Undo",
        "actor":        snac.actor(),
        "id":           object["id"] + "/Undo",
        "to":           object["actor"],
        "published":    datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "object":       object
    }

    return msg


""" HTTP handlers """

def get_handler(snac, q_path, q_vars, acpt):
    """ GET handler """

    status, body, ctype = 0, None, "application/activity+json"

    # not activitypub? done
    if "application/activity+json" not in acpt and "application/ld+json" not in acpt:
        return status, body, ctype

    if q_path == "/%s" % snac.user["uid"]:
        # main user query

        body = msg_actor(snac)

        status = 200

    elif q_path == "/%s/outbox" % snac.user["uid"]:
        # create a list with the latest entries
        entries = []

        for e in snac.data.locals(snac):
            if e["type"] != "Like":
                del(e["_snac"])

                entries.append(e)

                if len(entries) >= 20:
                    break

        body = {
            "@context":     "https://www.w3.org/ns/activitystreams",
            "attributedTo": snac.actor(),
            "id":           snac.actor("/outbox"),
            "orderedItems": entries,
            "totalItems":   len(entries),
            "type":         "OrderedCollection"
        }

        status = 200

    elif q_path == "/%s/followers" % snac.user["uid"]:
        body = {
            "@context":     "https://www.w3.org/ns/activitystreams",
            "attributedTo": snac.actor(),
            "id":           snac.actor("/followers"),
            "orderedItems": [],
            "totalItems":   0,
            "type":         "OrderedCollection"
        }

        status = 200

    elif q_path == "/%s/following" % snac.user["uid"]:
        body = {
            "@context":     "https://www.w3.org/ns/activitystreams",
            "attributedTo": snac.actor(),
            "id":           snac.actor("/following"),
            "orderedItems": [],
            "totalItems":   0,
            "type":         "OrderedCollection"
        }

        status = 200

    elif q_path.startswith("/%s/p/" % snac.user["uid"]):
        # a post in the local list

        id = snac.actor(q_path.replace("/%s" % snac.user["uid"], ""))

        status, body = snac.data.get_from_timeline(snac, id)

    else:
        status = 404

    if body is not None:
        body = json.dumps(body)

    if status != 0:
        snac.debug(2, "serving get %s %s" % (q_path, status))

    return status, body, ctype


def post_handler(snac, q_path, q_vars, acpt, p_data, headers):
    """ POST handler """

    status, body, ctype = 0, None, "application/activity+json"

    # not activitypub? done
    if "application/activity+json" not in acpt and "application/ld+json" not in acpt:
        return status, body, ctype

    # error by default
    status = 404

    # q_path not inbox? done, with error
    if q_path != "/%s/inbox" % snac.user["uid"]:
        snac.debug(2, "discarding post path %s" % q_path)
        return status, body, ctype

    # decode object
    try:
        msg   = json.loads(p_data)
        actor = msg["actor"]
        mtype = msg["type"]
    except:
        msg = None

    # error decoding JSON?
    if msg is None:
        snac.debug(1, "error decoding JSON payload in %s" % q_path)
        return 400, "<h1>400 Bad Request</h1>", "text/html"

    snac.data.archive(snac, "<", "POST", actor, msg)

    if actor == snac.actor():
        snac.log("dropping message for me")
        return 400, "400 Bad Request", "text/plain"

    # check headers
    s_status = snac.http.check_signature(snac, q_path, p_data, headers)

    if s_status < 200 or s_status > 299:
        if s_status != 410:
            snac.log("signature check failure from %s %s" % (actor, s_status))

        return 400, "<h1>400 Bad Request</h1>", "text/html"

    status = 200

    # process the message
    snac.debug(2, "message type '%s' received from %s" % (mtype, actor))

    if mtype == "Follow":
        # build a confirmation
        reply = {
            "type":     "Accept",
            "id":       "%s/c/%s" % (snac.actor(), snac.tid()),
            "object":   msg,
            "actor":    snac.actor(),
            "to":       actor,
            "@context": "https://www.w3.org/ns/activitystreams"
        }

        snac.activitypub.post(snac, reply)

        snac.data.add_to_timeline(snac, msg, msg["id"])
        status = snac.data.add_to_followers(snac, actor, msg)

        if status >= 200 and status <= 299:
            snac.log("now following us %s" % actor)
        else:
            snac.log("error confirming follow %s %s" % (actor, status))

    elif mtype == "Undo":
        utype = msg["object"]["type"]

        if utype == "Follow":
            # this fellow is no longer following us
            status = snac.data.delete_from_followers(snac, actor, msg)

            if status >= 200 and status <= 299:
                snac.log("no longer following us %s" % actor)
            else:
                snac.log("error deleting follower %s %s" % (actor, status))

        if utype == "Like" or utype == "Announce":
            # they do not admire us
            snac.data.delete_from_timeline(snac, msg["object"]["id"])

            snac.log("deleted admiration %s %s" % (actor, msg["object"]["id"]))

        else:
            snac.debug(1, "ignored 'Undo' for object type '%s'" % utype)

    elif mtype == "Create":
        utype = msg["object"]["type"]

        if utype == "Note":
            if snac.data.is_muted(snac, actor):
                snac.log("dropping note from muted actor %s" % actor)

            else:
                # get the in_reply_to
                try:
                    in_reply_to = msg["object"]["inReplyTo"]
                except:
                    in_reply_to = None

                # recursively download in_reply_tos
                nid = in_reply_to
                while nid is not None:
                    irt2 = None

                    s_status, s_body = snac.data.get_from_timeline(snac, nid)

                    if s_status < 200 or s_status > 299:
                        s_status, s_body = snac.data.request_object(snac, nid)

                        if s_status >= 200 and s_status <= 299:
                            # does it have an in_reply_to itself?
                            try:
                                irt2 = s_body["inReplyTo"]
                            except:
                                try:
                                    irt2 = s_body["object"]["inReplyTo"]
                                except:
                                    pass

                            snac.data.add_to_timeline(snac, s_body, nid, irt2)

                        snac.debug(2, "requested in_reply_to %s %s" % (nid, s_status))

                    else:
                        snac.debug(2, "in_reply_to already here %s" % nid)

                        # this is ugly af
                        try:
                            irt2 = s_body["inReplyTo"]
                        except:
                            try:
                                irt2 = s_body["object"]["inReplyTo"]
                            except:
                                pass

                    nid = irt2

                # store the message itself
                snac.data.add_to_timeline(snac, msg, msg["object"]["id"], in_reply_to)
                snac.log("new note %s" % actor)

        else:
            snac.debug(1, "ignored 'Create' for object type '%s'" % utype)

    elif mtype == "Accept":
        utype = msg["object"]["type"]

        if utype == "Follow":
            # this guy is confirming our follow request... is it true?
            s_status, s_body = snac.data.following(snac, actor)

            if s_status == 200:
                status = snac.data.add_to_following(snac, actor, msg)
                snac.log("confirmed follow from %s %s" % (actor, status))

            else:
                snac.log("spurious follow accept from %s %s" % (actor, s_status))

        else:
            snac.debug(1, "ignored 'Accept' for object type '%s'" % utype)

    elif mtype == "Like" or mtype == "Announce":
        # someone likes or boosts something

        if snac.data.is_muted(snac, actor):
            snac.log("dropped admiration from muted actor %s" % actor)

        else:
            if isinstance(msg["object"], str):
                s_status, s_body = snac.data.request_object(snac, msg["object"])

                if s_status >= 200 and s_status <= 299:
                    # object taken; store
                    msg["object"] = s_body
                else:
                    # cannot resolve it? meh
                    msg = None

            if msg is not None:
                if msg["object"]["type"] == "Create":
                    ato = msg["object"]["object"]["attributedTo"]
                    rel = msg["object"]["object"]["id"]
                else:
                    ato = msg["object"]["attributedTo"]
                    rel = msg["object"]["id"]

                if snac.data.is_muted(snac, ato):
                    snac.log("dropped admiration about muted actor %s" % ato)
                else:
                    snac.data.add_to_timeline(snac, msg, msg["id"], rel)
                    snac.log("new admiration %s" % actor)

            else:
                snac.debug(1, "dropping admiration %s %s" % (actor, s_status))

    elif mtype == "Update":

        utype = msg["object"]["type"]

        if utype == "Person" or utype == "Group":
            # some animal has changed something about itself
            snac.data.add_to_actors(snac, actor, msg["object"])
            snac.log("updated actor %s" % actor)

        else:
            # probably a Note that was edited
            snac.debug(1, "ignored 'Update' for object type '%s'" % utype)

    elif mtype == "Delete":
        to_delete = None

        # some software (i.e. honk) returns the notes unresolved
        if isinstance(msg["object"], str):
            to_delete = msg["object"]

        elif msg["object"]["type"] == "Tombstone":
            to_delete = msg["object"]["id"]

        if to_delete is not None:
            if snac.data.delete_from_timeline(snac, to_delete) is None:
                snac.log("trying to delete non-existent from timeline %s" % to_delete)

            else:
                snac.log("delete request %s %s" % (actor, to_delete))

        else:
            snac.log("ignored delete from %s" % actor)

    else:
        snac.debug(1, "message type '%s' ignored" % mtype)

    if status != 0:
        snac.debug(2, "serving post %s %s" % (q_path, status))

    return status, body, ctype
