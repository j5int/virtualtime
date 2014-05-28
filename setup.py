from setuptools import setup

setup(
    name='j5.VirtualTime',
    version='1.0',
    packages=['j5', 'j5.Test'],
    license='Apache Software License',
    description='Implements a system for simulating a virtual time.',
    long_description=open('README.md').read(),
    url='http://www.j5int.com/',
    author='j5 Software',
    author_email='support@sjsoft.com',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: Apache Software License',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2 :: Only',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    extras_require = {
        'tests':  ["nose", 'j5.datetime_tz', 'j5.Test'],
        }
)