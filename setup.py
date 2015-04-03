#!/usr/bin/env python

from setuptools import setup

with open('requirements.txt', 'r') as f:
    reqs = f.read()

setup(
    name="tagg",
    version="0.1.2",
    description="CLI tool for tag-github project",
    author="porter.io",
    author_email="opensource@porter.io",
    url="https://github.com/porter-io/tagg-python",
    install_requires=reqs,
    packages=["tagg"],
    entry_points={
        'console_scripts': [
            "tagg = tagg.cli:main",
            "autotagg = tagg.autotag:main",
        ]
    },
    package_data={
        '': ['*.json']
    }
)
