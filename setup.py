#!/usr/bin/env python3

# python setup.py sdist --format=zip,gztar

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.install import install
from distutils import core
import os
import sys
import platform
import imp
import argparse

with open('contrib/requirements/requirements.txt') as f:
    requirements = f.read().splitlines()

with open('contrib/requirements/requirements-hw.txt') as f:
    requirements_hw = f.read().splitlines()

version = imp.load_source('version', 'lib/version.py')

if sys.version_info[:3] < (3, 4, 0):
    sys.exit("Error: Electrum requires Python version >= 3.4.0...")

data_files = []

if platform.system() in ['Linux', 'FreeBSD', 'DragonFly']:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root=', dest='root_path', metavar='dir', default='/')
    opts, _ = parser.parse_known_args(sys.argv[1:])
    usr_share = os.path.join(sys.prefix, "share")
    icons_dirname = 'pixmaps'
    if not os.access(opts.root_path + usr_share, os.W_OK) and \
       not os.access(opts.root_path, os.W_OK):
        icons_dirname = 'icons'
        if 'XDG_DATA_HOME' in os.environ.keys():
            usr_share = os.environ['XDG_DATA_HOME']
        else:
            usr_share = os.path.expanduser('~/.local/share')
    data_files += [
        (os.path.join(usr_share, 'applications/'), ['electrum-ftc.desktop']),
        (os.path.join(usr_share, icons_dirname), ['icons/electrum_light.png'])
    ]

extras_require = {
    'hardware': requirements_hw,
    'fast': ['pycryptodomex'],
    ':python_version < "3.5"': ['typing>=3.0.0'],
}
extras_require['full'] = extras_require['hardware'] + extras_require['fast']

class BuildPyCommand(build_py):
    def run(self):
        build_py.run(self)
        try:
            from PyQt5 import pyrcc_main
            if not pyrcc_main.processResourceFile(['icons.qrc'],
                                                  'build/lib/electrum_ftc_gui/qt/icons_rc.py',
                                                  False):
                raise RuntimeError('Failed to generate icons_rc.py')
        except ImportError:
            import subprocess
            subprocess.run(['pyrcc5', 'icons.qrc', '-o', 'build/lib/electrum_ftc_gui/qt/icons_rc.py'])
        with open('build/lib/electrum_ftc/version.py', 'r+') as fp:
            verfile = fp.readlines()
            verfile[0] = "ELECTRUM_FTC_VERSION = '{}'\n".format(
                version.ELECTRUM_FTC_VERSION)
            fp.seek(0)
            fp.writelines(verfile)
            fp.truncate()

class InstallCommand(install):
    def run(self):
        setup = core.run_setup('neoscrypt_module/setup.py', stop_after='commandline')
        if platform.system() == 'Windows':
            setup.command_options['build_ext'] = {'compiler': ('build_ext', 'mingw32')}
        setup.run_command('install')
        install.run(self)

setup(
    name="Electrum-FTC",
    version=version.ELECTRUM_FTC_VERSION,
    cmdclass={'build_py': BuildPyCommand, 'install': InstallCommand},
    install_requires=requirements,
    extras_require=extras_require,
    packages=[
        'electrum_ftc',
        'electrum_ftc_gui',
        'electrum_ftc_gui.qt',
        'electrum_ftc_plugins',
        'electrum_ftc_plugins.audio_modem',
        'electrum_ftc_plugins.cosigner_pool',
        'electrum_ftc_plugins.email_requests',
        'electrum_ftc_plugins.hw_wallet',
        'electrum_ftc_plugins.keepkey',
        'electrum_ftc_plugins.labels',
        'electrum_ftc_plugins.ledger',
        'electrum_ftc_plugins.revealer',
        'electrum_ftc_plugins.trezor',
        'electrum_ftc_plugins.digitalbitbox',
        'electrum_ftc_plugins.virtualkeyboard',
    ],
    package_dir={
        'electrum_ftc': 'lib',
        'electrum_ftc_gui': 'gui',
        'electrum_ftc_plugins': 'plugins',
    },
    package_data={
        '': ['*.txt', '*.json', '*.ttf', '*.otf'],
        'electrum_ftc': [
            'wordlist/*.txt',
            'locale/*/LC_MESSAGES/electrum.mo',
        ],
    },
    scripts=['electrum-ftc'],
    data_files=data_files,
    description="Lightweight Feathercoin Wallet",
    author="Thomas Voegtlin; Feathercoin Development Foundation",
    author_email="thomasv@electrum.org; info@feathercoin.foundation",
    license="MIT Licence",
    url="https://electrum.org",
    long_description="""Lightweight Feathercoin Wallet"""
)
