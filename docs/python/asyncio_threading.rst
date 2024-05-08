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
run long-lived tasks on the default executor as that reduces the number of
workers available, or worse, saturate the executor and indefinitely prevent
new tasks from being processed.

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

Let's start with inter-thread communication in the form of queues and messages
because it's a versatile design to use. How would we typically use a queue
in a synchronous program that processes images in the background?
Well, it might look like this:

.. code-block:: python

    import threading
    from queue import Queue

    class ImageProcessor:
        def __init__(self) -> None:
            self.queue: Queue[bytes | None] = Queue()
            self._thread: threading.Thread | None = None

        def __enter__(self):
            self._thread = threading.Thread(target=self.run_forever)
            self._thread.start()
            return self

        def __exit__(self, exc_type, exc_val, tb):
            if self._thread is not None:
                self.queue.put(None)
                self._thread.join()

        def run_forever(self):
            while True:
                item = self.queue.get()
                if item is None:
                    break
                # Do some processing with the given image bytes...

        def submit(self, image_bytes: bytes):
            self.queue.put(image_bytes)

    with ImageProcessor() as worker:
        worker.submit(b"some image bytes")

Here, we instantiate the queue object in the **main thread** and then start
the worker thread from our context manager, which blocks on the queue until
items are submitted to it. The thread knows to stop when it receives a ``None``
sentinel value marking the end of subsequent jobs.

How do we translate this to asyncio? Let's start with the simplest option,
which is using the same code:

.. code-block:: python

    async def main():
        with ImageProcessor() as worker:
            worker.submit(b"some image bytes")
            await do_something_else()

    asyncio.run(main())

And for a simple script like this, you won't notice any issues with it!
That's because we only have one task in our event loop, the main task.
If ``do_something_else()`` were to receive an :py:class:`asyncio.CancelledError`,
perhaps caused by a keyboard interrupt, the context manager would tell
the worker to shut down and join the thread, freezing the event loop
during that period. The main task was the only thing running anyway,
so nothing else got blocked.
However, if there were other tasks running at the same time:

.. code-block:: python

    TODO

(insert paragraph about handling thread closure)

.. warning::

   For threads that handle I/O or otherwise anything that should be
   cleaned up upon exiting, please refrain from using ``daemon=True``.
   Yes, it means you don't have to deal with checking when to stop,
   but it also makes your program prone to breaking when some missed
   teardown results in improperly closed connections or half-written
   files.

TODO

Because of how asyncio depends on callbacks being non-blocking, the way you
communicate messages from your worker thread back to the event loop has to
be different from how you send messages to the worker thread. You can't just
wait on a :py:class:`queue.Queue` in asyncio, as that would block the event loop!
If only we had an asynchronous version of a queue to wait on...

You probably already guessed where this is going. Yes, asyncio has it's own
:py:class:`~asyncio.Queue` class. But you can see what it says in the docs:

    This class is `not thread safe`_.

.. _not thread safe: https://docs.python.org/3/library/asyncio-dev.html#asyncio-multithreading

Oh no, it's not thread-safe! That means we can't put items into this queue
from another thread, right? Actually, clicking the link in that text gives
us the solution:

    Almost all asyncio objects are not thread safe, which is typically not
    a problem unless there is code that works with them from outside of a
    Task or a callback. If there's a need for such code to call a low-level
    asyncio API, the :py:meth:`loop.call_soon_threadsafe() <asyncio.loop.call_soon_threadsafe>`
    method should be used, e.g.:

    .. code-block:: python

        loop.call_soon_threadsafe(fut.cancel)

But what makes this method thread-safe compared to calling :py:meth:`queue.put_nowait() <asyncio.Queue.put_nowait>`
directly? Well, this comes down to what an event loop is built on.
You can guess from the name that there's a loop, but if you look at its
`source code <https://github.com/python/cpython/blob/v3.12.3/Lib/asyncio/base_events.py#L1910-L1988>`_,
you can see what it really does each iteration:

.. code-block:: python

    def _run_once(self):
        """Run one full iteration of the event loop.

        This calls all currently ready callbacks, polls for I/O,
        schedules the resulting callbacks, and finally schedules
        'call_later' callbacks.
        """
        ...
        event_list = self._selector.select(timeout)
        self._process_events(event_list)
        ...
        for i in range(ntodo):
            handle = self._ready.popleft()
            ...
            handle._run()

It **blocks** on this selector object waiting for events to come in,
and then runs all callbacks scheduled for that iteration.
How does that selector wait for events? The exact mechanism depends on the type
of event loop that was created by asyncio, but by default, the :py:class:`~asyncio.DefaultEventLoopPolicy`
returns a :py:class:`~asyncio.SelectorEventLoop` on Unix which uses the
:py:mod:`selectors` module, and on Windows it returns a :py:class:`~asyncio.ProactorEventLoop`
which uses Windows's `I/O Completion Ports`_ API. In either case, the operating
system allows Python to wait on multiple data sources at once, whether it be
network sockets or named pipes used in IPC.

.. _I/O Completion Ports: https://learn.microsoft.com/en-ca/windows/win32/fileio/i-o-completion-ports

So why does this matter to using ``asyncio.Queue`` from another thread?
Well, you know how once you call a function that blocks, that thread can't
do anything else? [#signals]_ For an event loop, the same issue exists too.
If you were to call ``queue.put_nowait()`` from the worker thread while the
event loop was waiting on an event, the item *would* get queued but nothing
would happen because the event loop is still blocked on the selector.
How does ``loop.call_soon_threadsafe()`` solve this issue? It schedules
your callback to run on the event loop's thread, and sends one byte to a
self-pipe which the selector is listening on:

.. code-block:: python
   :emphasize-lines: 6, 9

    def call_soon_threadsafe(self, callback, *args, context=None):
        """Like call_soon(), but thread-safe."""
        self._check_closed()
        if self._debug:
            self._check_callback(callback, 'call_soon_threadsafe')
        handle = self._call_soon(callback, args, context)
        if handle._source_traceback:
            del handle._source_traceback[-1]
        self._write_to_self()
        return handle

That wakes up the event loop immediately, allowing it to run the callback
you passed to the method along with anything else that was scheduled.
If we were to pass ``queue.put_nowait`` as our callback, that would enqueue
our item for us and wake up the first task waiting on ``queue.get()``,
enqueuing the task to resume in the next iteration of the event loop.
So that's everything we need! Let's put that method into practice:

.. code-block:: python

    TODO

.. note::

    *Hey, what about* ``queue.put()`` *? Can I pass that as a callback too?*

    From asyncio's perspective, callbacks just mean synchronous functions.
    :py:meth:`queue.put() <asyncio.Queue.put>` returns a coroutine object,
    and the event loop doesn't actually know how to run a coroutine object
    by itself. That's what an :py:class:`asyncio.Task` is for; it knows how
    to turn the "steps" in a coroutine into callbacks, and schedule them on
    the event loop.

    There's more to investigate here about how futures bridge the event loop's
    low-level callbacks with our high-level, async/await coroutines, but I
    won't discuss it in this guide. Just know that there's a separate function
    for scheduling coroutines from other threads, :py:func:`asyncio.run_coroutine_threadsafe()`,
    which has the handy feature of returning a :py:class:`concurrent.futures.Future`
    that lets you wait on the coroutine's result from another thread.

Running event loops in other threads
------------------------------------

.. warning:: This section is currently a work-in-progress.

In the previous sections I discussed, but what if you have a synchronous
program that you can't migrate to asyncio, but you still need to run
asynchronous code inside it?

.. rubric:: Footnotes

.. [#signals]
   :py:mod:`Signals <signal>` can interrupt threads, but in Python only
   the main thread runs signal handlers, so it won't work here for IPC.