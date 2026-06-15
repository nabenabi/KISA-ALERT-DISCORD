import os
import json
import feedparser
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
KISA_RSS_URL = os.getenv("KISA_RSS_URL")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

SEEN_FILE = "seen_kisa.json"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()

    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-500:], f, ensure_ascii=False, indent=2)


def get_ntt_id(link: str) -> str:
    try:
        query = parse_qs(urlparse(link).query)
        return query.get("nttId", [link])[0]
    except Exception:
        return link


@tasks.loop(minutes=10)
async def check_kisa_rss():
    if not KISA_RSS_URL:
        print("KISA_RSS_URL이 없습니다.")
        return

    channel = bot.get_channel(DISCORD_CHANNEL_ID)

    if channel is None:
        print("Discord 채널을 찾을 수 없습니다.")
        return

    feed = feedparser.parse(KISA_RSS_URL)
    entries = feed.entries

    seen = load_seen()

    # 첫 실행 도배 방지
    if not os.path.exists(SEEN_FILE):
        initial_seen = {get_ntt_id(entry.link) for entry in entries if hasattr(entry, "link")}
        save_seen(initial_seen)
        print("초기 실행: 기존 KISA 공지는 저장만 하고 전송하지 않음")
        return

    new_entries = []

    for entry in entries:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", "제목 없음")
        published = getattr(entry, "published", "게시일 확인 불가")

        if not link:
            continue

        ntt_id = get_ntt_id(link)

        if ntt_id not in seen:
            new_entries.append((ntt_id, title, link, published))

    if not new_entries:
        print("새 KISA 보안공지 없음")
        return

    # 오래된 것부터 전송
    for ntt_id, title, link, published in reversed(new_entries):
        embed = discord.Embed(
            title=title,
            url=link,
            description="KISA 보호나라 보안공지에 새 글이 등록되었습니다.",
            color=0xE74C3C,
        )
        embed.add_field(name="게시일", value=published, inline=True)
        embed.add_field(name="출처", value="KISA 보호나라", inline=True)

        await channel.send(embed=embed)
        seen.add(ntt_id)

        print(f"KISA 보안공지 전송 완료: {title}")

    save_seen(seen)


@bot.tree.command(name="초기설정", description="KISA 최신 보안공지 10개를 전송하고 초기 seen 목록을 설정합니다.")
@app_commands.checks.has_permissions(administrator=True)
async def initial_setup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not KISA_RSS_URL:
        await interaction.followup.send("KISA_RSS_URL이 설정되어 있지 않습니다.", ephemeral=True)
        return

    feed = feedparser.parse(KISA_RSS_URL)
    entries = feed.entries[:10]

    if not entries:
        await interaction.followup.send("RSS에서 공지를 찾지 못했습니다.", ephemeral=True)
        return

    seen = load_seen()

    for entry in reversed(entries):
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", "제목 없음")
        published = getattr(entry, "published", "게시일 확인 불가")

        if not link:
            continue

        ntt_id = get_ntt_id(link)

        embed = discord.Embed(
            title=title,
            url=link,
            description="KISA 보호나라 보안공지입니다.",
            color=0xE74C3C,
        )
        embed.add_field(name="게시일", value=published, inline=True)
        embed.add_field(name="출처", value="KISA 보호나라", inline=True)

        await interaction.channel.send(embed=embed)
        seen.add(ntt_id)

    save_seen(seen)

    await interaction.followup.send("초기설정 완료: 최신 보안공지 10개를 전송하고 seen 목록에 저장했습니다.", ephemeral=True)


@initial_setup.error
async def initial_setup_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("관리자 권한이 있는 사람만 사용할 수 있습니다.", ephemeral=True)
    else:
        await interaction.response.send_message(f"오류 발생: {error}", ephemeral=True)

@bot.event
async def on_ready():
    print(f"로그인 완료: {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"슬래시 명령어 동기화 완료: {len(synced)}개")
    except Exception as e:
        print(f"슬래시 명령어 동기화 실패: {e}")

    if not check_kisa_rss.is_running():
        check_kisa_rss.start()


bot.run(TOKEN)