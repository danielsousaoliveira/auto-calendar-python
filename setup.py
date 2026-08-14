from setuptools import setup, find_packages

setup(
    name='cal-auto-python',
    version='0.0.1',
    packages=find_packages(where='src'), 
    package_dir={'': 'src'}, 
    python_requires='>=3.9,<3.14',
    classifiers=[
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
    ],
    install_requires=[
        'google-api-python-client',
        'google-auth-httplib2',
        'google-auth-oauthlib'
    ],
    entry_points={
        'console_scripts': [
            'cal-auto-python=src.main:main',
        ],
    },
)
