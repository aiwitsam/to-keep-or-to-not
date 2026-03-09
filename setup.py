"""Setup for To Keep or to Not."""

from setuptools import setup, find_packages

setup(
    name="tokeep",
    version="0.1.0",
    description="To Keep or to Not — Shakespeare-themed external drive backup tool",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "rich>=13.0.0",
        "pyyaml>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "tokeep=tokeep.__main__:main",
        ],
    },
)
