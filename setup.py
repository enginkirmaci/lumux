"""Setup configuration for Lumux."""

from setuptools import setup, find_packages
from pathlib import Path


setup(
    name="lumux",
    version="0.2.0",
    description="Lumux for Philips Hue Sync (Wayland)",
    author="Engin KIRMACI",
    license="MIT",
    packages=find_packages(),
    py_modules=['main'],
    install_requires=[
        'python-hue-v2>=0.1.0',
        'numpy>=1.24.0',
        'Pillow>=10.0.0',
    ],
    entry_points={
        'console_scripts': [
            'lumux=main:main',
        ],
    },
    data_files=[
        ('share/lumux/data', ['data/default_settings.json']),
        ('share/applications', ['data/io.github.enginkirmaci.lumux.desktop']),
        ('share/metainfo', ['data/io.github.enginkirmaci.lumux.metainfo.xml']),
        ('share/icons/hicolor/scalable/apps', ['io.github.enginkirmaci.lumux.svg']),
    ],
    python_requires='>=3.10',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Multimedia :: Graphics',
        'Topic :: Desktop Environment',
    ],
)
