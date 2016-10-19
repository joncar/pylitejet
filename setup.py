from setuptools import setup
setup(
  name = 'pylitejet',
  packages = ['pylitejet'],
  version = '0.1.0',
  description = 'A library for controlling a LiteJet lighting system.',
  author = 'Jon Caruana',
  author_email = 'jon@joncaruana.com',
  url = 'https://github.com/joncar/pylitejet',
  download_url = 'https://github.com/joncar/pylitejet/tarball/0.1.0',
  keywords = ['litejet'],
  classifiers = [
    'Development Status :: 3 - Alpha',
    'License :: OSI Approved :: MIT License',
    'Programming Language :: Python :: 3.4',
  ],
  license = 'MIT',
  install_requires = ['pyserial']
  )
