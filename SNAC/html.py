# snac - ActivityPub thing by grunfink

import re
import json
import mimetypes
import base64
import urllib
import time
import SNAC

def not_really_markdown(content):
    """ converts content using some Markdown rules """

    f_content = ""

    in_pre = False
    in_blq = False

    for ss in content.replace("\r", "").split("\n"):

        ss = re.sub("`([^`]+)`", "<code>\g<1></code>", ss)
        ss = re.sub("\*\*([^\*]+)\*\*", "<b>\g<1></b>", ss)
        ss = re.sub("\*([^\*]+)\*", "<i>\g<1></i>", ss)

        ss = re.sub("(https?://[^ ]+)", "<a href=\"\g<1>\">\g<1></a>", ss)

        if ss.startswith("```"):
            if not in_pre:
                f_content += "<pre>"
                in_pre = True

            else:
                f_content += "</pre>"
                in_pre = False

            continue

        if ss.startswith(">"):
            ss = ss[1:].strip()

            if not in_blq:
                f_content += "<blockquote>"
                in_blq = True

            f_content += ss + "<br>"
            continue

        if in_blq:
            f_content += "</blockquote>"
            in_blq = False

        f_content += ss + "<br>"

    if in_blq:
        f_content += "</blockquote>"
    if in_pre:
        f_content += "</pre>"

    # some beauty fixes
    f_content = f_content.replace("</blockquote><br>", "</blockquote>")

    return f_content


def _get_actor(snac, msg, actor_u):
    """ gets the actor from a message and completes the fields """

    s_status, actor = snac.data.request_actor(snac, actor_u)

    if s_status < 200 or s_status > 299:
        snac.log("bad actor in timeline %s %s" % (actor_u, s_status))
        actor = None

    else:
        # if the actor has no name, simulate one from the url
        if actor["name"] == "":
            actor["name"] = actor_u.split("/")[-1]

        # set an avatar
        try:
            actor["_avatar"] = actor["icon"]["url"]
        except:
            actor["_avatar"] = "data:image/png;base64, " + SNAC.susie.replace("\n", "")

        actor["_actor_u"] = actor_u

    return actor


def _get_icon(snac, msg, action):
    """ returns the HTML for a message icon """

    s = ""

    if msg["type"] == "Create":
        msg = msg["object"]

    if snac.activitypub.is_msg_public(snac, msg):
        private = ""
    else:
        private = "<span title=\"private\">&#128274;</span>"

    if msg.get("published"):
        date = msg["published"].replace("T", " ").replace("Z", "")
    else:
        # Mastodon Likes do not have a "published" date
        date = "&nbsp;"

    a = msg["_actor"]

    s += "<div class=\"snac-content-header\">\n"
    s += "<p><img class=\"snac-avatar\" src=\"%s\"/>\n" % a["_avatar"]
    s += "<a href=\"%s\" class=\"p-author h-card snac-author\">%s</a>" % (
        a["_actor_u"], a["name"])

    if msg["type"] == "Note":
        s += " <a href=\"%s\">»</a>" % msg["id"]

    s += " %s %s<br>\n" % (private, action)

    s += "<time class=\"dt-published snac-pubdate\">%s</time>\n" % date
    s += "</div>\n"

    return s


def entry(snac, local, msg, seen, level=0):
    """ returns the HTML for an entry """

    # skip already seen stories
    if msg["id"] in seen:
        snac.debug(2, "already seen %s" % msg["id"])
        return ""

    # list of emojis to be replaced
    emojis = []

    # get the first message
    msg_1 = msg

    # get the first actor
    if msg["type"] == "Note":
        msg_1["_actor"] = _get_actor(snac, msg, msg["attributedTo"])
    else:
        msg_1["_actor"] = _get_actor(snac, msg, msg["actor"])

    # no actor? skip this entry
    if msg_1["_actor"] is None:
        return ""

    # never show non-public messages in local timelines
    if local is True and not snac.activitypub.is_msg_public(snac, msg):
        return ""

    try:
        emojis += msg_1["_actor"]["tag"]
    except:
        pass

    children = msg_1["_snac"]["children"]

    s = ""

    # add an anchor
    my_md5 = snac.data.md5(msg["id"])
    s += "<a name=\"%s\"></a>" % my_md5

    if level == 0:
        s += "\n<div class=\"snac-post\">\n"
    else:
        s += "\n<div class=\"snac-child\"> <!-- %d -->\n" % level

    # create? resolve again
    if msg["type"] == "Create":
        msg = msg["object"]

    action = ""

    if msg["type"] in ("Follow", "Like", "Announce"):
        # set the origin of this entry

        if msg["type"] == "Like":
            action = "&#9733;"
        elif msg["type"] == "Announce":
            action = "&#8634;"
        elif msg["type"] == "Follow":
            action = snac.L("is following you")

        # re-resolve
        if isinstance(msg["object"], dict):
            msg = msg["object"]

        # if it's a Create, resolve again
        if msg["type"] == "Create":
            msg = msg["object"]

    if msg["type"] == "Note":
        if level == 0 and action == "" and msg_1["_snac"]["parent"] is not None:
            action = "%s <a href=\"%s\">»</a>" % (snac.L("in reply to"), msg_1["_snac"]["parent"])

        # who wrote this?
        msg["_actor"] = _get_actor(snac, msg, msg["attributedTo"])

        if snac.data.is_muted(snac, msg["_actor"]["_actor_u"]):
            snac.debug(2, "silencing note for muted actor %s" % msg["_actor"]["_actor_u"])
            return ""

    if level == 0:
        if action != "":
            s += "<div class=\"snac-origin\">"
            s += "<a href=\"%s\">%s</a> %s" % (
                msg_1["_actor"]["_actor_u"],
                msg_1["_actor"]["name"],
                action
            )
            s += "</div>\n"

        s += _get_icon(snac, msg, "")

    else:
        s += _get_icon(snac, msg_1, action)

    if msg["type"] == "Note" and (level == 0 or action == ""):
        c = msg["content"]

        c = c.replace("\r", "")

        while c.endswith("<br><br>"):
            c = c[:-4]

        c = c.replace("<br><br>", "<p>")

        if not c.startswith("<p>"):
            c = "<p>%s</p>" % c

        # add the possible emoji tags
        try:
            emojis += msg["tag"]
        except:
            pass

        s += "<div class=\"e-content snac-content\">\n"
        s += "%s\n" % c

        if msg.get("attachment") is not None:
            # iterate the attachments
            for att in msg["attachment"]:
                if att["mediaType"].startswith("image/"):
                    url  = att.get("url")
                    name = att.get("name")

                    if url is not None:
                        s += "<p><img src=\"%s\" alt=\"%s\"/></p>\n" % (url, name)

        s += "</div>\n"

    show_controls = not local

    # no controls for nested entries that are not notes
    if level > 0 and msg_1["type"] != "Create":
        show_controls = False

    if show_controls:
        # add controls
        s += "<div class=\"snac-controls\">\n"

        if msg["type"] == "Note":
            relevant_actor = msg["attributedTo"]
        else:
            relevant_actor = msg_1["actor"]

        status, obj = snac.data.following(snac, relevant_actor)

        if obj is not None:
            following = True
        else:
            following = False

        # like
        s += "<form method=\"post\" action=\"%s\">\n" % snac.actor("/admin/action")
        s += "<input type=\"hidden\" name=\"id\" value=\"%s\">\n" % msg["id"]
        s += "<input type=\"hidden\" name=\"cid\" value=\"%s\">\n" % msg_1["id"]
        s += "<input type=\"hidden\" name=\"actor\" value=\"%s\">\n" % relevant_actor

        if msg["type"] == "Note":
            s += "<input type=\"button\" name=\"action\" "
            s += "value=\"%s\" onclick=\"%s\">\n" % (
                snac.L("Reply"),
                    ("x = document.getElementById('%s_reply'); " % my_md5) +
                    "if (x.style.display == 'block') " +
                    "   x.style.display = 'none'; else " +
                    "   x.style.display = 'block';"
            )

        if relevant_actor != snac.actor():
            if msg_1["type"] != "Follow" and snac.activitypub.is_msg_public(snac, msg):
                # get the list of likes for this container
                l = msg_1["_snac"].get("liked_by")

                if l is None or not snac.actor() in l:
                    s += "<input type=\"submit\" name=\"action\" " + \
                        "class=\"snac-btn-like\" value=\"%s\">\n" % snac.L("Like")

                # get the list of boosts for this container
                l = msg_1["_snac"].get("announced_by")

                if l is None or not snac.actor() in l:
                    s += "<input type=\"submit\" name=\"action\" " + \
                        "class=\"snac-btn-boost\" value=\"%s\">\n" % snac.L("Boost")

            if following:
                s += "<input type=\"submit\" name=\"action\" " + \
                    "class=\"snac-btn-unfollow\" value=\"%s\">\n" % snac.L("Unfollow")
            else:
                s += "<input type=\"submit\" name=\"action\" " + \
                    "class=\"snac-btn-follow\" value=\"%s\">\n" % snac.L("Follow")
                s += "<input type=\"submit\" name=\"action\" " + \
                    "class=\"snac-btn-mute\" value=\"%s\">\n" % snac.L("MUTE")

        s += "<input type=\"submit\" name=\"action\" " + \
            "class=\"snac-btn-delete\" value=\"%s\">\n" % snac.L("Delete")

        s += "</form>\n"
#        s += "&#9733;&nbsp;"

#        s += "&#8634;&nbsp;"

        # write
#        s += "&#128393;&nbsp;&nbsp;&nbsp;&nbsp;"

        # mute
#        s += "&#128263;"

        if msg["type"] == "Note":
            # iterate the citations and add them
            ct = ""

            try:
                for t in msg["tag"]:
                    if t["type"] == "Mention" and t["href"] != snac.actor():
                        if len(t["name"].split("@")) < 3:
                            # sometimes the name is only the user,
                            # so query the webfinger for a better name
                            snac.debug(2, "crappy short mention name %s" % t["name"])

                            s_status, s_body = snac.webfinger.request(snac, t["href"])

                            if s_status >= 200 and s_status <= 299:
                                try:
                                    name = s_body["subject"].replace("acct:", "@")

                                except:
                                    name = ""

                        else:
                            name = t["name"]

                        ct += "%s " % name
            except:
                pass

            s += "<p><div class=\"snac-note\" style=\"display: none\" id=\"%s_reply\">\n" % my_md5
            s += "<form method=\"post\" action=\"%s\" id=\"%s_reply_form\">\n" % (
                snac.actor("/admin/note"), my_md5)
            s += "<textarea class=\"snac-textarea\" name=\"content\" "
            s += "rows=\"4\" wrap=\"virtual\" required=\"required\">%s</textarea>\n" % ct
            s += "<input type=\"hidden\" name=\"in_reply_to\" value=\"%s\">\n" % msg["id"]
            s += "<input type=\"submit\" class=\"button\" value=\"%s\">\n" % snac.L("Post")
            s += "</form><p>\n"
            s += "</div>\n"

        else:
            s += "<p>\n"

        s += "</div>\n"

    if len(children):
        # children section
        s += "<div class=\"snac-children\">\n"

        if len(children) > 3:
            s += "<details><summary>...</summary>\n"

        left = len(children) - 3

        for chid in children:
            status, s_msg = snac.data.get_from_timeline(snac, chid)

            if left == 0:
                s += "</details>\n"

            if s_msg is not None:
                s += entry(snac, local, s_msg, seen, level + 1)

            else:
                snac.debug(2, "cannot read from timeline child %s" % chid)

            left -= 1

        s += "</div>\n"

    s += "</div>\n"

    # finally, iterate the emojis
    for e in emojis:
        if isinstance(e, dict) and e["type"] == "Emoji":
            en = e["name"]
            try:
                url = e["icon"]["url"]
            except:
                url = None

            if url is not None:
                s = s.replace(en, "<img src=\"%s\"/ style=\"height: 1.5em\">" % url)

    # add to seen
    seen.add(msg_1["id"])

    return s


def timeline(snac, local, seq):
    """ returns the HTML for a timeline """

    t1 = time.time()

    seen = set()

    s  = "<!DOCTYPE html>\n"
    s += "<html>\n<head>\n"
    s += "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>\n"
    s += "<meta name=\"generator\" content=\"%s\"/>\n" % snac.user_agent

    for url in snac.server["cssurls"]:
        if url != "":
            s += "<link rel=\"stylesheet\" type=\"text/css\" href=\"%s\"/>\n" % url

    # if there is a style.css served as static, embed it
    status, css = snac.data.static(snac, "%s/s/style.css" % snac.user["uid"])

    if status == 200:
        s += "<style>\n%s</style>\n" % css

    s += "<title>%s</title>\n" % snac.user["name"]
    s += "<body>\n"

    if local:
        s += "<nav style=\"snac-top-nav\"><a href=\"%s\">admin</a></nav>\n" % snac.actor("/admin")
    else:
        s += "<nav style=\"snac-top-nav\"><a href=\"%s\">public</a></nav>\n" % snac.actor()

    # header
    s += "<div class=\"h-card snac-top-user\">\n"
    s += "<p class=\"p-name snac-top-user-name\">%s</p>\n" % snac.user["name"]
    s += "<p class=\"snac-top-user-id\">@%s@%s</p>\n" % (snac.user["uid"], snac.server["host"])
    s += "<div class=\"p-note snac-top-user-bio\">%s</div>\n" % not_really_markdown(snac.user["bio"])
    s += "</div>\n"

    if local is not True:
        s += "<div class=\"snac-top-controls\">\n"

        # add a post edit box
        s += "<div class=\"snac-note\">\n"
        s += "<form method=\"post\" action=\"%s\">\n" % snac.actor("/admin/note")
        s += "<textarea class=\"snac-textarea\" name=\"content\" "
        s += "rows=\"8\" wrap=\"virtual\" required=\"required\"></textarea>\n"
        s += "<input type=\"hidden\" name=\"in_reply_to\" value=\"\">\n"
        s += "<input type=\"submit\" class=\"button\" value=\"%s\">\n" % snac.L("Post")
        s += "</form><p>\n"
        s += "</div>\n"

        s += "<div class=\"snac-top-controls-more\">\n"

        s += "<details><summary>%s</summary>\n" % snac.L("More options...")

        # webfinger search
#        s += "<form method=\"post\" action=\"%s\">\n" % snac.actor("/admin/webfinger")
#        s += "<input type=\"text\" name=\"query\" required=\"required\">\n"
#        s += "<input type=\"submit\" class=\"button\" disabled value=\"%s\">\n" % (
#            snac.L("Search people by Id"))
#        s += "</form></p>\n"

        # follow by url
        s += "<form method=\"post\" action=\"%s\">\n" % snac.actor("/admin/action")
        s += "<input type=\"text\" name=\"actor\" required=\"required\">\n"
        s += "<input type=\"submit\" name=\"action\" value=\"%s\"> %s\n" % (
            snac.L("Follow"), snac.L("(by URL or user@host)"))
        s += "</form></p>\n"

        # boost by url
        s += "<form method=\"post\" action=\"%s\">\n" % snac.actor("/admin/action")
        s += "<input type=\"text\" name=\"id\" required=\"required\">\n"
        s += "<input type=\"submit\" name=\"action\" value=\"%s\"> %s\n" % (
            snac.L("Boost"), snac.L("(by URL)"))
        s += "</form></p>\n"

        # the user configuration form
        s += "<details><summary>%s</summary>\n" % snac.L("User setup...")

        s += "<div class=\"snac-user-setup\">\n"
        s += "<form method=\"post\" action=\"%s\">\n" % snac.actor("/admin/user-setup")

        s += "<p>%s:<br>\n" % snac.L("User name")
        s += "<input type=\"text\" name=\"name\" value=\"%s\"></p>\n" % snac.user["name"]

        s += "<p>%s:<br>\n" % snac.L("Avatar URL")
        s += "<input type=\"text\" name=\"avatar\" value=\"%s\"></p>\n" % snac.user["avatar"]

        s += "<p>%s:<br>\n" % snac.L("Bio")
        s += "<textarea name=\"bio\" cols=60 rows=4>%s</textarea></p>\n" % snac.user["bio"]

        s += "<p>%s:<br>\n" % snac.L("Password (only to change it)")
        s += "<input type=\"password\" name=\"passwd1\" value=\"\"></p>\n"

        s += "<p>%s:<br>\n" % snac.L("Repeat Password")
        s += "<input type=\"password\" name=\"passwd2\" value=\"\"></p>\n"

        s += "<input type=\"submit\" class=\"button\" value=\"%s\">\n" % snac.L("Update user info")
        s += "</form>\n"

        s += "</div>\n"
        s += "</details>\n"

        s += "</details>\n"

        s += "</div>\n"

        s += "</div>\n"

    s += "<div class=\"snac-posts\">\n"

    for msg in seq:
        s += entry(snac, local, msg, seen)

    s += "</div>\n"

    if local is True:
        # add the history
        s += "<div class=\"snac-history\">\n"
        s += "<p class=\"snac-history-title\">%s</p>\n" % snac.L("History")
        s += "<ul>\n"

        for hf in snac.data.history(snac):
            if not hf.startswith("_"):
                s += "<li><a href=\"%s\">%s</a></li>\n" % (
                    snac.actor("/h/%s" % hf), hf.replace(".html", ""))

        s += "</ul>\n"
        s += "</div>\n"

    s += "<div class=\"snac-footer\">\n"
    s += "<a href=\"%s\">%s</a> - " % (snac._server.base_url(), snac.L("about this site"))
    s += "powered by <abbr title=\"Social Networks Are Crap\">snac</abbr>.</div>\n"

    s += "<!-- %f seconds -->\n" % (time.time() - t1)

    s += "</body>\n</html>\n"

    return s


def request_authorization(snac, headers):
    """ ensures the user is authorized """

    logged_in = False

    try:
        auth = headers["Authorization"]

        if auth.startswith("Basic "):
            auth = auth[6:]
        else:
            auth = None

    except:
        auth = None

    if auth is not None:
        # decode and split
        i_uid, i_passwd = base64.b64decode(auth).decode().split(":", 2)

        # check
        logged_in = snac.data.check_password(i_uid, i_passwd, snac.user["passwd"])

        snac.debug(2, "basic auth identification %s" % logged_in)

    return logged_in


""" HTTP handlers """

def get_handler(snac, q_path, q_vars, acpt, headers):
    """ GET handler """

    status, body, ctype = 404, "<h1>404 Not Found</h1>", "text/html"

    if q_path.endswith("/"):
        q_path = q_path[:-1]

    logged_in = False

    # all things starting with /admin must be authenticated
    if q_path.startswith("/%s/admin" % snac.user["uid"]):
        logged_in = request_authorization(snac, headers)

        if logged_in is False:
            return 401, "401 Authorization Required", "text/plain"

    if q_path == "/%s" % snac.user["uid"]:

        hf = time.strftime("%Y-%m.html")

        # get cached output
        mtime, body = snac.data.history_get(snac, hf)

        if mtime > snac.data.timeline_mtime(snac):
            # cached HTML is newer than timeline; serve cached
            status = 200

            snac.debug(1, "serving cached local timeline")

        else:
            status, body = 200, timeline(snac, True, snac.data.locals(snac))

            snac.data.history_put(snac, body, hf)

    elif q_path == "/%s/admin" % snac.user["uid"]:

        # get cached output
        mtime, body = snac.data.history_get(snac, "_timeline.html")

        if mtime > snac.data.timeline_mtime(snac):
            # cached HTML is newer than timeline; serve cached
            status = 200

            snac.debug(1, "serving cached timeline")

        else:
            status, body = 200, timeline(snac, False, snac.data.timeline(snac))

            snac.data.history_put(snac, body, "_timeline.html")

    elif q_path.startswith("/%s/p/" % snac.user["uid"]):

        entry_id = snac.actor("/p/%s" % q_path.split("/")[-1])

        status, body = snac.data.get_from_timeline(snac, entry_id)

        if status >= 200 and status <= 299:
            status, body = 200, timeline(snac, True, [body])

    elif q_path.startswith("/%s/s/" % snac.user["uid"]):

        status, body = snac.data.static(snac, q_path)

        ctype, enc = mimetypes.guess_type(q_path)

    elif q_path.startswith("/%s/h/" % snac.user["uid"]):

        hf = q_path.split("/")[-1]

        if not hf.startswith("_"):
            mtime, body = snac.data.history_get(snac, hf)

            if mtime != 0:
                ctype, enc = mimetypes.guess_type(q_path)
                status     = 200

    snac.debug(3, "serving html get %s %s" % (q_path, status))

    return status, body, ctype


def post_handler(snac, q_path, q_vars, acpt, p_data, headers):
    """ POST handler """

    status, body, ctype = 404, "<h1>404 Not Found</h1>", "text/html"

    logged_in = False

    # all things starting with /admin must be authenticated
    if q_path.startswith("/%s/admin" % snac.user["uid"]):
        logged_in = request_authorization(snac, headers)

        if logged_in is False:
            return 401, "401 Authorization Required", "text/plain"

    # convert the p_data from lists to scalars
    tmp_data = urllib.parse.parse_qs(p_data)
    p_data = {}
    for k, v in tmp_data.items():
        p_data[k] = v[0];

    if q_path == "/%s/admin/note" % snac.user["uid"]:
        snac.debug(1, "web command 'note' received")

        content     = p_data.get("content")
        in_reply_to = p_data.get("in_reply_to")

        if content is not None:
            msg = snac.activitypub.msg_create(
                snac, snac.activitypub.msg_note(snac, content, irt=in_reply_to))

            snac.data.add_to_timeline(snac, msg, msg["object"]["id"], in_reply_to)

            snac.activitypub.post(snac, msg)

        else:
            snac.debug(1, "not sending an empty or invalid note")

        status, body = 303, snac.actor("/admin")

    if q_path == "/%s/admin/action" % snac.user["uid"]:
        action = p_data.get("action")

        if action is None:
            snac.debug(1, "can't get action")
            return 400, "<h1>400 Bad Request</h1>", ctype

        id    = p_data.get("id")
        cid   = p_data.get("cid")
        actor = p_data.get("actor")

        snac.debug(1, "web action '%s' received" % action)

        status, body = 303, snac.actor("/admin")

        if action == snac.L("Like") or action == snac.L("Boost"):

            if id is None:
                snac.debug(1, "can't get id for '%s'" % action)
                return 400, "<h1>400 Bad Request</h1>", ctype

            like = False
            if action == snac.L("Like"):
                like = True

            msg = snac.activitypub.msg_admiration(snac, id, like)

            if msg is not None:
                snac.data.add_to_timeline(snac, msg, msg["id"], id)
                snac.activitypub.post(snac, msg)

        elif action == snac.L("Follow"):

            if actor is None:
                snac.debug(1, "can't get actor for '%s'" % action)
                return 400, "<h1>400 Bad Request</h1>", ctype

            # if it's not an actor url, try to resolve it
            if not actor.startswith("https://"):
                s_status, s_body = snac.webfinger.request(snac, actor)

                if s_status >= 200 and s_status <= 299:
                    r_actor = ""

                    for l in s_body["links"]:
                        if l.get("type") == "application/activity+json":
                            r_actor = l["href"]

                    if r_actor == "":
                        snac.debug(2, "webfinger resolv error following id %s" % actor)
                        actor = ""
                    else:
                        actor = r_actor
                else:
                    snac.debug(2, "webfinger connection error following id %s" % actor)
                    actor = ""

            if actor != "":
                # unmute first (we could have muted this guy
                # before and not remember it)
                snac.data.unmute(snac, actor)

                msg = snac.activitypub.msg_follow(snac, actor)

                # actor may have changed due to canonicalization
                actor = msg["object"]

                if msg is not None:
                    snac.data.add_to_following(snac, actor, msg)
                    snac.data.enqueue_output(snac, actor, msg)

        elif action == snac.L("Unfollow"):

            if actor is None:
                snac.debug(1, "can't get actor for '%s'" % action)
                return 400, "<h1>400 Bad Request</h1>", ctype

            s_status, object = snac.data.following(snac, actor)

            if s_status == 200:
                msg = snac.activitypub.msg_undo(snac, object["object"])
                snac.data.enqueue_output(snac, actor, msg)
                snac.data.delete_from_following(snac, actor)

            else:
                snac.debug(1, "%s is not being followed" % actor)

        elif action == snac.L("MUTE"):

            if actor is None:
                snac.debug(1, "can't get actor for '%s'" % action)
                return 400, "<h1>400 Bad Request</h1>", ctype

            snac.data.mute(snac, actor)

        elif action == snac.L("Delete"):

            for i in (id, cid):
                if i is None:
                    continue

                # if this message is ours, create a message and send it
                if i.startswith(snac.actor()):
                    if i.endswith("Like") or i.endswith("Announce"):
                        s_status, object = snac.data.get_from_timeline(snac, i)

                        if s_status == 200:
                            msg = snac.activitypub.msg_undo(snac, object)

                            # fix the destination to be everyone
                            msg["to"] = snac.activitypub.public_address

                            snac.activitypub.post(snac, msg)
                            snac.log("posted undo for %s" % i)

                        else:
                            snac.debug(1, "trying to undo something not in timeline %s" % i)

                    else:
                        msg = snac.activitypub.msg_delete(snac, i)
                        snac.activitypub.post(snac, msg)
                        snac.log("posted tombstone for %s" % i)

                snac.data.delete_from_timeline(snac, i)

        else:
            snac.log("invalid '%s' action" % action)
            status, body = 404, ""

    if q_path == "/%s/admin/user-setup" % snac.user["uid"]:

        snac.debug(1, "web command 'user-setup' received")

        # fill the fields
        for f in ("name", "avatar", "bio"):
            try:
                v = p_data[f]
            except:
                v = ""

            snac.user[f] = v

        try:
            pw1 = p_data["passwd1"]
            pw2 = p_data["passwd2"]

        except:
            pw1, pw2 = "", ""

        if pw1 != "":
            if pw1 == pw2:
                snac.user["passwd"] = snac.data.hash_password(snac.user["uid"], pw1)
                snac.debug(1, "changed password")
            else:
                snac.debug(1, "passwords don't match")

        # save the data
        snac.data.save_cfgfile("%s/user.json" % snac.basedir, snac.user)

        # delete the timeline cache
        snac.data.history_delete(snac, "_timeline.html")

        # send an update
        msg = snac.activitypub.msg_update(snac, snac.activitypub.msg_actor(snac))
        snac.activitypub.post(snac, msg)

        status, body = 303, snac.actor("/admin")

    return status, body, ctype

susie = """
data:image/png;base64, iVBORw0KGgoAAAANSUhEUgAAABAAAAAQAQAAAA
A3iMLMAAAAO0lEQVQI1wEwAM//AAZgAAcwAA/4AAPkAB3cAAPgAKXIAKfIAH/
8AD/8ADw8AB56AA/2AEPtAMwfAO+/UlQP2C3B0yEAAAAASUVORK5CYII=
"""
