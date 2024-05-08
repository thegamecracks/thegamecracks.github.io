Using multi-threading and asyncio together
==========================================

.. toctree::

Most of the time when you write an asyncio application, it'll typically be
single-threaded and I/O-bound. This combination is what makes asyncio fast
and efficient compared to their equivalent threaded programs, because you
only need one thread to wait for network and other I/O operations to complete.
However in certain applications, blocking code is sometimes impossible to
escape, and so you'll find yourself combining asyncio with multiple threads.

Python's relationship with threading
------------------------------------

Before we discuss using threads, we need to talk about Python's
`Global Interpreter Lock`_.

As of 2024-05-08, Python 3.13 is slated to release in just under five months,
which will come with GIL and no-GIL builds as a result of the tremendous work
done towards :pep:`703`. For most of Python's lifetime, it lived with a lock
that prevented the Python interpreter from executing more than one bytecode
instruction at a time across threads. This meant that true parallelism with
pure-Python code couldn't be achived via multi-threading, so users that
needed this had to look towards other alternatives like multi-processing
which brings the overhead of :abbr:`IPC (inter-process communication)`,
or C-extensions that release the GIL but take more effort to maintain
and requires the extension to be compiled, either ahead of time by the
maintainer or by the user installing the extension.

.. _Global Interpreter Lock: https://realpython.com/python-gil/

As such, Python's multi-threading tended to be reserved for CPU-bound
operations implemented via C-extensions, or for I/O-bound operations.
`requests`_ for example is a library that performs I/O-bound HTTP requests
synchronously. Because a making request blocks the current thread,
you need multiple threads to make multiple requests simultaneously instead
of sequentially:

.. code-block:: python

    from concurrent.futures import ThreadPoolExecutor, as_completed
    import requests

    URLS = [...]

    def request(url: str, timeout: float) -> bytes:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.content

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {}
        for url in URLS:
            future_to_url[url] = executor.submit(request, url, timeout=60)

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            data = future.result()
            print(f"{url} page returned {len(data)} bytes")

.. seealso:: :py:class:`concurrent.futures.ThreadPoolExecutor`

.. _requests: https://docs.python-requests.org/

When you need a high amount of concurrency, you'll start to be limited by
your system resources when you have 100s to 1000s of threads. Of course
that might be enough to saturate your network, but overall it's not a
super efficient option for concurrent I/O.

That's why we have :py:mod:`asyncio`. Cooperative multi-tasking via an event loop
with callbacks, combined with non-blocking I/O, allows a single thread to
handle multiple requests at once, relying on the operating system to wake up
the thread when events / responses are received.
Coroutines and futures can then abstract the underlying callbacks
into a succinct syntax that resembles the procedural programming
Python developers are used to:

.. code-block:: python

    import asyncio
    import httpx

    URLS = [...]

    async def make_request(client: httpx.AsyncClient, url: str, timeout: float) -> bytes:
        async with client.get(url, timeout=timeout) as response:
            response.raise_for_status()
            return response.content

    async def main():
        async with httpx.AsyncClient() as client, asyncio.TaskGroup() as tg:
            tasks_to_url = {}
            for url in URLS:
                t = tg.create_task(make_request(client, url))
                tasks_to_url[t] = url

            for task in asyncio.as_completed(tasks_to_url):
                data = await task
                print(f"{url} page returned {len(data)} bytes")

    asyncio.run(main())

The difference being that each task of execution takes up much less
resources than threads, on the scale of `hundreds of thousands`_.

.. _hundreds of thousands: https://textual.textualize.io/blog/2023/03/08/overhead-of-python-asyncio-tasks/

.. note::

   :py:class:`asyncio.TaskGroup` was added in Python 3.11, and has similar
   semantics to ThreadPoolExecutor in that it ensures all tasks are
   completed upon exiting the context manager. But unlike the executor,
   TaskGroup will cancel any in-progress tasks if one of them fails.
   If you're not familiar with idea of "structured concurrency",
   you should read `Nathaniel J. Smith's article`_ about it,
   who also originally authored the `Trio`_ concurrency library.

.. _Nathaniel J. Smith's article: https://vorpus.org/blog/notes-on-structured-concurrency-or-go-statement-considered-harmful/
.. _Trio: https://trio.readthedocs.io/en/stable/index.html

Running threads in an event loop
--------------------------------

Because asyncio relies on **cooperative** multi-tasking for concurrency,
all callbacks that run on the event loop need to be non-blocking.
One blocking callback, which could be one step of a coroutine that incorrectly
makes a request using ``requests`` instead of an async HTTP client, would cause
the entire event loop to stop processing events until that callback finished.
The solution there is simple: use a library that relies on asyncio's mechanisms
for non-blocking I/O, like `aiohttp`_ or `httpx`_.
But sometimes it isn't that simple.
Maybe there's no async library written for that purpose, too much code
to migrate to async/await, or perhaps the blocking callback is CPU-bound
rather than I/O-bound, such as image processing with `Pillow`_.
In this case, you'll need to fallback to pre-emptive multi-tasking, either
with threads or `subprocesses`_. For this guide, I'll only cover threading.

.. _aiohttp: https://docs.aiohttp.org/
.. _httpx: https://www.python-httpx.org/
.. _Pillow: https://pillow.readthedocs.io/
.. _subprocesses: https://docs.python.org/3/library/asyncio-subprocess.html

Python 3.9 introduced :py:func:`asyncio.to_thread()` as a convenient shorthand
for submitting functions to the event loop's default thread pool executor:

.. code-block:: python

    def process_image(image: Image) -> Image:
        ...

    images = [...]
    tasks = []
    processed = []

    async with asyncio.TaskGroup() as tg:
        for image in images:
            coro = asyncio.to_thread(process_image, image)
            t = tg.create_task(coro)
            tasks.append(t)

        for t in tasks:
            processed.append(await t)

Before that, you had to call the lower-level
:py:meth:`loop.run_in_executor() <asyncio.loop.run_in_executor>`
method instead:

.. code-block:: python

    loop = asyncio.get_running_loop()
    futures = []

    for image in images:
        fut = loop.run_in_executor(None, process_image, image)
        futures.append(fut)

    try:
        await asyncio.gather(*futures)
    except BaseException:
        for fut in futures:
            fut.cancel()
        raise

You could also create your own ThreadPoolExecutor and submit tasks
to that instead:

.. code-block:: python

    async def main(executor: ThreadPoolExecutor):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(executor, process_image, image)

        # Above would be equivalent to writing:
        await asyncio.wrap_future(executor.submit(process_image, image))


    with ThreadPoolExecutor(max_workers=5) as executor:
        asyncio.run(main(executor))

Keep in mind that the default thread pool executor has a maximum number
of threads based on your processor's core count. As such, you **should not**
use :py:func:`asyncio.to_thread()` to run long-lived tasks, as that can
saturate the executor and reduce the number of workers available,
or worse, indefinitely prevent new tasks from being processed.

Managing long-lived tasks
-------------------------

.. warning:: This section is currently a work-in-progress.

What do you do to thread long-lived tasks then? It's simple! Thread them
as you normally would in a synchronous program.

.. code-block:: python

    def serve_forever(addr):
        ...

    async def main():
        thread = threading.Thread(target=serve_forever, args=(addr,))
        thread.start()
        # Profit???

...okay, but how do you communicate messages from your event loop to your
thread? And how do you make sure the thread closes alongside your
event loop? Well, this is where you should have a decent understanding
of thread-safety as it relates to asyncio.

(insert paragraph about handling thread closure)

.. warning::

   For threads that handle I/O or otherwise anything that should be
   cleaned up upon exiting, please refrain from using ``daemon=True``.
   Yes, it means you don't have to deal with checking when to stop,
   but it also makes your program prone to breaking when some missed
   teardown results in improperly closed connections or half-written
   files.

Running event loops in other threads
------------------------------------

.. warning:: This section is currently a work-in-progress.

In the previous sections I discussed, but what if you have a synchronous
program that you can't migrate to asyncio, but you still need to run
asynchronous code inside it?
