from setuptools import setup
import os
import SNAC

with open("README.md", "r") as r:
    long_desc = r.read()

setup(
    name="snac",
    version=SNAC.__version__,
    description="A simple, minimalistic ActivityPub instance",
    long_description=long_desc,
    author="grunfink",
    author_email="nobody@localhost",
    packages=["SNAC"],
    url="https://example.com",
    license="Public Domain",
    install_requires=['urllib3',
                      'pyOpenSSL',                     
                      ],
    entry_points={
        "console_scripts": [
            "snac = SNAC.__main__:main"
        ]
    }
)
