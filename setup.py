from setuptools import setup

setup(
    name='virtualtime',
    version='1.0',
    packages=['virtualtime'],
    license='Apache License, Version 2.0',
    description='Implements a system for simulating a virtual time.',
    long_description=open('README.md').read(),
    url='http://www.sjoft.com/',
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
    install_requires = ['python-datetime-tz'],
    extras_require = {
        'tests':  ["nose", 'decorator'],
        }
)