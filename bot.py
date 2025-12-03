# bot.py
import os
import asyncio
import datetime
import certifi

# certifi에서 제공하는 CA 인증서를 전역 SSL 기본값으로 설정
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# 타임존 (Python 3.9+)
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # 없으면 로컬 시간 기준으로 처리

import discord
from discord.ext import commands, tasks

# 1. 디스코드 Intents 설정 (메시지 내용 읽기 허용)
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 2. 인증 채널 ID (디스코드에서 복사한 숫자로 바꾸기)
VERIFY_CHANNEL_ID =   # 여기에 실제 채널 ID 넣기

# 3. 이번 주 문제 카운트 저장용 (메모리용)
# {user_id: count}
weekly_counts = {}


# ----------------------------------------
# A. 이번 주 채팅 로그를 읽어서 카운트 복원
# ----------------------------------------
async def rebuild_weekly_counts_from_history():
    """이번 주 인증 채널 메시지 기준으로 weekly_counts 다시 계산"""
    global weekly_counts
    weekly_counts = {}

    channel = bot.get_channel(VERIFY_CHANNEL_ID)
    if channel is None:
        print("VERIFY_CHANNEL_ID 채널을 찾을 수 없습니다.")
        return

    # 한국 시간 기준으로 이번 주 월요일 00:00 구하기
    if ZoneInfo is not None:
        tz = ZoneInfo("Asia/Seoul")
        now = datetime.datetime.now(tz)
    else:
        tz = None
        now = datetime.datetime.now()

    # 월=0, ..., 일=6 → 이번 주 월요일 00:00
    days_since_monday = now.weekday()
    week_start = (now - datetime.timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    print(f"Rebuilding weekly_counts from messages after {week_start} ...")

    # week_start 이후의 메시지 중, !solve 로 시작하는 것만 카운트
    async for message in channel.history(after=week_start, limit=None, oldest_first=True):
        # 봇이 보낸 건 무시
        if message.author.bot:
            continue

        content = message.content.strip()
        if content.startswith("!solve "):
            user_id = message.author.id
            weekly_counts[user_id] = weekly_counts.get(user_id, 0) + 1

    print("Rebuild done. weekly_counts =", weekly_counts)


# ----------------------------------------
# B. 봇 준비 & 자동 리셋 태스크
# ----------------------------------------
@bot.event
async def on_ready():
    # 1) 봇이 켜질 때마다 이번 주 채팅 로그 기준으로 카운트 복원
    await rebuild_weekly_counts_from_history()

    print(f"Logged in as {bot.user}")
    if not weekly_auto_reset.is_running():
        weekly_auto_reset.start()
        print("weekly_auto_reset task started")

    if not weekly_auto_settle.is_running():
        weekly_auto_settle.start()
        print("weekly_auto_settle task started")

@tasks.loop(hours=168)  # 1주일 간격
async def weekly_auto_settle():
    """매주 한 번 자동으로 정산"""
    channel = bot.get_channel(VERIFY_CHANNEL_ID)
    if channel is None:
        print("VERIFY_CHANNEL_ID 채널을 찾을 수 없어 자동 정산을 건너뜁니다.")
        return

    guild = channel.guild
    # 자동 정산은 멤버를 멘션으로 표시
    await do_settle_for_guild(guild, channel, mention_members=True)


@weekly_auto_settle.before_loop
async def before_weekly_auto_settle():
    """첫 실행 시점: 한국 시간 기준 일요일 23:50에 맞추기"""
    await bot.wait_until_ready()

    if ZoneInfo is not None:
        tz = ZoneInfo("Asia/Seoul")
        now = datetime.datetime.now(tz)
    else:
        tz = None
        now = datetime.datetime.now()

    # 월=0, ..., 일=6 → 일요일 = 6
    days_until_sunday = (6 - now.weekday()) % 7
    next_run = (now + datetime.timedelta(days=days_until_sunday)).replace(
        hour=23, minute=50, second=0, microsecond=0
    )

    # 이미 이번 주 일요일 23:50이 지났다면 다음 주
    if next_run <= now:
        next_run += datetime.timedelta(days=7)

    wait_seconds = (next_run - now).total_seconds()
    print(f"weekly_auto_settle will start at {next_run} (wait {wait_seconds} seconds)")
    await asyncio.sleep(wait_seconds)

@tasks.loop(hours=168)  # 168시간 = 7일 간격 (1주일)
async def weekly_auto_reset():
    """매주 한 번 weekly_counts 자동 초기화"""
    global weekly_counts
    weekly_counts = {}

    channel = bot.get_channel(VERIFY_CHANNEL_ID)
    if channel:
        await channel.send("이번 주 기록을 자동으로 초기화했습니다. 새 주 시작!")


@weekly_auto_reset.before_loop
async def before_weekly_auto_reset():
    """첫 실행 시점: 한국 시간 기준 일요일 23:59에 맞추기"""
    await bot.wait_until_ready()

    if ZoneInfo is not None:
        tz = ZoneInfo("Asia/Seoul")
        now = datetime.datetime.now(tz)
    else:
        tz = None
        now = datetime.datetime.now()

    # 월=0, ..., 일=6 → 일요일 = 6
    days_until_sunday = (6 - now.weekday()) % 7
    next_run = (now + datetime.timedelta(days=days_until_sunday)).replace(
        hour=23, minute=59, second=0, microsecond=0
    )

    # 이미 이번 주 일요일 23:59가 지났다면 다음 주
    if next_run <= now:
        next_run += datetime.timedelta(days=7)

    wait_seconds = (next_run - now).total_seconds()
    print(f"weekly_auto_reset will start at {next_run} (wait {wait_seconds} seconds)")
    await asyncio.sleep(wait_seconds)


# ----------------------------------------
# C. 명령어: !solve (인증)
# ----------------------------------------
@bot.command(name="solve")
async def solve(ctx: commands.Context, *, url: str):
    """
    사용 예시:
    !solve https://www.acmicpc.net/problem/1000
    """

    # 1) 인증 채널에서만 받기
    if ctx.channel.id != VERIFY_CHANNEL_ID:
        await ctx.send("이 명령어는 인증 채널에서만 사용할 수 있습니다.")
        return

    # 2) URL 검증
    if not url.startswith("http"):
        await ctx.send("URL 형식이 올바르지 않습니다. 예: !solve https://www.acmicpc.net/problem/1000")
        return

    # 필요하면 백준 전용으로 제한:
    # if "acmicpc.net" not in url and "boj.kr" not in url:
    #     await ctx.send("백준 문제 링크만 인증 가능합니다.")
    #     return

    user_id = ctx.author.id
    weekly_counts[user_id] = weekly_counts.get(user_id, 0) + 1

    await ctx.send(
        f"{ctx.author.display_name}님, 인증 완료!\n"
        f"이번 주 누적: {weekly_counts[user_id]}회"
    )


# ----------------------------------------
# D. 명령어: !week (이번 주 현황)
# ----------------------------------------
@bot.command(name="week")
async def week(ctx: commands.Context):
    # 서버 전체 멤버 중 봇 제외
    members = [m for m in ctx.guild.members if not m.bot]

    if not members:
        await ctx.send("이 서버에 봇을 제외한 멤버가 없습니다.")
        return

    lines = ["이번 주 문제 풀이 현황 (서버 기준):"]

    for member in members:
        count = weekly_counts.get(member.id, 0)
        lines.append(f"- {member.display_name}: {count}회")

    await ctx.send("\n".join(lines))
# ----------------------------------------
# E. 명령어: !settle (정산)
# ----------------------------------------
async def do_settle_for_guild(guild: discord.Guild, channel: discord.TextChannel, mention_members: bool):
    """서버(guild) 기준으로 정산 로직 수행하고 channel에 결과 메시지 전송"""
    # 서버 멤버 기준 (봇 제외)
    members = [m for m in guild.members if not m.bot]

    if not members:
        await channel.send("이 서버에 정산 대상 멤버(봇 제외)가 없습니다.")
        return

    target = 5               # 주당 목표 문제 수
    penalty_per_miss = 1000  # 1회 미인증당 벌금

    payers = []     # [(member_obj, amount, count), ...]
    receivers = []  # [member_obj, ...]
    total_penalty = 0

    for member in members:
        count = weekly_counts.get(member.id, 0)

        if count >= target:
            receivers.append(member)
        else:
            miss = target - count
            amount = miss * penalty_per_miss
            if miss > 0:
                total_penalty += amount
                payers.append((member, amount, count))

    if total_penalty == 0:
        await channel.send("이번 주에는 벌금이 없습니다. 모두 수고하셨습니다!")
        return

    if not receivers:
        await channel.send(
            f"기준 이상 인증자가 없어 벌금 분배 대상이 없습니다.\n"
            f"총 벌금: {total_penalty}원"
        )
        return

    per_person = total_penalty // len(receivers)

    def fmt_member(m: discord.Member) -> str:
        return m.mention if mention_members else m.display_name

    lines = []
    lines.append("이번 주 정산 결과:")
    lines.append("")
    lines.append(f"- 기준 문제 수: 주당 {target}회")
    lines.append(f"- 1회 미달 벌금: {penalty_per_miss}원")
    lines.append(f"- 총 벌금: {total_penalty}원")
    lines.append("")

    if payers:
        lines.append("벌금 내야 하는 사람 (서버 기준):")
        for member, amount, count in payers:
            lines.append(f"  • {fmt_member(member)}: {count}회 인증 → {amount}원")
    else:
        lines.append("벌금 내야 하는 사람: 없음")

    lines.append("")
    lines.append("기준 이상 인증 완료한 사람:")
    for member in receivers:
        lines.append(f"  • {fmt_member(member)}")

    lines.append("")
    lines.append(f"1인당 받을 금액: {per_person}원")

    await channel.send("\n".join(lines))

@bot.command(name="settle")
@commands.has_permissions(administrator=True)
async def settle(ctx: commands.Context):
    channel = bot.get_channel(VERIFY_CHANNEL_ID)
    if channel is None:
        await ctx.send("인증 채널을 찾을 수 없습니다. VERIFY_CHANNEL_ID를 확인해주세요.")
        return

    # 수동 settle은 멤버 이름만 쓰고 싶다면 mention_members=False
    await do_settle_for_guild(ctx.guild, channel, mention_members=False)

# ----------------------------------------
# F. 명령어: !resetweek (수동 초기화)
# ----------------------------------------
@bot.command(name="resetweek")
@commands.has_permissions(administrator=True)
async def reset_week(ctx: commands.Context):
    global weekly_counts
    weekly_counts = {}
    await ctx.send("이번 주 기록을 초기화했습니다.")


@bot.command(name="members")
async def members(ctx: commands.Context):
    # 서버 전체 멤버 리스트 (봇 제외)
    members = [m for m in ctx.guild.members if not m.bot]

    if not members:
        await ctx.send("이 서버에 봇을 제외한 멤버가 없습니다.")
        return

    lines = ["📋 서버 전체 멤버 목록 (봇 제외):"]

    # 알파벳순 정렬(원하면 제거 가능)
    members = sorted(members, key=lambda m: m.display_name.lower())

    for member in members:
        lines.append(f"- {member.display_name}")

    # discord 메시지 최대 길이 제한 방지
    # 너무 길 경우 여러 메시지로 나눠서 전송
    chunk = []
    for line in lines:
        chunk.append(line)
        if sum(len(s) for s in chunk) > 1900:
            await ctx.send("\n".join(chunk))
            chunk = []
    if chunk:
        await ctx.send("\n".join(chunk))
# 6. 봇 실행
TOKEN = ""
bot.run(TOKEN)
