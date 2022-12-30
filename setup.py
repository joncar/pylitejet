from setuptools import setup

setup(
    name="pylitejet",
    packages=["pylitejet"],
    version="0.4.5",
    description="A library for controlling a LiteJet lighting system.",
    long_description="A library for controlling a LiteJet lighting system.",
    author="Jon Caruana",
    author_email="jon@joncaruana.com",
    url="https://github.com/joncar/pylitejet",
    download_url="https://github.com/joncar/pylitejet/tarball/0.4.5",
    keywords=["litejet"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.9",
    ],
    license="MIT",
    install_requires=["pyserial", "pyserial-asyncio"],
)
