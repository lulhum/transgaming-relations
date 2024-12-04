import discord
import asyncio
import os
import datetime
import matplotlib.pyplot as plt
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from pathlib import Path
from dotenv import load_dotenv
from nlp import nlp

class MessageMap(object):
    def __init__(self, role):
        self.createdAt = datetime.datetime.now()
        self.since = self.createdAt - datetime.timedelta(days=30)
        self.role = role
        self.members = set(role.members)
        self.guild = role.guild
        self.mmap = {m.id: {
            'member': m,
            'messages': {m.id: [] for m in self.members}
        } for m in self.members}
        self.task = None
        self.filename = None

    async def resolve(self):
        if self.task is None:
            self.task = asyncio.create_task(self.map())
        await self.task
        if self.filename is None:
            self.filename = asyncio.create_task(self.renderMap())
        return await self.filename

    async def renderMap(self):
        labels = [entry['member'].display_name[:10] for entry in self.mmap.values()]
        data = [
            [0 if not len(m) else sum(m) / len(m) for m in entry['messages'].values()]
            for entry in self.mmap.values()
        ]
        fig = plt.figure()
        plt.subplots_adjust(top=0.8, left=0.15)
        ax = fig.add_subplot(111)
        matrix = ax.matshow(data)
        fig.colorbar(matrix)
        plt.xticks(range(len(labels)), labels, rotation='vertical')
        plt.yticks(range(len(labels)), labels)
        Path('var/maps').mkdir(parents=True, exist_ok=True)
        filename = 'var/maps/{}.png'.format(datetime.datetime.now().isoformat())
        plt.savefig(filename)
        self.mmap = None
        return filename

    def addToMap(self, author, target, score):
        self.mmap[author.id]['messages'][target.id].append(score)

    async def getTargets(self, message, previous):
        if message.reference is not None:
            if message.reference.cached_message is not None:
                if message.reference.cached_message.author in self.members:
                    yield message.reference.cached_message.author
            elif message.reference.message_id is not None:
                channel = self.guild.get_channel(message.reference.channel_id)
                msg = await channel.fetch_message(message.reference.message_id)
                if msg.author in self.members:
                    yield msg.author
        elif previous and previous.author in self.members and previous.author != message.author:
            yield previous.author            
        for member in message.mentions:
            if member in self.members:
                yield member

    def scoreMessage(self, message):
        score = nlp(message.content)
        if score[0]['label'] == 'POSITIVE':
            return score[0]['score']
        return -score[0]['score']

    async def map(self):
        for channel in self.guild.text_channels:
            await self.mapChannel(channel)

    async def mapChannel(self, channel):
        previous = None
        async for message in channel.history(after=self.since, limit=None):
            await self.mapMessage(message, previous)
            previous = message

    async def mapMessage(self, message, previous):
        author = message.author
        if author not in self.members:
            return
        score = None
        targets = set()
        async for target in self.getTargets(message, previous):
            if target == author:
                continue
            if target.id in targets:
                continue
            targets.add(target.id)
            if score is None:
                score = self.scoreMessage(message)
            self.addToMap(author, target, score)
            print('Message from {} to {} ({})'.format(author.name, target.name, score))

class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)

    async def on_guild_join(self, guild):
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print('joined {}'.format(guild.name))
        
    async def on_ready(self):
        print(f'Logged on as {self.user}!')
        for guild in self.guilds:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print('installed on {}'.format(guild.name))


print(discord.__version__)
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

client = MyClient(intents=intents)
maps = {}

@client.tree.command(name='map')
@discord.app_commands.describe(role='The role to map')
async def mapRole(interaction: discord.Interaction, role: discord.Role):
    await interaction.response.send_message(
        'Mapping du role {} en cours...'.format(role.name)
    )
    if role.id not in maps:
        maps[role.id] = MessageMap(role)
    if maps[role.id].createdAt < datetime.datetime.now() - datetime.timedelta(days=7):
        maps[role.id] = MessageMap(role)
    filename = await maps[role.id].resolve()
    await interaction.channel.send(file=discord.File(filename))

load_dotenv()
client.run(os.getenv('DISCORD_TOKEN'))
