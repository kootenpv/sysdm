from setuptools import find_packages
from setuptools import setup

MAJOR_VERSION = "0"
MINOR_VERSION = "8"
MICRO_VERSION = "44"
VERSION = "{}.{}.{}".format(MAJOR_VERSION, MINOR_VERSION, MICRO_VERSION)

with open("README.md") as f:
    LONG_DESCRIPTION = f.read()

setup(
    name='sysdm',
    version=VERSION,
    description="Scripts as a service. Builds on systemctl.",
    url='https://github.com/kootenpv/sysdm',
    author='Pascal van Kooten',
    author_email='kootenpv@gmail.com',
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    entry_points={'console_scripts': ['sysdm = sysdm.__main__:main']},
    license='MIT',
    install_requires=["inotify", "blessed", "pick", "yagmail"],
    packages=find_packages(),
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Customer Service',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: Unix',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Software Development',
        'Topic :: Software Development :: Build Tools',
        'Topic :: Software Development :: Debuggers',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Software Distribution',
        'Topic :: System :: Systems Administration',
        'Topic :: Utilities',
    ],
    zip_safe=False,
    platforms='posix',
)
