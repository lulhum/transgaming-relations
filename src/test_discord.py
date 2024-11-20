import discord
import asyncio

class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        # A CommandTree is a special type that holds all the application command
        # state required to make it work. This is a separate class because it
        # allows all the extra state to be opt-in.
        # Whenever you want to work with application commands, your tree is used
        # to store and work with them.
        # Note: When using commands.Bot instead of discord.Client, the bot will
        # maintain its own tree instead.
        self.tree = discord.app_commands.CommandTree(self)
        
    async def on_ready(self):
        print(f'Logged on as {self.user}!')
        for guild in self.guilds:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(guild.id)


print(discord.__version__)
intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)

@client.tree.command()
async def test(interaction: discord.Interaction):
    await interaction.response.send_message('I\'ll be working on this !')

client.run('token')
