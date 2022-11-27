# snac - ActivityPub thing by grunfink

import re
import json
import SNAC

def request(snac, id):
    """ Queries webfinger about this id """

    status   = 404
    body     = None
    query    = ""
    resource = ""

    if re.search("^@?[^@]+@[^@]+$", id):
        # @user@host
        query    = "https://" + re.sub("^@?[^@]+@", "", id)
        resource = "acct:" + re.sub("^@", "", id)

    elif re.search("^https?://", id):
        # url
        x        = re.search("^https?://[^/]+", id)
        query    = x.group(0)
        resource = id

    if query:
        # is this query for this same host?
        if query == "https://%s" % snac.server["host"]:
            snac.debug(2, "shortcut webfinger request for %s in this host" % resource)

            status, body, ctype = get_handler(snac._server, "/.well-known/webfinger", {
                "resource": [resource] }, "")

        else:
            url = query + "/.well-known/webfinger?resource=" + resource

            # do the query
            status, body = snac.http.request(snac, "GET", url, headers={
                "Accept": "application/json"}
            )

    if body is not None:
        try:
            body = json.loads(body)

        except:
            snac.debug(2, "error parsing JSON in webfinger")
            status, body = 500, None

    return status, body


def get_handler(snacsrv, q_path, q_vars, acpt):
    """ HTTP GET handler """

    status, body = 0, None

    if q_path == "/.well-known/webfinger":
        try:
            # resource can be acct:user@hostname or the actor url
            resource = q_vars["resource"][0]

        except:
            resource = ""

        if resource != "":
            snac = None

            # starts with https? it's an actor, find it
            if resource.startswith("https://"):
                for u in snacsrv.users():
                    if u.actor() == resource:
                        # found
                        snac = u
                        break

            elif resource.startswith("acct:"):
                resource = resource.replace("acct:", "")

                if resource[0] == "@":
                    resource = resource[1:]

                try:
                    q_user, q_host = resource.split("@", 1)
                except:
                    q_user, q_host = "", ""

                if q_host == snacsrv.config["host"]:
                    # get this user
                    u = SNAC.snac(snacsrv, q_user)

                    if u.ok:
                        snac = u

            if snac is not None:
                body = {
                    "subject": "acct:%s@%s" % (snac.user["uid"], snac.server["host"]),
                    "links": [
                        {
                            "rel":  "self",
                            "type": "application/activity+json",
                            "href": snac.actor()
                        }
                    ]
                }

                body = json.dumps(body)
                status = 200

            else:
                status = 404

        else:
            # arguments are not valid
            status, body = 400, "<h1>400 Bad Request</h1>"

        snacsrv.log("webfinger for %s %s" % (resource, status))

    return status, body, "application/json"
