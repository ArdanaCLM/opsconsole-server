..
 (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
 (c) Copyright 2017 SUSE LLC

========
Overview
========

Basic Architecture
------------------
The Business Logic Layer (BLL) is the server component of the operations console.
It consists of a single component which handles all incoming requests and 
executes each in a thread.  It runs under the pecan_ WSGI framework.  In 
production, the web layer is hosted under Apache, but it can also run standalone 
for development and testing.

.. _pecan: http://pypi.python.org/pypi/pecan

Configuration Files
-------------------

The configuration for the BLL is contained in a Python-formatted text file.
There have been many copies of this file floating around inside and outside of
the source tree, used for the variety of ways that the BLL can be launched.

Now there is just a single copy file in this source distribution,
``tests/config.py``, that is used for the BLL testing.  The production version
of this file is maintained in a separate repo.

In modern versions of pecan (0.8.3. and above), the config file is required to
be a python file whose name ends with ``.py``, and will fail at startup if it is
anything else, including ``.conf``.

Launch environments
...................
There are a number of ways the code can be run:

- Unit/functional tests

  Launched via run_tests.sh or via an IDE.  The Jenkins build also launches
  functional tests via run_tests.sh.  Note: since Python tests do not have a
  "main" program, there is no way to pass command line parameters, and thus the
  only way to change which config file used is via the BLL_CONF_OVERRIDE
  environment variable.

- ``run_tests.sh --runserver``

  Launches the pecan web server directly, using the config file name as a
  command line argument.

- apache / wsgi

  In production, the web layer runs in a pecan container under apache, via WSGI.
  The file that is launched is ``app.wsgi``, and it in turn deploys pecan
  and specifies the config file to be used.  Note: ``app.wsgi`` is generated
  by ansible from a template.

Config file properties
......................
The config file, ``tests/config.py``, used for the BLL development and testing
is intended to be flexible enough for the variety of situations in which it is
used and normally requires no local changes.  These properties include:

- console logging

  All logging is done to the console, which is the most useful place for
  dev/test.  By not logging to the file system, it also avoids the issue of
  finding a system-independent, launch-independent, writable location to place the
  file(s).  Of course, standard shell redirection and/or tee-ing can be used to
  save the output into a file.

- environment variables

  Most values that are dependent upon the environment and are likely to change
  are first looked up in the environment, and use a reasonable default if not
  set.

In the event that some value in this file needs to be customized for a
particular environment, the first (and preferred) option is to add another
configuration variable within the file and use a reasonable default for it.  If
that is not possible, then the next best choice is to copy the file somewhere
else (usually outside of the source tree), make the local modifications, and
then specify that the bll use this file for configuration.  There are a couple ways
to specify this, as demonstrated in the next section.


Resolution order
................

The BLL figures out which config file to use based on a resolution order that is,
as much as possible and reasonable, common to all ways of launching it, with
exceptions noted below.  The BLL will use the *first* file it can find, and will
stop searching for others; therefore do *not* expect to be able to set some
values in one config file and other values in another and expect it to read
them both and merge them together at run-time.

The order as follows:

#. Filename passed in as a command-line arguments

   This is supported in those launchers that accept command line arguments:
   the test script and ``run_tests.sh``

#. Filename specified in BLL_CONF_OVERRIDE environment variable

   Specifies the config file to use.  Supported everywhere.

#. File from source distribution

   When running in a dev/test environment, i.e. via ``run_tests.sh`` or via the
   unit/functional test framework, the file ``tests/config.py`` will be used.
   Note: this file is not present on a production system, and the launchers used
   in production (via apache) will not look for this file.

#. ``/etc/opsconsole-server/config.py`` (production only)

   When launched in production (via apache) this file is used if present.

#. ``/etc/opsconsole-server/opsconsole-server.conf`` (production only -- deprecated)

   When launched in production (via apache) this file is used as a last resort.
   Since its name prevents migrating to a modern version of pecan, it is
   expected that this will be removed in an upcoming release.

Localization
------------

Message files
.............

Message files are created and managed in several steps.  The first is to
extract strings from all python code that calls the ``_()`` or ``gettext()``
functions.  These strings are placed into the Portable Object Template
(``.pot``) file.  To create or update this ``.pot`` file::

   ./setup.py extract_messages -o bll/locale/messages.pot

Tweak the copyright that is inserted into the generated
file, ``bll/locale/messages.pot`` to match the corporate standard. This
extraction step needs to be done whenever localizable strings in python code
are added or modified.

Portable Object (``.po``) files are created for each locale from the ``.pot``
file.  These ``.po`` files contain translations for each of the strings.  These
files are sent off to the translators for translation, and the
translated files should be checked back into the git repository.

Whenever the ``.pot`` template file is changed, the ``.po`` files can be updated
with::

   ./setup.py update_catalog -d bll/locale -i bll/locale/messages.pot

The final step is to create Machine Object (``.mo``) files from the
``.po`` files, which are used at runtime.  These files are automatically
generated by the continuous integrated build process via ``setup.py bdist``.
If you want to create these ``.mo`` files manually for development and
testing, use::

   ./setup.py compile_catalog -d bll/locale -f

For more information about these working with message catalogs and
the ``setup`` commands, see the babel_ page.

.. _babel: http://babel.pocoo.org/en/latest/messages.html

Python usage
............

To use strings in plugin code::

   raise BllException(self._("Error message"))

To use strings with a single placeholder::

   raise BllException(self._("Error with id {}").format(id))

To use with multiple placeholders::

   raise BllException(self._("Error with id {1} doing operation {2}").format(
      id, operation))

