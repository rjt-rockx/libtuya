libtuya Documentation
====================

A unified Python library for Tuya device control that combines QR code authentication, intelligent device control, and fast local control.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   quickstart
   architecture
   api/modules

Features
--------

* **QR Code Authentication**: Seamless authentication using Smart Life app
* **Automatic Device Discovery**: Find devices with local keys automatically  
* **Intelligent Device Control**: Proper scaling and capability mapping
* **Multiple Interfaces**: Python API, CLI, and REST API support
* **No Manual Configuration**: Just works out of the box

Quick Start
-----------

.. code-block:: bash

   pip install -e .
   tuya login
   tuya devices
   tuya control "Living Room Light" on

API Documentation
-----------------

.. toctree::
   :maxdepth: 2
   :caption: API Reference:

   api/libtuya
   api/libtuya.auth
   api/libtuya.devices
   api/libtuya.intelligence
   api/libtuya.dps
   api/libtuya.cli_core

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`