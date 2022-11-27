# snac

A simple, minimalistic ActivityPub instance

# Features

- lightweight, minimal dependencies
- large support of ActivityPub operations, e.g. write public notes, follow users, be followed, reply to the notes of others, admire wonderful content (like or boost), write private messages...
- Easily-accessed mute button to silence morons
- Tested interoperability with similar software
- No database needed
- Not much bullshit

# About

**NOTE:** This release (1.x) is no longer maintained. Please use the 2.x branch, that it's probably available from the same place you got this one but named like `snac2` or similar.

This program runs as a daemon (proxied by a TLS-enabled real httpd server) and provides the basic services for a Fediverse / ActivityPub instance (sharing messages and stuff from/to other systems like Mastodon, Pleroma, Friendica, etc.).

This is not the manual; man pages `snac(1)` (user manual), `snac(5)` (formats) and `snac(8)` (administrator manual) are what you are looking for.

`snac` stands for Social Networks Are Crap.

# Installation

This application is written in Python 3 and needs the following external packages:

* OpenSSL
* urllib3

On Debian/Ubuntu, you can satisfy these requirements by running

```
    apt install python3-openssl python3-urllib3
```

And for OpenBSD

```
    pkg_add py3-openssl py3-urllib3
```

Then run `make install` as root.

See the administrator manual on how to proceed from here.

# License and author

See the LICENSE file for details.
