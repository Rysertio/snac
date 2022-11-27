PREFIX=/usr/local

all:
	@echo "Run 'make install' to install."

install:
	(umask 0022 && python3 ./setup.py install)
	mkdir -p -m 755 $(PREFIX)/man/man1
	install -m 644 doc/snac.1 $(PREFIX)/man/man1/snac.1
	mkdir -p -m 755 $(PREFIX)/man/man5
	install -m 644 doc/snac.5 $(PREFIX)/man/man5/snac.5
	mkdir -p -m 755 $(PREFIX)/man/man8
	install -m 644 doc/snac.8 $(PREFIX)/man/man8/snac.8
	rm -rf snac.egg-info build dist

uninstall:
	pip3 uninstall snac
	rm -f $(PREFIX)/bin/snac
