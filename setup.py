from setuptools import setup

setup(
    name='virtualtime',
    version='1.2',
    packages=['virtualtime', 'virtualtime.datetime_tz'],
    license='Apache License, Version 2.0',
    description='Implements a system for simulating a virtual time.',
    long_description=open('README.md').read(),
    url='http://www.sjsoft.com/',
    author='St James Software',
    author_email='support@sjsoft.com',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: Apache Software License',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 2 :: Only',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Software Development :: Testing',
    ],
    install_requires = ['python-datetime-tz == 0.2-j5p1'],
    extras_require = {
        'tests':  ["nose", 'decorator'],
        },
    dependency_links = ["https://github.com/st-james-software/python-datetime-tz/archive/v0.2-j5p1.zip#egg=python-datetime-tz-0.2-j5p1"]
)