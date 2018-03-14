#!/usr/bin/env python3

# python setup.py sdist --format=zip,gztar

import os
import sys
import platform
import imp
import argparse
import subprocess

from distutils import core
from setuptools import setup, find_packages
from setuptools.command.install import install
from setuptools.command.build_py import build_py

with open('contrib/requirements/requirements.txt') as f:
    requirements = f.read().splitlines()

with open('contrib/requirements/requirements-hw.txt') as f:
    requirements_hw = f.read().splitlines()

version = imp.load_source('version', 'electrum/version.py')

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
    'gui': ['pyqt5'],
}
extras_require['full'] = [pkg for sublist in list(extras_require.values()) for pkg in sublist]


class CustomInstallCommand(install):
    def run(self):
        setup = core.run_setup('neoscrypt_module/setup.py', stop_after='commandline')
        if platform.system() == 'Windows':
            setup.command_options['build_ext'] = {'compiler': ('build_ext', 'mingw32')}
        setup.run_command('install')
        install.run(self)
        # potentially build Qt icons file
        try:
            import PyQt5
        except ImportError:
            pass
        else:
            try:
                path = os.path.join(self.install_lib, "electrum/gui/qt/icons_rc.py")
                if not os.path.exists(path):
                    subprocess.call(["pyrcc5", "icons.qrc", "-o", path])
            except Exception as e:
                print('Warning: building icons file failed with {}'.format(e))

class BuildPyCommand(build_py):
    def run(self):
        build_py.run(self)
        with open('build/lib/electrum_ftc/version.py', 'r+') as fp:
            verfile = fp.readlines()
            verfile[0] = "ELECTRUM_FTC_VERSION = '{}'\n".format(
                version.ELECTRUM_FTC_VERSION)
            fp.seek(0)
            fp.writelines(verfile)
            fp.truncate()

setup(
    name="Electrum-FTC",
    version=version.ELECTRUM_FTC_VERSION,
    install_requires=requirements,
    extras_require=extras_require,
    packages=[
        'electrum_ftc',
        'electrum_ftc.gui',
        'electrum_ftc.gui.qt',
        'electrum_ftc.plugins',
    ] + [('electrum_ftc.plugins.'+pkg) for pkg in find_packages('electrum/plugins')],
    package_dir={
        'electrum_ftc': 'electrum'
    },
    package_data={
        '': ['*.txt', '*.json', '*.ttf', '*.otf'],
        'electrum_ftc': [
            'wordlist/*.txt',
            'locale/*/LC_MESSAGES/electrum.mo',
        ],
    },
    scripts=['electrum/electrum-ftc'],
    data_files=data_files,
    description="Lightweight Feathercoin Wallet",
    author="Thomas Voegtlin; Feathercoin Development Foundation",
    author_email="thomasv@electrum.org; info@feathercoin.foundation",
    license="MIT Licence",
    url="https://electrum.org",
    long_description="""Lightweight Feathercoin Wallet""",
    cmdclass={
        'build_py': BuildPyCommand,
        'install': CustomInstallCommand,
    },
)
