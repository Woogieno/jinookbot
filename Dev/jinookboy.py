import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
from dotenv import load_dotenv
from discord import app_commands

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

queue = []
now_playing = None
repeat = False

class MusicView(discord.ui.View):
    def __init__(self, vc):
        super().__init__(timeout=None)
        self.vc = vc

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.vc.is_playing():
            self.vc.stop()
            await interaction.response.send_message("⏹ 음악이 정지되었습니다.", ephemeral=True)
        else:
            await interaction.response.send_message("재생 중인 음악이 없습니다.", ephemeral=True)

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.primary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.vc.is_playing():
            self.vc.stop()
            await interaction.response.send_message("⏭ 다음 곡으로 스킵합니다.", ephemeral=True)
        else:
            await interaction.response.send_message("재생 중인 음악이 없습니다.", ephemeral=True)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary)
    async def repeat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        global repeat
        repeat = not repeat
        await interaction.response.send_message(f"🔁 반복 {'활성화' if repeat else '비활성화'}", ephemeral=True)

@bot.event
async def on_ready():
    print(f"봇 로그인: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"슬래시 커맨드 {len(synced)}개 동기화됨")
    except Exception as e:
        print(e)

async def play_next(ctx, vc):
    global now_playing
    if repeat and now_playing:
        queue.insert(0, now_playing)
    if queue:
        now_playing = queue.pop(0)
        await play_song(ctx, vc, now_playing)
    else:
        now_playing = None

        # 5분 대기: 사람이 없거나, 곡이 추가되지 않으면 퇴장
        def is_someone_in_channel():
            return vc.channel and len([m for m in vc.channel.members if not m.bot]) > 0  # 봇 제외

        for _ in range(30):  # 30초 동안 1초마다 체크
            await asyncio.sleep(1)
            if queue:
                return await play_next(ctx, vc)  # 곡이 추가되면 바로 재생
            if not is_someone_in_channel():
                await ctx.send("아무도 없어 봇이 음성 채널에서 퇴장합니다.")
                await vc.disconnect()
                return
        # 30초가 지나도 아무도 없고, 곡도 없으면 퇴장
        await ctx.send("30초 동안 아무도 없거나, 노래가 추가되지 않아 봇이 음성 채널에서 퇴장합니다.")
        await vc.disconnect()

async def play_song(ctx, vc, song):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'default_search': 'ytsearch',
        'noplaylist': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(song, download=False)
        if 'entries' in info:
            info = info['entries'][0]
        url2 = info['url']
        title = info.get('title', '알 수 없음')
        uploader = info.get('uploader', '알 수 없음')
        webpage_url = info.get('webpage_url', song)
        thumbnail = info.get('thumbnail', None)

    source = await discord.FFmpegOpusAudio.from_probe(url2)
    vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx, vc), bot.loop))

    voice_channel_name = ctx.author.voice.channel.name if ctx.author.voice and ctx.author.voice.channel else "음성채널"
    embed = discord.Embed(
        title=f"🇰🇷{voice_channel_name}🇰🇷 | 음악 재생중...",
        description=f"[{title}]({webpage_url})",
        color=discord.Color.blue()
    )
    embed.add_field(name="가수", value=uploader, inline=True)
    embed.add_field(name="대기중인 곡", value=str(len(queue)), inline=True)
    embed.add_field(name="반복", value="반복중" if repeat else "반복없음", inline=True)
    embed.add_field(name="요청자", value=ctx.author.mention, inline=True)
    embed.add_field(name="서버명", value=ctx.guild.name, inline=True)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    await ctx.send(embed=embed, view=MusicView(vc))

@bot.command(name="play", help="유튜브에서 음악을 검색/재생합니다.")
async def play(ctx, *, search: str):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("음성 채널에 먼저 접속해 주세요.")
    channel = ctx.author.voice.channel
    vc = ctx.voice_client or await channel.connect()
    queue.append(search)
    if not vc.is_playing():
        await play_next(ctx, vc)
    else:
        await ctx.send("대기열에 추가되었습니다.")

@bot.command(name="skip", help="다음 곡으로 스킵합니다.")
async def skip(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send("재생중인 음악이 없습니다.")
    vc.stop()
    await ctx.send("⏭ 다음 곡으로 스킵합니다.")

@bot.command(name="stop", help="음악을 정지하고 나갑니다.")
async def stop(ctx):
    vc = ctx.voice_client
    if not vc:
        return await ctx.send("재생중인 음악이 없습니다.")
    await vc.disconnect()
    await ctx.send("⏹ 음악이 정지되었습니다.")

@bot.command(name="queue", help="대기열을 확인합니다.")
async def queue_cmd(ctx):
    if not queue:
        return await ctx.send("대기열이 비어 있습니다.")
    queue_list = "\n".join([f"{idx+1}. {q}" for idx, q in enumerate(queue)])
    await ctx.send(f"**대기열:**\n{queue_list}")

@bot.command(name="repeat", help="반복 재생을 토글합니다.")
async def repeat_cmd(ctx):
    global repeat
    repeat = not repeat
    await ctx.send(f"🔁 반복 {'활성화' if repeat else '비활성화'}")

@bot.tree.command(name="play", description="유튜브에서 음악을 검색/재생합니다.")
@app_commands.describe(search="검색어 또는 유튜브 URL")
async def play_slash(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    await play(ctx, search=search)
    await interaction.followup.send("음악 재생 명령이 실행되었습니다.")

@bot.tree.command(name="skip", description="다음 곡으로 스킵합니다.")
async def skip_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    await skip(ctx)
    await interaction.followup.send("스킵 명령이 실행되었습니다.")

@bot.tree.command(name="stop", description="음악을 정지하고 나갑니다.")
async def stop_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    await stop(ctx)
    await interaction.followup.send("정지 명령이 실행되었습니다.")

@bot.tree.command(name="queue", description="대기열을 확인합니다.")
async def queue_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    await queue_cmd(ctx)
    await interaction.followup.send("대기열 확인 명령이 실행되었습니다.")

@bot.tree.command(name="repeat", description="반복 재생을 토글합니다.")
async def repeat_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    await repeat_cmd(ctx)
    await interaction.followup.send("반복 토글 명령이 실행되었습니다.")

bot.run(TOKEN)