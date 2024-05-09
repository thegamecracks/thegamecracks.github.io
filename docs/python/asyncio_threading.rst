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
to that:

.. code-block:: python

    async def main(executor: ThreadPoolExecutor):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(executor, process_image, image)

        # Above would be equivalent to writing:
        await asyncio.wrap_future(executor.submit(process_image, image))


    with ThreadPoolExecutor(max_workers=5) as executor:
        asyncio.run(main(executor))

Keep in mind that the default thread pool executor has a maximum number
of threads based on your processor's core count. As such, you should **not**
run long-lived tasks on the default executor. That reduces the number of
workers available to other tasks and can at worst saturate the executor,
preventing new tasks from being processed indefinitely.

Managing long-lived tasks
-------------------------

What do you do to run long-lived tasks in threads then? It's simple!
Thread them as you normally would in a synchronous program:

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
because it's a versatile design pattern. How would we typically use a queue
in a synchronous program that processes images in the background?
Well, it might look like this:

.. code-block:: python

    import threading
    from queue import Queue

    class ImageProcessor:
        def __init__(self) -> None:
            self._queue: Queue[bytes | None] = Queue()
            self._thread: threading.Thread | None = None

        def __enter__(self):
            self._thread = threading.Thread(target=self.run_forever)
            self._thread.start()
            return self

        def __exit__(self, exc_type, exc_val, tb):
            if self._thread is not None:
                self._queue.put(None)
                self._thread.join()

        def run_forever(self):
            while True:
                item = self._queue.get()
                if item is None:
                    break
                # Do some processing with the given image bytes...

        def submit(self, image_bytes: bytes):
            self._queue.put(image_bytes)

    with ImageProcessor() as worker:
        worker.submit(b"some image bytes")

Here, we instantiate the queue object in the **main thread** and then start
the worker thread from our context manager, which blocks on the queue until
items are submitted to it. The thread knows to stop when it receives a ``None``
sentinel value upon exiting the context manager.

.. warning::

   For threads that handle I/O or otherwise anything that should be
   cleaned up upon exiting, please refrain from using ``daemon=True``
   and starting your thread without joining it.

   Yes, it means you don't have to deal with checking when to stop,
   but it also makes your program prone to breaking in obscure ways
   when some missed teardown results in improperly closed connections
   or half-written files.

How do we translate this to asyncio? Let's start with the simplest option,
which is using the same code in a coroutine:

.. code-block:: python

    async def main():
        with ImageProcessor() as worker:
            worker.submit(b"some image bytes")
            await do_something_else()

    asyncio.run(main())

For a simple script like this, you won't notice any issues with it!
That's because we only have one task in our event loop, the main task.
If ``do_something_else()`` were to receive an :py:class:`asyncio.CancelledError`,
perhaps caused by a keyboard interrupt, the context manager would tell
the worker to shut down and join the thread, freezing the event loop
during that period. The main task was the only thing running anyway,
so nothing else got blocked.
However, if there were other tasks running at the same time:

.. code-block:: python

    async def main():
        async with asyncio.TaskGroup() as tg:
            tg.create_task(do_something_else())

            with ImageProcessor() as worker:
                worker.submit(b"some image bytes")
                await asyncio.sleep(3)
                raise Exception("Houston, we have a problem!")

Then when exiting the worker, it would block the event loop until the remaining
image was processed, preventing ``do_something_else()`` from running during
that period. We could remove the ``_thread.join()`` call, but that would
make it much more confusing to reason about the thread's lifetime.
It's also worth noting that ``queue.put()`` can also block, but since the queue
doesn't have a max size set, it's effectively non-blocking.

So what do we do about it? Actually, not a lot is needed to avoid this problem.
Because ``worker.submit()`` doesn't need to be changed, the only problem we
have is shutting down the worker thread. To fix that, we just need to do the
same thing in the previous ThreadPoolExecutor example, which is to construct
our image processor before starting the event loop:

.. code-block:: python

    async def main(worker: ImageProcessor):
        async with asyncio.TaskGroup() as tg:
            tg.create_task(do_something_else())
            worker.submit(b"some image bytes")
            await asyncio.sleep(3)
            raise Exception("Houston, we have a problem!")

    with ImageProcessor() as worker:
        asyncio.run(main(worker))

Now if an error occurs, our event loop is able to run all remaining coroutines
and shut down before our worker blocks and shuts down.

*What if I want to create workers on the fly?*

Right, we didn't really solve the problem of managing threads from inside the
event loop. To do that, we'll need to know how to send events from the worker
to the event loop first.

Because of how asyncio depends on callbacks being non-blocking, the way you
communicate messages from your worker thread back to the event loop has to
be different from how you send messages to the worker thread. You can't just
wait on a :py:class:`queue.Queue` in asyncio, as that would block the event loop!
If only we had an asynchronous version of a queue to wait on...

You probably already guessed where this is going. Yes, asyncio has it's own
:py:class:`~asyncio.Queue` class! But you can see what it says in the docs:

    This class is `not thread safe`_.

.. _not thread safe: https://docs.python.org/3/library/asyncio-dev.html#asyncio-multithreading

Oh no, it's not thread-safe! That means we can't put items from another thread,
right? Actually, clicking the link in that text says we can, but not
by putting items from the thread directly:

    Almost all asyncio objects are not thread safe, which is typically not
    a problem unless there is code that works with them from outside of a
    Task or a callback. If there's a need for such code to call a low-level
    asyncio API, the :py:meth:`loop.call_soon_threadsafe() <asyncio.loop.call_soon_threadsafe>`
    method should be used, e.g.:

    .. code-block:: python

        loop.call_soon_threadsafe(fut.cancel)

Okay, so this method is how we can call methods of asyncio objects from
other threads.

But what makes this method thread-safe compared to calling :py:meth:`queue.put_nowait() <asyncio.Queue.put_nowait>`
directly? Well, this comes down to what an event loop really does.
You can guess from the name that there's a loop, but if you look at its
`source code <https://github.com/python/cpython/blob/v3.12.3/Lib/asyncio/base_events.py#L1910-L1988>`_,
you can see what happens in each iteration:

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
How the selector waits for events will depend on the type of event loop
that was created by asyncio, but by default, the :py:class:`~asyncio.DefaultEventLoopPolicy`
uses the :py:mod:`selectors` module on Unix, and `I/O Completion Ports`_ on Windows.
Both of them interface with the operating system's APIs to wait on multiple
data sources at once, whether it be network sockets, or named pipes used in IPC.

.. _I/O Completion Ports: https://learn.microsoft.com/en-ca/windows/win32/fileio/i-o-completion-ports

Why does this matter to using ``asyncio.Queue`` from another thread?
Well, you know how once a thread calls a function that blocks, that thread can't
do anything else? [#signals]_ For an event loop, the same issue exists too.
If you were to call ``queue.put_nowait()`` from the worker thread while the
event loop was waiting on an event, the item *would* get queued but nothing
would happen because the event loop is still blocked on the selector.
How does ``loop.call_soon_threadsafe()`` solve this issue? It schedules your
callback to run on the event loop's thread, and then sends one byte to a
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

That wakes up the event loop, allowing it to run the callback
you passed to the method along with anything else that was scheduled.
If we were to pass ``queue.put_nowait`` as our callback, that would enqueue
our item for us and wake up the first task waiting on ``queue.get()``,
scheduling the task to resume in the next iteration of the event loop.
So that's everything we need! Let's put that method into practice.
We can add a way to register callbacks on our worker that run when an item
has finished processing:

.. code-block:: python
    :emphasize-lines: 9, 21-22, 30-31

    from typing import Callable

    ImageProcessorCallback = Callable[[bytes], object]

    class ImageProcessor:
        def __init__(self) -> None:
            self._queue: Queue[bytes | None] = Queue()
            self._thread: threading.Thread | None = None
            self._callbacks: list[ImageProcessorCallback] = []

        def __enter__(self):
            self._thread = threading.Thread(target=self.run_forever)
            self._thread.start()
            return self

        def __exit__(self, exc_type, exc_val, tb):
            if self._thread is not None:
                self._queue.put(None)
                self._thread.join()

        def add_done_callback(self, callback: ImageProcessorCallback):
            self._callbacks.append(callback)

        def run_forever(self):
            while True:
                item = self._queue.get()
                if item is None:
                    break
                # Do some processing with the given image bytes...
                for callback in self._callbacks:
                    callback(result)

        def submit(self, image_bytes: bytes):
            self._queue.put(image_bytes)

And then use it to redirect results to an asynchronous queue:

.. code-block:: python

    async def main(worker: ImageProcessor):
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        worker.add_done_callback(
            lambda result: loop.call_soon_threadsafe(queue.put_nowait, result)
        )

        worker.submit(b"some image bytes")
        result = await queue.get()
        print("processed image bytes:", result)

And there you go! This uses a thread-safe queue and non-blocking callbacks
to communicate events between both threads at once.
We can wrap it up in another class to make this interaction simpler:

.. code-block:: python

    class AsyncImageProcessor:
        def __init__(self, worker: ImageProcessor):
            self._worker = worker
            self._queue: asyncio.Queue[bytes] = asyncio.Queue()
            self._loop = asyncio.get_running_loop()
            self._worker.add_done_callback(self._on_item_processed)

        def _on_item_processed(self, result: bytes):
            self._loop.call_soon_threadsafe(self._queue.put_nowait, result)

        async def submit(self, item: bytes) -> bytes:
            self._worker.submit(item)
            return await self._queue.get()

        # Because the worker processes items sequentially and queue.get()
        # wakes up waiters in FIFO order, our results will be in the same order.
        # This would stop being true if items could be returned out of order.
        #
        # The callback could also use something besides an asyncio.Queue to
        # store results and notify waiters, like pairing each item with an
        # asyncio future.


    async def main(sync_worker: ImageProcessor):
        worker = AsyncImageProcessor(sync_worker)
        tasks = []
        async with asyncio.TaskGroup() as tg:
            for i in range(5):
                image = f"image {i}".encode()
                task = tg.create_task(worker.submit(image))
                tasks.append(task)

            for task in asyncio.as_completed(tasks):
                print(await task)

.. note::

    *Hey, what about* ``queue.put()`` *? Can I pass that as a callback too?*

    From asyncio's perspective, callbacks just mean synchronous functions.
    :py:meth:`queue.put() <asyncio.Queue.put>` returns a coroutine object,
    and the event loop doesn't actually know how to run a coroutine object
    by itself. That's what an :py:class:`asyncio.Task` is for; it knows how
    to turn the "steps" in a coroutine into callbacks, and schedule them on
    the event loop.

    There's more to investigate here about how futures bridge the event loop's
    low-level callbacks with high-level async/await coroutines, but I
    won't discuss it in this guide. Just know that there's a separate function
    for scheduling coroutines from other threads, :py:func:`~asyncio.run_coroutine_threadsafe()`,
    which has the handy feature of returning a :py:class:`concurrent.futures.Future`
    that lets you wait on the coroutine's result from another thread.

Running event loops in other threads
------------------------------------

In the previous sections I discussed creating threads to be used by
the asyncio event loop, but what if you have a synchronous program
that you can't migrate to asyncio and yet you still need to run
asynchronous code inside it?

Before we start threading, let's understand the ways we can run coroutines
in our main thread. First and foremost is :py:func:`asyncio.run()`:

.. code-block:: python

    import asyncio

    async def request(url: str) -> bytes:
        async with httpx.AsyncClient() as client:
            ...

    first = asyncio.run(request("https://example.com"))
    second = asyncio.run(request("https://sub.example.com"))

:py:func:`asyncio.run()` starts a new event loop each time, runs your
coroutine to completion, cleans up the event loop, and then returns the
result of your coroutine. This can be sufficient for some scenarios,
but it requires the coroutine to set up any asynchronous resources from within
the event loop. asyncio's primitives, whether it be locks, queues, or sockets,
are tightly coupled to the event loop they're created in. Trying to re-use
them across event loops can lead to obscure errors as a result of callbacks
running on different event loops:

.. code-block:: python

    import asyncio

    async def new_fut() -> asyncio.Future:
        fut = asyncio.get_running_loop().create_future()
        fut.add_done_callback(lambda fut: print("fut finished"))
        return fut

    async def set_fut(fut: asyncio.Future):
        fut.set_result("Done!")

    fut = asyncio.run(new_fut())
    asyncio.run(set_fut(fut))

.. code-block:: python
    :force:

    Traceback (most recent call last):
    File "main.py", line 12, in <module>
        asyncio.run(set_fut(fut))
    File "Lib\asyncio\runners.py", line 190, in run
        return runner.run(main)
               ^^^^^^^^^^^^^^^^
    File "Lib\asyncio\runners.py", line 118, in run
        return self._loop.run_until_complete(task)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    File "Lib\asyncio\base_events.py", line 654, in run_until_complete
        return future.result()
               ^^^^^^^^^^^^^^^
    File "main.py", line 9, in set_fut
        fut.set_result("Done!")
    File "Lib\asyncio\base_events.py", line 762, in call_soon
        self._check_closed()
    File "Lib\asyncio\base_events.py", line 520, in _check_closed
        raise RuntimeError('Event loop is closed')
    RuntimeError: Event loop is closed

This example looks a bit weird since we're just passing a future,
but in a practical situation this can happen indirectly when you
re-use some instance from an async library, like an HTTP client.
With Python 3.11 and newer, the :py:class:`asyncio.Runner` class
can avoid this issue by re-using an event loop to run multiple
coroutines:

.. code-block:: python

    with asyncio.Runner() as runner:
        fut = runner.run(new_fut())
        runner.run(set_fut(fut))

This lets you start, pause, and resume the event loop while ensuring
that it gets cleaned up once you exit the context manager.
For older versions, you had to create the event loop yourself:

.. code-block:: python

    loop = asyncio.new_event_loop()

    fut = loop.run_until_complete(new_fut())
    loop.run_until_complete(set_fut(fut))

    loop.close()

However, managing the event loop like above is notoriously difficult
to get right. The above example, which you might see often in other
codebases, has multiple problems with it:

1. Current event loop not set for the thread
2. Execution and teardown not enclosed in try/finally
3. Asynchronous generators not closed
4. Default executor not closed
5. Remaining tasks not cancelled and waited on

In short, it has a high risk of not executing try/finally clauses
and leaving behind unclosed resources (see `this gist <https://gist.github.com/thegamecracks/e14904a2ffe346a4f74c827d7492cc38>`_
for an example).
If you really need to do this, I suggest vendoring the `Runner <https://github.com/python/cpython/blob/v3.12.3/Lib/asyncio/runners.py>`_
class from CPython's source code, or re-purposing `asyncio.run() <https://github.com/python/cpython/blob/v3.10.14/Lib/asyncio/runners.py>`_'s
implementation as it existed in 3.10 and older.

Regardless of which one you pick above, they all have the same limitation
in that the event loop stops running in between the coroutines you pass to it.
If you wanted to say, serve multiple connections asynchronously, the event loop
would only run during the ``.run()`` call when you add another connection, before
pausing indefinitely again. This is where we come back to threads! With the above
options in mind, how do we start an event loop in another thread?

Well, the first thing you can start with is passing :py:func:`asyncio.run()`
as a target function for the thread to run:

.. code-block:: python

    async def func():
        ...

    coro = func()
    thread = threading.Thread(target=asyncio.run, args=(coro,))
    thread.start()

But we know that :py:func:`asyncio.run()` can only run one coroutine before
it closes the event loop. How do we give it more than one coroutine to run?
We need a way to run coroutines while keeping the event loop alive...

What if we give it a coroutine that runs forever? Let's see:

.. code-block:: python

    async def run_forever():
        while True:
            await asyncio.sleep(60)

    thread = threading.Thread(target=asyncio.run, args=(run_forever(),))
    thread.start()

Now the event loop is running indefinitely, but we don't have a way to
pass it coroutines. If you followed along in the previous sections, you
might recall the :py:func:`asyncio.run_coroutine_threadsafe()` function
I briefly mentioned. It exists specifically to let threads submit coroutines
to an event loop and wait on their results if needed. But if you look at
its signature, you'll see it needs a coroutine object and the event loop
object. We don't have an event loop object in our main thread, so we need
a way to have the worker thread send us an event loop object back.
We can do this in many ways, but let's try a simple one, which is assigning
the loop to an attribute and then setting an event:

.. code-block:: python

    class EventThread:
        def __init__(self):
            self._thread: threading.Thread | None = None
            self._loop: asyncio.AbstractEventLoop | None = None
            self._event = threading.Event()

        def start(self):
            self._thread = threading.Thread(target=asyncio.run, args=(self._run_forever(),), daemon=True)
            self._thread.start()

        def get_loop(self) -> asyncio.AbstractEventLoop:
            self._event.wait()
            assert self._loop is not None
            return self._loop

        async def _run_forever(self):
            self._set_event_loop()
            while True:
                await asyncio.sleep(60)

        def _set_event_loop(self):
            self._loop = asyncio.get_running_loop()
            self._event.set()

And putting our EventThread class into practice:

.. code-block:: python

    async def func():
        await asyncio.sleep(1)
        print("Hello from event loop!")
        return 1234

    thread = EventThread()
    thread.start()

    loop = thread.get_loop()
    fut = asyncio.run_coroutine_threadsafe(func(), loop)
    print("Main thread waiting on coroutine...")
    result = fut.result()
    print("Main thread received:", result)

.. code-block:: python
    :force:

    Main thread waiting on coroutine...
    Hello from event loop!
    Main thread received: 1234

Great! We have an event loop that runs forever and a way to submit coroutines
to it. The last thing we're missing is a way to *gracefully* stop the thread.
If you read the class carefully, you'll notice that the thread had ``daemon=True``
set which would abruptly kill the thread, risking improper cleanup just like the
previous ``asyncio.new_event_loop()`` example. To avoid that, we need a way
to send a signal to our ``_run_forever()`` method so it knows to exit.

Given that we used an event to notify the main thread of our event loop object,
let's try to do the same thing here but with :py:class:`asyncio.Event` instead.
As per the last section, we know that we can call the event's ``set()`` method
from our main thread using ``loop.call_soon_threadsafe(event.set)`` instead of
``asyncio.run_coroutine_threadsafe()`` since ``event.set()`` isn't a coroutine.
Both will work, but the former will be a bit simpler in our case:

.. code-block:: python
    :emphasize-lines: 6, 18-22, 25, 27

    class EventThread:
        def __init__(self):
            self._loop: asyncio.AbstractEventLoop | None = None
            self._event = threading.Event()
            self._thread: threading.Thread | None = None
            self._stop_ev: asyncio.Event | None = None

        def start(self):
            coro = self._run_forever()
            self._thread = threading.Thread(target=asyncio.run, args=(coro,))
            self._thread.start()

        def get_loop(self) -> asyncio.AbstractEventLoop:
            self._event.wait()
            assert self._loop is not None
            return self._loop

        def stop(self):
            assert self._stop_ev is not None
            assert self._thread is not None
            self.get_loop().call_soon_threadsafe(self._stop_ev.set)
            self._thread.join()

        async def _run_forever(self):
            self._stop_ev = asyncio.Event()
            self._set_event_loop()
            await self._stop_ev.wait()

        def _set_event_loop(self):
            self._loop = asyncio.get_running_loop()
            self._event.set()

And now we can stop the event loop at the end:

.. code-block:: python
    :emphasize-lines: 10-11

    thread = EventThread()
    thread.start()

    loop = thread.get_loop()
    fut = asyncio.run_coroutine_threadsafe(func(), loop)
    print("Main thread waiting on coroutine...")
    result = fut.result()
    print("Main thread received:", result)

    thread.stop()
    print("Event loop stopped")

.. code-block:: python
    :emphasize-lines: 4
    :force:

    Main thread waiting on coroutine...
    Hello from event loop!
    Main thread received: 1234
    Event loop stopped

Finally, we have a class that can run an event loop indefinitely
and let us submit any coroutine to it! 🎉

Refactoring our EventThread class
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Before I end this guide, I want to suggest some improvements to this class.
For one, the ``start()`` and ``stop()`` methods should be turned into a
context manager so it's harder to accidentally leave it unclosed.
It could also use a ``submit()`` method that handles calling
``asyncio.run_coroutine_threadsafe()`` for us.
But I want to talk about the more interesting topic, futures.

First, what is a future? According to :py:class:`asyncio.Future`'s docs:

    A Future represents an eventual result of an asynchronous operation.

What does that mean? In Python, this Future class is something you can call
``set_result()`` on with some arbitrary value, and you can ``await`` from a
coroutine to get its result. It also has this ``add_done_callback()`` method
to make stuff run when the result is set.
In other words, it's kind of like a one-time event that stores a value
when it's done. If you look back at the EventThread class:

.. code-block:: python

    class EventThread:
        def __init__(self):
            self._loop: asyncio.AbstractEventLoop | None = None
            self._event = threading.Event()
            ...

        def _set_event_loop(self):
            self._loop = asyncio.get_running_loop()
            self._event.set()

We have a ``threading.Event`` that gets set right after the ``_loop`` attribute
is assigned a value. See what I'm getting at? We've manually combined an event
and attribute together to essentially hand-craft our own future, except that
it's for synchronous threads rather than asyncio.
What if we had a full-fledged synchronous future object that worked like
``asyncio.Future``?

Well, you've been looking at that since the very start of this guide!
The :py:mod:`concurrent.futures` package has its own implementation of
futures used to transfer results from worker threads back to the caller:

.. code-block:: python

    with ThreadPoolExecutor() as executor:
        fut = executor.submit(my_func, arg1, arg2)
        fut.result()

What it returns is a :py:class:`concurrent.futures.Future` class, and calling
``.result()`` is how we wait for results (since we can't use ``await`` outside
of ``async def`` functions). It also has the same ``add_done_callback()`` method
to let us add our own callbacks!

Can we create our own futures and use it for other things?

Here's the awkward bit, the documentation says:

    Future instances are created by :py:meth:`Executor.submit() <concurrent.futures.Executor>`
    and should not be created directly except for testing.

Supposedly we shouldn't use this beyond testing purposes.
But if you look at how `run_coroutine_threadsafe() <https://github.com/python/cpython/blob/v3.12.3/Lib/asyncio/tasks.py#L931-L951>`_
is implemented:

.. code-block:: python
    :emphasize-lines: 8

    def run_coroutine_threadsafe(coro, loop):
        """Submit a coroutine object to a given event loop.

        Return a concurrent.futures.Future to access the result.
        """
        if not coroutines.iscoroutine(coro):
            raise TypeError('A coroutine object is required')
        future = concurrent.futures.Future()

        def callback():
            try:
                futures._chain_future(ensure_future(coro, loop=loop), future)
            except (SystemExit, KeyboardInterrupt):
                raise
            except BaseException as exc:
                if future.set_running_or_notify_cancel():
                    future.set_exception(exc)
                raise

        loop.call_soon_threadsafe(callback)
        return future

It's not actually that difficult to set up the class. You'll also notice
there's a function in asyncio, :py:func:`asyncio.wrap_future()`,
specifically meant to convert these Future objects into asyncio equivalents:

.. py:function:: asyncio.wrap_future(future, *, loop=None)

    Wrap a :py:class:`concurrent.futures.Future` object in
    a :py:class:`asyncio.Future` object.

Admittedly I can't guarantee that ``concurrent.futures.Future`` won't
break in future versions of Python, but regardless, it's perfect for
our EventThread class which needs to broadcast a single value from its thread.
Let's replace our ``_event`` and ``_loop`` attributes with a single
``_loop_fut`` attribute:

.. code-block:: python
    :emphasize-lines: 11, 25-26, 36-37

    from typing import Awaitable, TypeVar

    T = TypeVar("T")

    class EventThread:
        _loop_fut: concurrent.futures.Future[asyncio.AbstractEventLoop]

        def __init__(self):
            self._thread: threading.Thread | None = None
            self._stop_ev: asyncio.Event | None = None
            self._loop_fut = concurrent.futures.Future()

        def __enter__(self):
            coro = self._run_forever()
            self._thread = threading.Thread(target=asyncio.run, args=(coro,))
            self._thread.start()
            return self

        def __exit__(self, exc_type, exc_val, tb):
            assert self._stop_ev is not None
            assert self._thread is not None
            self.get_loop().call_soon_threadsafe(self._stop_ev.set)
            self._thread.join()

        def get_loop(self) -> asyncio.AbstractEventLoop:
            return self._loop_fut.result()

        def submit(self, coro: Awaitable[T]) -> concurrent.futures.Future[T]:
            return asyncio.run_coroutine_threadsafe(coro, self.get_loop())

        async def _run_forever(self):
            self._stop_ev = asyncio.Event()
            self._set_event_loop()
            await self._stop_ev.wait()

        def _set_event_loop(self):
            self._loop_fut.set_result(asyncio.get_running_loop())

We can also go one step further and replace ``_stop_ev`` with a stop future:

.. code-block:: python
    :emphasize-lines: 8, 18, 29

    class EventThread:
        _loop_fut: concurrent.futures.Future[asyncio.AbstractEventLoop]
        _stop_fut: concurrent.futures.Future[None]

        def __init__(self):
            self._thread: threading.Thread | None = None
            self._loop_fut = concurrent.futures.Future()
            self._stop_fut = concurrent.futures.Future()

        def __enter__(self):
            coro = self._run_forever()
            self._thread = threading.Thread(target=asyncio.run, args=(coro,))
            self._thread.start()
            return self

        def __exit__(self, exc_type, exc_val, tb):
            assert self._thread is not None
            self._stop_fut.set_result(None)
            self._thread.join()

        def get_loop(self) -> asyncio.AbstractEventLoop:
            return self._loop_fut.result()

        def submit(self, coro: Awaitable[T]) -> concurrent.futures.Future[T]:
            return asyncio.run_coroutine_threadsafe(coro, self.get_loop())

        async def _run_forever(self):
            self._set_event_loop()
            await asyncio.wrap_future(self._stop_fut)

        def _set_event_loop(self):
            self._loop_fut.set_result(asyncio.get_running_loop())

And just for fun, let's use a third to allow the main thread (or other threads)
to add callbacks that run when the event loop stops:

.. code-block:: python
    :emphasize-lines: 12, 31-32, 39

    EventThreadCallback = Callable[[concurrent.futures.Future[None]], object]

    class EventThread:
        _loop_fut: concurrent.futures.Future[asyncio.AbstractEventLoop]
        _stop_fut: concurrent.futures.Future[None]
        _finished_fut: concurrent.futures.Future[None]

        def __init__(self):
            self._thread: threading.Thread | None = None
            self._loop_fut = concurrent.futures.Future()
            self._stop_fut = concurrent.futures.Future()
            self._finished_fut = concurrent.futures.Future()

        def __enter__(self):
            coro = self._run_forever()
            self._thread = threading.Thread(target=asyncio.run, args=(coro,))
            self._thread.start()
            return self

        def __exit__(self, exc_type, exc_val, tb):
            assert self._thread is not None
            self._stop_fut.set_result(None)
            self._thread.join()

        def get_loop(self) -> asyncio.AbstractEventLoop:
            return self._loop_fut.result()

        def submit(self, coro: Awaitable[T]) -> concurrent.futures.Future[T]:
            return asyncio.run_coroutine_threadsafe(coro, self.get_loop())

        def add_done_callback(self, callback: EventThreadCallback):
            self._finished_fut.add_done_callback(callback)

        async def _run_forever(self):
            self._set_event_loop()
            try:
                await asyncio.wrap_future(self._stop_fut)
            finally:
                self._finished_fut.set_result(None)

        def _set_event_loop(self):
            self._loop_fut.set_result(asyncio.get_running_loop())

This is what its usage will look like:

.. code-block:: python
    :emphasize-lines: 2

    with EventThread() as thread:
        thread.add_done_callback(lambda fut: print("Event loop stopped"))

        fut = thread.submit(func())
        print("Main thread waiting on coroutine...")
        result = fut.result()
        print("Main thread received:", result)

.. caution::

    Callbacks added to :py:class:`concurrent.futures.Future` will run on
    whichever thread calls its ``set_result()`` method. As such, you should
    make sure to only add callbacks that are thread-safe, such as a function
    that sets a :py:class:`threading.Event` or pushes to a :py:class:`queue.Queue`.

.. *But what's the point of using callbacks for this? Can't I just run my code*
.. *after the event thread's already exited?*
..
.. TODO: showcase practical usage of EventThread.add_done_callback()

.. rubric:: Footnotes

.. [#signals]
   :py:mod:`Signals <signal>` can interrupt threads, but in Python only
   the main thread runs signal handlers, so it won't work here for IPC.
