import discord
import asyncio
import os
import datetime
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib as mpl
from pathlib import Path
from dotenv import load_dotenv
import nlp
import math
from enum import Enum
from typing import Optional, Literal

Colormap = Enum('Colormap', ((c, i) for i, c in enumerate(list(mpl.colormaps))))

async def periodic(period, cb):
    while True:
        await cb()
        await asyncio.sleep(period)

class MessageMap(object):
    def __init__(self, role, client, since=7, channel=None):
        self.channel = channel
        self.client = client
        self.createdAt = datetime.datetime.now()
        self.since = self.createdAt - datetime.timedelta(days=since)
        self.role = role
        self.members = [m for m in role.members if m.id != self.client.user.id]
        self.mids = set(m.id for m in self.members)
        self.guild = role.guild
        self.mmap = {m.id: {
            'member': m,
            'messages': {m.id: {'count': 0, 'sum': 0} for m in self.members}
        } for m in self.members}
        self.task = None
        self.files = {}

    async def resolve(self):
        if self.task is None:
            self.task = asyncio.create_task(self.map())
        await self.task
        return self

    async def getGraph(self, min_count):
        filename = '{}.{}.graph.png'.format(self.createdAt.isoformat(), min_count)
        if filename not in self.files:
            self.files[filename] = asyncio.create_task(self.renderGraph(filename, min_count))
        return await self.files[filename]

    async def getMatrix(self, metric, cmap):
        filename = '{}.{}.{}.matrix.png'.format(self.createdAt.isoformat(), cmap, metric)
        if filename not in self.files:
            self.files[filename] = asyncio.create_task(self.renderMatrix(filename, metric, cmap))
        return await self.files[filename]

    async def renderGraph(self, filename, min_count):
        graph = nx.DiGraph()
        mmax = 0
        for mid, entry in self.mmap.items():
            label = entry['member'].display_name
            weight = sum(m['count'] for m in entry['messages'].values())
            if abs(weight) > mmax:
                mmax = abs(weight)
            graph.add_node(mid, label=label, weight=weight)
            for tid, m in entry['messages'].items():
                if m['count'] >= min_count:
                    graph.add_edge(mid, tid, count=m['count'], sum=m['sum'])
        plt.figure(figsize=(len(self.mmap) * 2, len(self.mmap) * 2))
        pos = nx.circular_layout(graph)
        nx.draw_networkx_nodes(
            graph,
            pos,
            cmap=Colormap.Wistia.name,
            node_color=[node[1]['weight'] for node in graph.nodes(data=True)],
            vmax=mmax,
            vmin=0,
            node_size=5000
        )
        nx.draw_networkx_edges(
            graph,
            pos,
            connectionstyle=['arc3,rad=0.15', 'arc3,rad=0.30'],
            edge_cmap=mpl.colormaps['coolwarm'],
            edge_color=[self.mean(edge[2]) for edge in graph.edges(data=True)],
            node_size=5000,
            edge_vmax=1,
            edge_vmin=-1,
            width=[math.log2(max(1, edge[2]['count'])) for edge in graph.edges(data=True)]
        )
        nx.draw_networkx_labels(
            graph,
            pos,
            labels={node[0]: node[1]['label'][:10] for node in graph.nodes(data=True)}
        )
        Path('var/maps').mkdir(parents=True, exist_ok=True)        
        filename = 'var/maps/{}'.format(filename)
        plt.savefig(filename)
        return filename

    def sum(self, m):
        return m['sum']

    def count(self, m):
        return m['count']

    def mean(self, m):
        if m['count'] == 0:
            return 0
        return m['sum'] / m['count']

    def logsum(self, m):
        if m['sum'] == 0:
            return 0
        if m['sum'] > 0:
            return math.log(m['sum'] + 1)
        return -math.log(abs(m['sum']) + 1)

    def logcount(self, m):
        if m['count'] == 0:
            return 0
        return math.log(m['count'] + 1)

    async def renderMatrix(self, filename, metric, cmap):
        labels = [entry['member'].display_name[:10] for entry in self.mmap.values()]
        data = [
            [getattr(self, metric)(m) for m in entry['messages'].values()]
            for entry in self.mmap.values()
        ]
        if metric == 'count' or metric == 'logcount':
            if cmap is None:
                cmap = Colormap.YlGnBu
            vmax = max(max(row) for row in data)
            vmin = 0
        else:
            if cmap is None:
                cmap = Colormap.seismic
            if metric == 'mean':
                vmax = 1
                vmin = -1
            else:
                vmax = max(max(abs(d) for d in row) for row in data)
                vmin = -vmax
        fig = plt.figure()
        plt.subplots_adjust(top=0.8, left=0.15)
        ax = fig.add_subplot(111)
        matrix = ax.matshow(data, vmax=vmax, vmin=vmin, cmap=cmap.name)
        fig.colorbar(matrix)
        plt.xticks(range(len(labels)), labels, rotation='vertical')
        plt.yticks(range(len(labels)), labels)
        Path('var/maps').mkdir(parents=True, exist_ok=True)
        filename = 'var/maps/{}'.format(filename)
        plt.savefig(filename)
        return filename

    def addToMap(self, author, target, score):
        self.mmap[author.id]['messages'][target.id]['count'] += 1
        self.mmap[author.id]['messages'][target.id]['sum'] += score

    async def getTargets(self, message, previous):
        if message.reference is not None:
            if message.reference.cached_message is not None:
                if message.reference.cached_message.author.id in self.mids:
                    yield message.reference.cached_message.author
            elif message.reference.message_id is not None:
                channel = self.guild.get_channel(message.reference.channel_id)
                msg = await channel.fetch_message(message.reference.message_id)
                if msg.author.id in self.mids:
                    yield msg.author
        elif previous and previous.author.id in self.mids and previous.author.id != message.author.id:
            yield previous.author            
        for member in message.mentions:
            if member.id in self.mids:
                yield member

    def scoreMessage(self, message):
        try:
            return nlp.score(message.content)
        except:
            return 0

    async def map(self):
        if self.channel is not None:
            await self.mapChannel(self.channel)
            return
        for channel in self.guild.text_channels:
            try:
                await self.mapChannel(channel)
            except:
                pass

    async def mapChannel(self, channel):
        print('Mapping Channel {}'.format(channel.name))
        previous = None
        async for message in channel.history(after=self.since, limit=None):
            await self.mapMessage(message, previous)
            if previous is None or previous.author != message.author:
                previous = message

    async def mapMessage(self, message, previous):
        author = message.author
        if author.id not in self.mids:
            return
        score = None
        targets = set()
        async for target in self.getTargets(message, previous):
            if target.id == author.id:
                continue
            if target.id in targets:
                continue
            targets.add(target.id)
            if score is None:
                score = self.scoreMessage(message)
            self.addToMap(author, target, score)
            print('Message from {} to {} ({}) - {}'.format(
                author.name,
                target.name,
                score,
                message.content[:80]
            ))

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

async def getMap(role, since, channel, clear_cache=False):
    key = '{}@{}@{}'.format(role.id, since, channel.id if channel else '*')
    if key not in maps or clear_cache:
        maps[key] = MessageMap(role, client, since, channel)
    return await maps[key].resolve()

def isMapCached(role, since):
    return '{}@{}'.format(role, since) in maps


@client.tree.command(name='matrix')
@discord.app_commands.describe(role='Le rôle cartographié',
                               since='Nombre de jour maximum à remonter dans l\'historique',
                               channel='Canal spécifique',
                               metric='Valeur à mesurer',
                               cmap='Échelle de couleurs')
async def matrix(interaction: discord.Interaction,
                 role: discord.Role,
                 since: Optional[discord.app_commands.Range[int, 1, 360]] = 7,
                 metric: Optional[Literal['sum', 'count', 'mean', 'logsum', 'logcount']] = 'sum',
                 channel: Optional[discord.TextChannel] = None,
                 cmap: Optional[str] = None):
    if cmap is not None:
        if cmap not in (c.name for c in Colormap):
            await interaction.response.send_message('Échelle de couleurs inconnue: {}. Voir https://matplotlib.org/stable/users/explain/colors/colormaps.html'.format(cmap))
            return
        cmap = Colormap[cmap]
    await interaction.response.send_message(
        'Génération de la matrice {} du role {}'.format(metric, role.name)
    )
    messageMap = await getMap(role, since, channel)
    filename = await messageMap.getMatrix(metric, cmap)
    await interaction.channel.send(file=discord.File(filename))
@client.tree.command(name='graph')
@discord.app_commands.describe(role='Le rôle cartographié',
                               since='Nombre de jour maximum à remonter dans l\'historique',
                               channel='Canal spécifique',
                               min_count='Nombre minimal de messages pour afficher le lien')
async def graph(interaction: discord.Interaction,
                role: discord.Role,
                since: Optional[discord.app_commands.Range[int, 1, 360]] = 7,
                channel: Optional[discord.TextChannel] = None,
                min_count: Optional[int] = 10):
    await interaction.response.send_message(
        'Génération du graphe du role {}'.format(role.name)
    )
    messageMap = await getMap(role, since, channel)
    filename = await messageMap.getGraph(min_count)
    await interaction.channel.send(file=discord.File(filename))

def send_message_cb(channel, msg):
    async def cb():
        await channel.send(msg)
    return cb

cnt = 0

@client.tree.command(name='map')
@discord.app_commands.describe(role='Le rôle cartographié',
                               since='Nombre de jour maximum à remonter dans l\'historique',
                               channel='Canal spécifique',
                               clear_cache='Ne Pas utiliser le cache')
async def mapRole(interaction: discord.Interaction,
                  role: discord.Role,
                  since: Optional[discord.app_commands.Range[int, 1, 360]] = 7,
                  channel: Optional[discord.TextChannel] = None,
                  clear_cache: Optional[bool] = False):
    cnt += 1
    if channel is None:
        msg = 'Mapping #{} du role {} ({} derniers jours) en cours...'.format(cnt, role.name, since)
    else:
        msg = 'Mapping #{} du role {} sur #{} ({} derniers jours) en cours...'.format(
            cnt, role.name, channel.name, since)
    await interaction.response.send_message(msg)
    task = asyncio.create_task(periodic(600, send_message_cb(
        interaction.channel,
        'Mapping #{} du role {} en cours...'.format(cnt, role.name)
    )))
    await getMap(role, since, channel, clear_cache)
    task.cancel()
    await interaction.channel.send('Mapping #{} du role {} terminé'.format(cnt, role.name))

    
load_dotenv()
client.run(os.getenv('DISCORD_TOKEN'))
