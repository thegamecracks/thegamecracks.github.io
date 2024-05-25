Why can't I import my submodules?
=================================

.. toctree::

Are you trying to write a package but you can't figure out how to import your
submodules correctly, and it keeps failing with :py:exc:`ModuleNotFoundError`?
This shortened guide from my :doc:`invoking_modules` article should hopefully
help you understand why you're getting those errors, and how to fix it.

.. admonition:: Before you read...

   This guide requires some pre-requisite knowledge of using Python.
   If you can answer the following questions with at least some level
   of confidence, you can continue ahead:

   - What is a terminal? What can you use it for?
   - What is a current working directory?
   - How do you run Python scripts (``.py`` files) from the terminal?
   - How do you make a Python script import another script?

How do Python imports work?
---------------------------

In case you're not sure about the distinctions between a script, module,
and a package, let's assume that (1) a **script** is a ``.py`` file you
can run with ``python script.py``, (2) a **module** is something you can
import, and (3) a **package** is a specific kind of module consisting of
a directory with an ``__init__.py``.

You might already know that scripts can import other scripts as modules and
access their functions and classes, allowing you to organize your program
across separate files and re-use your code in a *modular* way.
However, when you start getting into writing packages and putting submodules
inside them, importing those submodules is no longer as intuitive as you
might think.

Take for example the following layout:

.. code-block:: python
    :force:

    CWD/
    ├── pkg/
    │   ├── __init__.py
    │   ├── foo.py
    │   └── bar.py
    └── main.py

If you were to write ``import bar`` in foo.py, what do you think would happen?
Presumably Python would find bar.py and import its contents because it's next
to foo.py, right? This is actually not always the case. ``import bar`` is an
*absolute import*, which means it's going to follow Python's `sys.path`_ to
find a ``bar`` module to be imported.

.. _sys.path: https://docs.python.org/3/library/sys.html#sys.path

How does sys.path affect imports?
---------------------------------

sys.path is a list of directories that Python searches when resolving imports.
When Python sees ``import bar``, it iterates through each directory to find the
first module that matches the name ``bar`` before importing it.
This includes your Python's standard library and the site-packages directory
where your pip-installed modules go to.

You can see for yourself what sys.path looks like by printing it out,
or by using the command ``python -m site``:

.. code-block:: python
    :force:

    sys.path = [
        '/home/thegamecracks/thegamecracks.github.io',
        '/home/thegamecracks/.pyenv/versions/3.11.9/lib/python311.zip',
        '/home/thegamecracks/.pyenv/versions/3.11.9/lib/python3.11',
        '/home/thegamecracks/.pyenv/versions/3.11.9/lib/python3.11/lib-dynload',
        '/home/thegamecracks/thegamecracks.github.io/.venv/lib/python3.11/site-packages',
    ]
    USER_BASE: '/home/thegamecracks/.local' (exists)
    USER_SITE: '/home/thegamecracks/.local/lib/python3.11/site-packages' (doesn't exist)
    ENABLE_USER_SITE: False

Now, here's the important thing to know: **All absolute imports rely on sys.path.**

It's a common mistake to think that because ``pkg/foo.py`` and ``pkg/bar.py``
are next to each other, either of them can use ``import foo`` or ``import bar``,
since absolute imports don't care about what modules are next to your script,
only modules that can be found in sys.path.

What affects sys.path then? The most important consideration here is how
you run Python in the terminal. When you run a command like ``python path/to/script.py``,
Python adds the directory containing the script, ``path/to/``, to sys.path.
So in the previous layout, if you ran ``python main.py``, ``CWD/`` would be in
sys.path. This means Python would only be able to find the package ``pkg``,
and not its inner modules ``foo`` and ``bar``.
Therefore, to import either submodule, you must refer to them by their
fully qualified names, ``pkg.foo`` and ``pkg.bar``, rather than simply
writing ``import bar``.

.. hint::

    This is where you might use `relative imports`_ over absolute imports!

    .. code-block:: python

        from . import foo
        from . import bar
        from .foo import ham, spam

    Python will assume that your relative imports start from each module's
    parent package, ``pkg``, meaning you don't have to write out their fully
    qualified names.
    In other words, the above relative imports become equivalent to
    the following absolute imports:

    .. code-block:: python

        from pkg import foo
        from pkg import bar
        from pkg.foo import ham, spam

    But beware, relative imports can't be used outside of submodules.
    You'll get an :py:exc:`ImportError` if you try to do so.

.. _relative imports: https://docs.python.org/3/tutorial/modules.html#intra-package-references

Because of these quirks, it's important to organize and run your scripts in a
consistent format to avoid stumbling into import problems and having to re-write
your imports. For example, you might put modules and scripts in the same directory
and then run your scripts with ``python path/to/script.py``:

.. code-block:: python
    :force:

    my_project/
    └── app/
        ├── layouts/
        │   ├── __init__.py
        │   │       from parser import Body, Footer, Header
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

Or you might organize all of your scripts into a package and use
``python -m package.submodule``:

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

The use of ``-m`` in ``python -m path.to.mod`` makes Python prepend your
current working directory to sys.path, unlike ``python path/to/main.py``
which prepends the script's parent directory.

However you organize your scripts, the one thing I recommend is setting your
project root as the current working directory. ``cd`` ing around to run
different scripts for one project is cumbersome, can unintentionally change
your sys.path, and can be confusing for other users which have to contend with
the same file structure and might assume that your project root is where they
should run your commands from. However, if you think your way makes your
project easier to work with, feel free to stick to it! Just make sure to keep
your procedures documented for others and/or for your future self.
