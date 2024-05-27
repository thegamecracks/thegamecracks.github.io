Writing Persistent Views
========================

.. toctree::

In `discord.py`_, persistent views allow a bot to handle interactions from
message components (i.e. buttons and select menus) after the bot has restarted.

.. _discord.py: https://discordpy.readthedocs.io/

For a view to be persistent, all its components must have a custom ID
and the view must have its timeout set to None. This can look something like:

.. code-block:: python

    class CreateTicketView(discord.ui.View):
        @discord.ui.button(label="Submit a Ticket", custom_id="create-ticket")
        async def on_create(self, interaction, button):
            ...

    view = CreateTicketView(timeout=None)
    await ctx.send("Need support from staff?", view=view)

Once your bot restarts, you must add back your persistent view so discord.py
knows which methods should be called when the same components are interacted with.
This can be done with the |add_view|_ method:

.. code-block:: python

    class MyClient(discord.Client):  # or commands.Bot
        async def setup_hook(self):
            view = CreateTicketView(timeout=None)
            self.add_view(view)

.. |add_view| replace:: ``Client.add_view()``
.. _add_view: https://discordpy.readthedocs.io/en/stable/api.html#discord.Client.add_view

Once you start your bot, this will handle interactions from *all messages* that
had ``CreateTicketView`` sent with them.

This works well for views that are stateless, meaning the view doesn't have any
attributes that need to be different between two messages with the same view.
However, sometimes you will need to implement views that require state.
The following example shows a view that can only be used by a particular user:

.. code-block:: python

    class GreetingView(discord.ui.View):
        def __init__(self, user_id):
            super().__init__(timeout=None)
            self.user_id = user_id

        @discord.ui.button(label="Greet", custom_id="greet")
        async def greet(self, interaction, button):
            mention = interaction.user.mention
            await interaction.response.send_message(f"Greetings {mention}!", ephemeral=True)

        async def interaction_check(self, interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message(
                    f"This button is only for greeting <@{self.user_id}>!",
                    ephemeral=True,
                )
                return False
            return True

To handle views like this after startup, you will need to pass the original
arguments to ``__init__()`` and give discord.py the same message IDs that
you sent with each of your view instances.
For a few messages, you can manually hardcode those values like so:

.. code-block:: python

    class MyClient(discord.Client):
        async def setup_hook(self):
            greet_erica = GreetingView(user_id=297463612870492160)
            self.add_view(greet_erica, message_id=1165036547050057789)

            greet_jack = GreetingView(user_id=581280216836734988)
            self.add_view(greet_jack, message_id=1165037150992085143)

Of course if your bot sends new views often, you wouldn't want to edit your
code each time to persist them, so it's a good idea to use a database for this.

Below are two examples, one implementing a stateless view and another
implementing a stateful view, using `sqlite3`_ to store the view's
state on disk.

.. note::

    `sqlite3`_ is a synchronous library which can block your bot from running
    if it has to wait for a database lock to be released. For practical usage,
    consider `asqlite`_ or a different database like PostgreSQL with the `asyncpg`_
    driver.

.. _sqlite3: https://docs.python.org/3/library/sqlite3.html
.. _asqlite: https://github.com/Rapptz/asqlite
.. _asyncpg: https://magicstack.github.io/asyncpg/current/

.. code-block:: python
    :caption: stateless.py

    import discord


    class MyView(discord.ui.View):
        def __init__(self) -> None:
            super().__init__(timeout=None)

        @discord.ui.button(label="Click me!", custom_id="my-view:click-me")
        async def click_me(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message("Hello there!", ephemeral=True)


    client = discord.Client(intents=discord.Intents.default())


    @client.event
    async def on_message(message: discord.Message):
        # Invoke with "@mention !view" in a guild, or "!view" if you're DMing the bot.
        # Restart your bot afterwards and see if the view still works.
        if message.content.endswith("!view"):
            await message.channel.send("Hello world!", view=MyView())


    @client.event
    async def setup_hook():
        # On startup, tell discord.py to handle interactions from any
        # message that uses the same custom IDs as MyView
        client.add_view(MyView())


    client.run("TOKEN")

.. code-block:: python
    :caption: stateful.py

    import contextlib
    import sqlite3

    import discord

    SQL_SCHEMA = """
    CREATE TABLE IF NOT EXISTS counter_view (
        message_id INTEGER PRIMARY KEY,
        current_count INTEGER
    );
    """


    @contextlib.contextmanager
    def open_database():
        # This example involves a view that has a count attribute,
        # and we want to restore that count every time the bot restarts.
        # Our database will keep track of each view's message ID and count
        # inside a table.
        conn = sqlite3.connect("stateful.db")
        conn.executescript(SQL_SCHEMA)
        try:
            yield conn
        finally:
            conn.close()


    class CounterView(discord.ui.View):
        def __init__(self, client: "MyClient", count: int) -> None:
            super().__init__(timeout=None)
            self.client = client
            self.count = count

        @discord.ui.button(label="Increment", custom_id="counter:increment")
        async def increment(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.count += 1
            self.client.set_counter_view(interaction.message.id, self.count)

            await interaction.response.send_message(
                f"You have incremented this message's count to {self.count:,}!",
                ephemeral=True,
            )

            # Technically this could be a stateless view if we retrieved
            # the count from the database each time the button was clicked.
            # For demonstrative purposes, this example stores the count as
            # an attribute of the view.


    class MyClient(discord.Client):
        def __init__(self):
            super().__init__(intents=discord.Intents.default())

        async def setup_hook(self):
            # During startup, let's tell discord.py about every view that we've
            # ever sent in our database so the library knows the correct count
            # for each message.
            with open_database() as conn:
                c = conn.execute("SELECT message_id, current_count FROM counter_view")
                for message_id, current_count in c.fetchall():
                    self.add_view(
                        CounterView(self, count=current_count),
                        message_id=message_id,
                    )

        async def on_message(self, message: discord.Message):
            # Invoke with "@mention !view" in a guild, or "!view" if you're DMing the bot.
            # Restart your bot afterwards and see if the view remembers the same count,
            # and also try it with multiple messages to see how their states differ.
            if message.content.endswith("!view"):
                sent = await message.channel.send("Hello world!", view=CounterView(self, count=0))
                self.set_counter_view(sent.id, count=0)

        def set_counter_view(self, message_id: int, count: int):
            with open_database() as conn:
                conn.execute(
                    # https://sqlite.org/lang_upsert.html
                    """
                    INSERT INTO counter_view (message_id, current_count) VALUES (?, ?)
                    ON CONFLICT DO UPDATE SET current_count = excluded.current_count
                    """,
                    (message_id, count),
                )
                conn.commit()


    client = MyClient()
    client.run("TOKEN")

.. rubric:: Footnotes

Original guide: https://gist.github.com/thegamecracks/0f9ab7ad3982e65ff4aa429acb39cc4e
