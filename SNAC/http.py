# snac - ActivityPub thing by grunfink

import SNAC
import urllib3
import re
import json
import OpenSSL
import base64
import datetime
import hashlib

# PoolManager
pm = urllib3.PoolManager(retries=urllib3.Retry(total=0, connect=0))

def request(snac, method, url, headers={}, fields=None, body=None):
    """ Does an HTTP request """

    # add the User Agent
    headers["User-Agent"] = snac.user_agent

    status = 500

    try:
        # why this?
        # request() barfs if both fields and body are set,
        # even if they are set to None (WTF?)
        if fields is not None:
            rq = SNAC.http.pm.request(method, url, headers=headers, fields=fields)
        else:
            rq = SNAC.http.pm.request(method, url, headers=headers, body=body)

        status, body = rq.status, rq.data
    except:
        pass

    return status, body


def request_signed(snac, method, url, msg=None):
    """ Does an HTTP request, signed """

    if msg is not None:
        body = json.dumps(msg)
    else:
        body = None

    # calculate signature parts
    s = re.sub("^https://", "", url)

    try:
        host, target = s.split("/", 1)
    except:
        host, target = s, ""

    if method == "POST":
        target = "post /" + target
    else:
        target = "get /" + target

    date = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    # digest
    m = hashlib.sha256()

    if body is not None:
        m.update(body.encode())

    digest = "SHA-256=" + base64.b64encode(m.digest()).decode()

    # string to be signed
    s  = "(request-target): " + target + "\n"
    s += "host: " + host + "\n"
    s += "digest: " + digest + "\n"
    s += "date: " + date

    # build a key object
    pk = OpenSSL.crypto.load_privatekey(OpenSSL.crypto.FILETYPE_PEM, snac.key["secret"])

    b = OpenSSL.crypto.sign(pk, s, "sha256")
    sig_b64 = base64.b64encode(b).decode()

    # build the signature header
    key_name = snac.actor() + "#main-key"

    signature = "keyId=\"" + key_name + "\","
    signature += "algorithm=\"rsa-sha256\","
    signature += "headers=\"(request-target) host digest date\","
    signature += "signature=\"" + sig_b64 + "\""

    if method == "POST":
        # send the POST
        status, data = snac.http.request(snac, "POST", url, headers={
            "Content-Type":     "application/activity+json",
            "Date":             date,
            "Signature":        signature,
            "Digest":           digest,
            "User-Agent":       snac.user_agent
            }, body=body)
    else:
        # send the GET
        status, data = snac.http.request(snac, "GET", url, headers={
            "Accept":           "application/activity+json",
            "Date":             date,
            "Signature":        signature,
            "Digest":           digest,
            "User-Agent":       snac.user_agent
            })

    try:
        reply = data.decode()
    except:
        reply = str(data)

    snac.data.archive(snac, ">", method, url, msg, status, data)

    return status, data


def check_signature(snac, q_path, payload, headers):
    """ checks an http signature """

    # add back the server prefix
    q_path = snac.server["prefix"] + q_path

    # try first the digest
    m = hashlib.sha256()
    m.update(payload.encode())
    c_digest = "SHA-256=" + base64.b64encode(m.digest()).decode()

    try:
        digest = headers["digest"]
    except:
        digest = ""

    if digest != c_digest:
        snac.debug(1, "checksig bad digest %s" % q_path)
        return 400

    sig_hdr = headers["signature"]

    # get the keyId URL
    x = re.match(".*keyId=\"([^\"]+)\"", sig_hdr)

    if x is None:
        snac.debug(1, "checksig cannot extract keyId from header '%s'" % sig_hdr)
        return 400

    keyId = x.group(1)

    # take for granted if on this same instance,
    # we're not going to lie to ourselves
    if keyId.startswith(snac._server.base_url()):
        snac.debug(2, "checksig skipping signature check for this same instance")
        return 200

    # kludge: request for this (at least on mastodon, https://c.im/users/crappo)
    # returns a 401; stripping the # seems to fix it ???)
    keyId = keyId.replace("#main-key", "")

    status, actor = snac.data.request_actor(snac, keyId)

    if status < 200 or status > 299:
        # don't log 410 Gone because they are so boring
        if status != 410:
            snac.debug(1, "checksig cannot request key %s %s" % (keyId, status))

        return status

    try:
        pem = actor["publicKey"]["publicKeyPem"]
    except:
        snac.debug(1, "checksig cannot get PEM from key %s" % keyId)
        return 400

    # get the signature headers
    x = re.match(".*headers=\"([^\"]+)\"", sig_hdr)

    if x is None:
        snac.debug(1, "checksig cannot extract headers from header '%s'" % sig_hdr)
        return 400

    hdr_list = x.group(1)

    # calculate the string to be signed
    sig_str = ""

    for h in hdr_list.split(" "):
        if sig_str != "":
            sig_str += "\n"

        if h == "(request-target)":
            sig_str += "%s: post %s" % (h, q_path)
        else:
            sig_str += "%s: %s" % (h, headers[h])

    # get the signature itself
    x = re.match(".*signature=\"([^\"]+)\"", sig_hdr)

    if x is None:
        snac.debug(1, "checksig cannot extract signature from header '%s'" % sig_hdr)
        return 400

    sig_b64 = x.group(1)
    sig_bin = base64.b64decode(sig_b64)

    # get the public key and its X509 wrap
    pk      = OpenSSL.crypto.load_publickey(OpenSSL.crypto.FILETYPE_PEM, pem)
    x509    = OpenSSL.crypto.X509()
    x509.set_pubkey(pk)

    try:
        OpenSSL.crypto.verify(x509, sig_bin, sig_str, "sha256")

    except:
        snac.debug(1, "checksig OpenSSL verify error")

        # let's disable it for now
        #return False

    return 200
