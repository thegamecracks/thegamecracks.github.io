Using ``python -m`` to invoke modules as scripts
================================================

.. toctree::

.. admonition:: Before you read...

   This guide requires some pre-requisite knowledge of using Python.
   If you can answer the following questions with at least some level
   of confidence, you can continue ahead:

   - What is a terminal? What can you use it for?
   - What is a current working directory?
   - How do you run Python scripts (``.py`` files) from the terminal?
   - How do you make a Python script import another script?
   - How do you install third-party packages with pip? How do you use them?

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
and is easier to distribute to other systems.

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

To run a module inside a package, you should use the ``-m`` option like so:

.. code-block:: shell

    /my_project $ python -m my_downloader.main

This essentially imports the module described by the path ``my_downloader.main``,
and sets its ``__name__`` constant to ``"__main__"``. As a result, the
``my_downloader`` package goes through the entire import system, executing
``__init__.py`` and setting up the context for ``.`` relative imports,
allowing ``main.py`` to run as intended.

...don't understand how importing works here? Don't worry, I'll cover
this in a bit, but before that I want to mention using ``__main__.py``.

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

Yup, that's all.

What does importing a module really mean?
-----------------------------------------

.. note::

   In case you're lost about the script / module / package terminology,
   let's assume that (1) a **script** is a ``.py`` file you can run with
   ``python script.py``, (2) a **module** is something you can import,
   and (3) a **package** is a specific kind of module consisting of
   a directory with an ``__init__.py``. This will be sufficient for the
   following discussion.

You might have the understanding that scripts can import other scripts
as modules alongside the ones you install with pip, and then access
functions and classes from them. This mental model is generally correct.
However, you may have made some assumptions about how modules are found.

When running ``python -m my_downloader``, how does Python know where to
find this ``my_downloader`` module? You might assume it always looks in the
current working directory, but this isn't true all the time. The exact answer is
`sys.path`_, a list of directories that Python searches when resolving imports.
The use of ``-m`` in ``python -m path.to.mod`` makes Python prepend your
current working directory to sys.path, unlike say, ``python path/to/main.py``
which prepends the script's directory, ``path/to/`` instead of your CWD.

**All absolute imports rely on sys.path.**

How an import like ``import matplotlib`` gets resolved in ``main.py``
is no different from how it gets resolved in ``seaborn/__init__.py``.
What changes is the directories listed in sys.path, mainly based on your
environment variables and how you run the Python interpreter.
It's a common mistake to think that because ``pkg/foo.py`` and ``pkg/bar.py``
are next to each other, both of them can do ``import bar`` or ``import foo``,
since in reality it depends on whether their parent directory is in sys.path.
If you ran foo.py using ``python -m pkg.foo``, the parent directory of ``pkg/``
would be in sys.path rather than ``pkg/`` itself, and therefore the imports
must be written as ``import pkg.foo`` or ``import pkg.bar``.

That's why for local projects, it's important to organize and run your scripts
in a consistent manner. For example, you might always put modules in a single
directory, including your scripts, and then run them directly:

.. _sys.path: https://docs.python.org/3/library/sys.html#sys.path

.. code-block:: python
   :force:

    my_project/
    └── app/
        ├── cli/
        │   ├── __init__.py
        │   └── __main__.py
        ├── layouts/
        │   ├── __init__.py
        │   └── ...
        ├── parser/
        │   ├── __init__.py
        │   └── ...
        ├── compile.py
        │       from layouts import create_layout
        │       from parser import Body, Footer, Header
        ├── generate.py
        └── validate.py

.. code-block:: shell

    /my_project $ python app/generate.py
    /my_project $ python app/validate.py
    /my_project $ python app/compile.py

Or you'll organize all of your scripts into a package in your project root:

.. code-block:: python
   :force:

    my_project/
    └── my_package/
        ├── sub_package/
        │   └── __init__.py
        │           from my_package import submodule
        ├── __init__.py
        │       from . import sub_package
        ├── __main__.py
        ├── migrate.py
        └── submodule.py

.. code-block:: shell

    /my_project $ python -m my_package --help
    /my_project $ python -m my_package.migrate --input foo.csv --input bar.csv

However you organize your scripts, the one thing I recommend is setting your
project root as the current working directory. ``cd`` ing around to run
different scripts for one project is cumbersome, can unintentionally change
your sys.path, and can be confusing for other users which have to contend with
the same file structure and might assume by default that your project root
is where they should run your commands from. However, if you think your way
makes your project structure easier to work with, feel free to stick to it!
As long as you document it for others (and perhaps your future self).
But what if you want to use your module from anywhere in your terminal?
Well now...

Permanently adding modules to sys.path
--------------------------------------

Remember, ``python -m my_downloader`` worked in the previous examples because
the current directory was ``/my_project`` and ``-m`` added it to ``sys.path``.
If you were to change to another directory, ``my_downloader`` would no
longer be resolvable. This is one of the reasons why we have pip - it lets us
install packages to a common place, ``site-packages/``, that Python always
knows to search for modules [#site]_ regardless of our current working directory.
However we're not there yet, as pip can't just install any plain old package.
It needs to be packaged into a distribution that pip knows how to install.
For this, I recommend looking into `setuptools + pyproject.toml`_ for writing
your build configuration.
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

There are several other keys that can be written in the |project-table|_ table,
but those two are the only required ones.

.. note::

   See how we didn't say anything about ``my_downloader/`` in pyproject.toml?
   This takes advantage of setuptools's `automatic discovery`_ to include the
   ``my_downloader/`` package in the distribution. This won't work with all
   layouts, and other build systems like `Hatch`_ and `Poetry`_ handle package
   discovery differently.

.. _automatic discovery: https://setuptools.pypa.io/en/latest/userguide/package_discovery.html#automatic-discovery
.. _Hatch: https://hatch.pypa.io/latest/
.. _Poetry: https://python-poetry.org/

To build your |sdist|_ and |wheel|_ distribution files:

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
through the `official installer`_, their system's PATH won't be updated
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
