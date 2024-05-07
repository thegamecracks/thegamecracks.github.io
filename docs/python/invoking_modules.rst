Using ``python -m`` to invoke modules as scripts
================================================

.. toctree::

You might have seen the ``-m`` flag used in various python commands online,
or was told by someone else to use ``python -m`` to "run a module as a script",
but didn't really understand what that meant. This gist covers how that flag
is used, particularly in the context of package development.

Introduction to modules and packages
------------------------------------

Say you wanted to write a command-line utility for downloading a GitHub
repository release, and you started out with a single script, ``downloader.py``.
Eventually your code started growing too big to be well-organized in a single file,
so you decide to split its functionality into separate `modules`_:

.. code-block:: python
   :force:

    api.py    # interacts with GitHub's API using the requests library
    cache.py  # stores release information to avoid unnecessary requests
    cli.py    # provides an argparse interface for the user
    main.py   # the entry script that your users should run
        from api import download
        from cli import parser

        args = parser.parse_args()
        download(args.repository, args.filename)

.. _modules: https://docs.python.org/3/tutorial/modules.html

If you wanted to share this with other users or re-use it in another project,
they would need to download all four scripts inside whatever working directory
they might be in, as well as any dependencies required by your script:

.. code-block:: python
   :force:

    my_project/
    └── api.py, cache.py, cli.py, main.py
        # /my_project $ pip install requests
        # /my_project $ python main.py ...

This is a fairly inconvenient process to do. A nicer way to handle this
would be packaging and uploading the code onto `PyPI`_ so that users can
install it with a single command:

.. code-block:: shell

    pip install my-github-downloader
    python -m my_downloader

.. _PyPI: https://pypi.org/

If you want to do the same thing, the first step you should do is organize
your code into a `package`_, where you've collected your scripts into
a single directory:

.. code-block:: python
   :force:

    my_project/
    └── my_downloader/
        ├── __init__.py
        ├── api.py, cache.py, cli.py
        └── main.py
                # In packages you can use relative imports:
                from .api import download
                # Though absolute imports are also valid:
                from my_downloader.cli import parser

.. _package: https://docs.python.org/3/tutorial/modules.html#packages

This way, all of your tool's scripts are contained in one directory
and is easier to distribute to other systems. It also reduces the risk
of files being overwritten when installed by pip, since packages get
placed in a shared ``site-packages/`` directory with other package files.

How does -m play into this?
---------------------------

Now that your code is organized as a package, how do you run main.py?
You could try to do ``python my_downloader/main.py``, but this makes
Python run ``main.py`` as a standalone script, without knowledge of
the package layout it resides in. As such, you lose features of packages
like ``__init__.py`` and relative imports:

.. code-block:: python
   :force:

    /my_project $ python my_downloader/main.py
    Traceback (most recent call last):
    File "/my_project/my_downloader/main.py", line 2, in <module>
        from .api import download
    ImportError: attempted relative import with no known parent package

To run a module inside a package, you should use ``-m`` option like so:

.. code-block:: shell

    /my_project $ python -m my_downloader.main

This essentially imports the module described by the path ``my_downloader.main``,
and sets its ``__name__`` constant to ``"__main__"``. The ``-m`` option also
adds your current working directory to `sys.path`_, a list of directories
that Python will search when attempting to resolve ``my_downloader``.
As a result, the ``my_downloader`` package goes through the entire import system,
executing ``__init__.py`` and setting up the context for ``.`` relative imports,
allowing ``main.py`` to run as intended.

.. _sys.path: https://docs.python.org/3/library/sys.html#sys.path

Using ``__main__.py``
---------------------

Packages support another special script, |dunder_main|_.
When this is present in a package, the ``-m`` option will implicitly
run that script when its given the name of a package instead of a ``.py`` module.
We can take advantage of this to make ``my_downloader`` invokable
by renaming ``main.py`` to ``__main__.py``:

.. code-block:: python
   :force:

    my_project/
    └── my_downloader/
        ├── __init__.py
        ├── __main__.py  # contents of main.py
        └── ...

.. code-block:: shell

    /my_project $ python -m my_downloader
    # Equivalent to typing the full module path:
    /my_project $ python -m my_downloader.__main__

.. |dunder_main| replace:: ``__main__.py``
.. _dunder_main: https://docs.python.org/3/library/__main__.html#main-py-in-python-packages


Adding ``my_downloader`` to sys.path
------------------------------------

Remember, ``python -m my_downloader`` worked in the previous examples because
the current directory was ``/my_project`` and ``-m`` added it to ``sys.path``.
If you were to change to another directory, the ``my_downloader`` would no
longer be resolvable. This is one of the reasons why we have pip - it lets us
install packages to a common place, ``site-packages/``, that Python always
knows to search for modules [#site]_ regardless of our current working directory.
However we're not there yet, as pip can't just install any plain old package.
It needs to be packaged into a distribution first. For this, I recommend looking
into `setuptools + pyproject.toml`_ for writing your build configuration.
Here's the bare minimum you need to make a distribution package:

.. code-block:: python
   :force:

    my_project/
    ├── my_downloader/
    │   ├── __init__.py
    │   └── ...
    └── pyproject.toml

.. code-block:: toml
   :caption: pyproject.toml

    [build-system]
    requires = ["setuptools"]
    build-backend = "setuptools.build_meta"

    [project]
    name = "my-github-downloader"
    version = "0.1.0"

.. _setuptools + pyproject.toml: https://setuptools.pypa.io/en/latest/userguide/quickstart.html#basic-use

This takes advantage of setuptools's automatic discovery to include the
``my_downloader/`` package in the distribution. There are several other keys
that can be written in the |project-table|_ table, but those two are the
only required ones.
To build the |sdist|_ and |wheel|_ distribution files:

.. code-block:: shell

    /my_project $ pip install build
    /my_project $ python -m build  # Hey, it's -m again!

.. |project-table| replace:: ``[project]``
.. _project-table: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
.. |sdist| replace:: ``.tar.gz``
.. _sdist: https://packaging.python.org/en/latest/discussions/package-formats/
.. |wheel| replace:: ``.whl``
.. _wheel: https://packaging.python.org/en/latest/discussions/package-formats/

And to install your package:

.. code-block:: shell

    /my_project $ pip install dist/my-github-downloader-0.1.0-py3-none-any.whl
    # Or, installing directly from pyproject.toml:
    /my_project $ pip install .

.. seealso:: Using editable installs: https://setuptools.pypa.io/en/latest/userguide/development_mode.html

Sidenote: why is -m recommended on Windows?
-------------------------------------------

Searching online, you'll find a dozen ways to invoke Python on the command-line
(``python``, ``python3``, ``python3.11``, ``py``, etc.). Beginners to this
(especially to the command-line) may not understand how these commands are
provided by the `PATH`_ environment variable. If they take the shortest path
through the `official installer`_, their system's PATH will not be updated
to include ``python`` or any package entrypoints like |pip|_.
However, the installer does include the `Python Launcher for Windows`_
by default, providing the ``py`` command to invoke python. With ``py`` alone,
you can access pip or other installed modules by running their modules directly,
e.g. ``py -m pip install ...``. If you already understand how your Python
installation is set up, you won't need to use ``py -m``, but for novices,
this is typically more fool-proof than asking them to re-install with
the "Add Python to PATH" option and potentially confusing them if they
have multiple Python versions.

.. _PATH: https://www.maketecheasier.com/what-is-the-windows-path/
.. _official installer: https://www.python.org/downloads/
.. |pip| replace:: ``pip``
.. _pip: https://docs.python.org/3/tutorial/venv.html#managing-packages-with-pip
.. _Python Launcher for Windows: https://docs.python.org/3/using/windows.html#python-launcher-for-windows

.. rubric:: Footnotes

.. [#site]
   Assuming Python isn't told to skip loading the |site-module|_ module on startup.
   This can be turned off by using the |dash-S|_ flag, preventing ``site-packages/``
   from being searched.
.. |site-module| replace:: ``site``
.. _site-module: https://docs.python.org/3/library/site.html
.. |dash-S| replace:: ``-S``
.. _dash-S: https://docs.python.org/3/using/cmdline.html#cmdoption-S
