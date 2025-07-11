#!/usr/bin/env python3

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="libtuya",
    version="1.0.0",
    author="LibTuya Project",
    author_email="support@libtuya.dev",
    description="A 'just works' Tuya integration system combining authentication, device intelligence, and fast local control",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/libtuya/libtuya",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Home Automation",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "black>=22.0.0",
            "flake8>=5.0.0",
            "mypy>=1.0.0",
            "sphinx>=5.0.0",
            "sphinx-rtd-theme>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "tuya=libtuya.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "libtuya": [
            "intelligence/*.json",
            "intelligence/analysis/*.md",
            "analysis/*.md",
        ],
    },
    keywords="tuya, smart home, home automation, iot, devices, local control",
    project_urls={
        "Bug Reports": "https://github.com/libtuya/libtuya/issues",
        "Source": "https://github.com/libtuya/libtuya",
        "Documentation": "https://libtuya.readthedocs.io",
    },
)