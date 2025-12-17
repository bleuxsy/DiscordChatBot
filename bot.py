# bot.py
import os
import datetime
import certifi

# certifi에서 제공하는 CA 인증서를 전역 SSL 기본값으로 설정
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# 타임존 (Python 3.9+)
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

import discord
from discord.ext import commands, tasks
from discord.ext.commands import CommandNotFound

# ------------------------
# 시간대 설정 (Asia/Seoul)
# ------------------------
def get_kst():
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo("Asia/Seoul")
    except Exception:
        return None

KST = get_kst()

def now_kst_or_local():
    if KST:
        return datetime.datetime.now(KST)
    return datetime.datetime.now()

def kst_weekday_name(dt: datetime.datetime) -> str:
    names = ["월", "화", "수", "목", "금", "토", "일"]
    return names[dt.weekday()]

# ------------------------
# 1. 디스코드 Intents 설정
# ------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
)

# ------------------------
# 2. 채널 ID
# ------------------------
VERIFY_CHANNEL_ID =
SETTLE_CHANNEL_ID =

# ------------------------
# 3. 이번 주 카운트 (메모리)
# ------------------------
weekly_counts = {}  # {user_id: count}

# ------------------------
# 로그용: 현황 출력 헬퍼
# ------------------------
def build_weekly_status_lines(guild: discord.Guild) -> list[str]:
    members = [m for m in guild.members if not m.bot]
    members = sorted(members, key=lambda m: m.display_name.lower())
    lines = []
    for m in members:
        lines.append(f"- {m.display_name}: {weekly_counts.get(m.id, 0)}회")
    return lines

def print_status_log(title: str, guild: discord.Guild):
    now = now_kst_or_local()
    day = kst_weekday_name(now)
    print("\n" + "=" * 60)
    print(f"[{title}] {now:%Y-%m-%d %H:%M:%S} ({day})")
    for line in build_weekly_status_lines(guild):
        print("  " + line)
    print("=" * 60 + "\n")

# ----------------------------------------
# CommandNotFound 핸들러
# ----------------------------------------
@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, CommandNotFound):
        if ctx.channel.id == VERIFY_CHANNEL_ID:
            msg = (
                "존재하지 않는 명령어입니다.\n"
                "이 채널에서는 아래 명령어만 사용할 수 있어요:\n"
                "• `!solve <문제 URL>` - 문제 인증\n"
                "예시: `!solve https://www.acmicpc.net/problem/1000`"
            )
        elif ctx.channel.id == SETTLE_CHANNEL_ID:
            msg = (
                "존재하지 않는 명령어입니다.\n"
                "이 채널에서는 아래 명령어들을 사용할 수 있어요:\n"
                "• `!week` - 이번 주 문제 풀이 현황 보기\n"
                "• `!settle` - 이번 주 벌금 정산"
            )
        else:
            msg = (
                "존재하지 않는 명령어입니다.\n"
                "사용 가능한 주요 명령어:\n"
                f"- 인증 채널(<#{VERIFY_CHANNEL_ID}>): `!solve <문제 URL>`\n"
                f"- 정산 채널(<#{SETTLE_CHANNEL_ID}>): `!week`, `!settle`"
            )

        await ctx.send(msg)
        return

    raise error

# ----------------------------------------
# A. 이번 주 채팅 로그를 읽어서 카운트 복원
# ----------------------------------------
async def rebuild_weekly_counts_from_history():
    global weekly_counts
    weekly_counts = {}

    channel = bot.get_channel(VERIFY_CHANNEL_ID)
    if channel is None:
        print("VERIFY_CHANNEL_ID 채널을 찾을 수 없습니다.")
        return

    now = now_kst_or_local()

    # 월=0, ..., 일=6 → 이번 주 월요일 00:00
    days_since_monday = now.weekday()
    week_start = (now - datetime.timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    print(f"[REBUILD] {week_start:%Y-%m-%d %H:%M:%S} 이후 !solve 기록을 다시 읽습니다...")

    async for message in channel.history(after=week_start, limit=None, oldest_first=True):
        if message.author.bot:
            continue

        content = message.content.strip()
        if content.startswith("!solve "):
            user_id = message.author.id
            weekly_counts[user_id] = weekly_counts.get(user_id, 0) + 1

    # user_id dict를 그대로 찍지 말고, 유저이름 현황으로 출력
    print("[REBUILD] 완료. 이번 주 현황:")
    print_status_log("CURRENT STATUS (AFTER REBUILD)", channel.guild)

# ----------------------------------------
# B. 봇 준비 & 자동 태스크 시작
# ----------------------------------------
@bot.event
async def on_ready():
    await rebuild_weekly_counts_from_history()

    print(f"Logged in as {bot.user}")

    if not weekly_auto_reset.is_running():
        weekly_auto_reset.start()
        print("weekly_auto_reset task started")

    if not weekly_auto_settle.is_running():
        weekly_auto_settle.start()
        print("weekly_auto_settle task started")

    if not daily_status_log.is_running():
        daily_status_log.start()
        print("daily_status_log task started")

# ----------------------------------------
# 자동 정산/초기화: 벽시계 시간 고정
# ----------------------------------------
SETTLE_TIME = datetime.time(hour=23, minute=50, tzinfo=KST) if KST else datetime.time(hour=23, minute=50)
RESET_TIME  = datetime.time(hour=23, minute=59, tzinfo=KST) if KST else datetime.time(hour=23, minute=59)

@tasks.loop(time=SETTLE_TIME)
async def weekly_auto_settle():
    now = now_kst_or_local()
    if now.weekday() != 6:  # 일요일만
        return

    channel = bot.get_channel(SETTLE_CHANNEL_ID)
    if channel is None:
        print("[AUTO SETTLE] SETTLE_CHANNEL_ID 채널을 찾을 수 없어 건너뜁니다.")
        return

    print_status_log("AUTO SETTLE (BEFORE)", channel.guild)
    await do_settle_for_guild(channel.guild, channel, mention_members=True)
    print_status_log("AUTO SETTLE (AFTER)", channel.guild)

@tasks.loop(time=RESET_TIME)
async def weekly_auto_reset():
    now = now_kst_or_local()
    if now.weekday() != 6:  # 일요일만
        return

    channel = bot.get_channel(VERIFY_CHANNEL_ID)
    if channel is None:
        print("[AUTO RESET] VERIFY_CHANNEL_ID 채널을 찾을 수 없어 건너뜁니다.")
        return

    print_status_log("AUTO RESET (BEFORE)", channel.guild)

    global weekly_counts
    weekly_counts = {}

    await channel.send("이번 주 기록을 자동으로 초기화했습니다. 새 주 시작!")

    print_status_log("AUTO RESET (AFTER)", channel.guild)

# ----------------------------------------
# 매일 현황 로그 (콘솔)
# ----------------------------------------
# 원하는 시간으로 바꾸면 됨
DAILY_STATUS_HOUR = 23
DAILY_STATUS_MINUTE = 40
DAILY_STATUS_TIME = (
    datetime.time(hour=DAILY_STATUS_HOUR, minute=DAILY_STATUS_MINUTE, tzinfo=KST)
    if KST else datetime.time(hour=DAILY_STATUS_HOUR, minute=DAILY_STATUS_MINUTE)
)

@tasks.loop(time=DAILY_STATUS_TIME)
async def daily_status_log():
    channel = bot.get_channel(SETTLE_CHANNEL_ID) or bot.get_channel(VERIFY_CHANNEL_ID)
    if channel is None:
        print("[DAILY STATUS] 채널을 못 찾아서 현황 로그를 건너뜁니다.")
        return

    print_status_log("DAILY STATUS", channel.guild)

# ----------------------------------------
# 새 멤버 들어오면 도움말
# ----------------------------------------
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    channel = guild.system_channel

    if channel is None:
        channel = guild.get_channel(VERIFY_CHANNEL_ID) or guild.get_channel(SETTLE_CHANNEL_ID)

    if channel is None:
        print(f"on_member_join: 적절한 채널을 찾지 못해 {member}에게 도움말을 보내지 못했습니다.")
        return

    help_msg = build_help_message_for_channel(channel.id)

    await channel.send(
        f"{member.mention}님, 서버에 오신 것을 환영합니다!\n\n"
        f"{help_msg}"
    )

def build_help_message_for_channel(channel_id: int) -> str:
    if channel_id == VERIFY_CHANNEL_ID:
        return (
            "인증 채널 도움말\n"
            "\n"
            "이 채널에서는 백준 문제 인증만 할 수 있어요.\n"
            "\n"
            "사용 가능한 명령어\n"
            " - `!solve <문제 URL>`\n"
            "  예시: `!solve https://www.acmicpc.net/problem/1000`\n"
            "\n"
            "`!solve`만 치면 URL을 적어달라는 안내만 나오고, 인증은 되지 않습니다."
        )

    if channel_id == SETTLE_CHANNEL_ID:
        return (
            "정산 채널 도움말\n"
            "\n"
            "이 채널에서는 이번 주 인증 현황 확인 및 벌금 정산을 할 수 있어요.\n"
            "\n"
            "사용 가능한 명령어\n"
            " - `!week`  : 이번 주 인증 현황\n"
            " - `!settle`: 이번 주 벌금 정산\n"
            " - `!resetweek` (관리자 전용): 이번 주 기록 초기화\n"
        )

    return (
        "방장봇 도움말\n"
        "\n"
        "벌금 및 분배 규칙\n"
        "- 주당 목표 문제 수: 5회\n"
        "- 미달 1회당 벌금: 1,000원\n"
        "- 5회 이상 인증 시 수령자 자격 부여\n"
        "- 벌금 총액을 수령자 수로 N분의 1하여 지급\n"
        "\n"
        "명령어 사용 안내\n"
        f"- 인증 채널(<#{VERIFY_CHANNEL_ID}>): `!solve <문제 URL>`\n"
        f"- 정산 채널(<#{SETTLE_CHANNEL_ID}>): `!week`, `!settle`, `!resetweek`\n"
        "\n"
        "자동 정산 및 초기화 시간\n"
        "- 매주 일요일 23:50 → 자동 정산\n"
        "- 매주 일요일 23:59 → 자동 초기화\n"
    )

# ----------------------------------------
# 메시지 처리: "!" 단독 입력시 도움말
# ----------------------------------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.content.strip() == "!":
        help_msg = build_help_message_for_channel(message.channel.id)
        await message.channel.send(help_msg)
        return

    await bot.process_commands(message)

# ----------------------------------------
# C. !solve (인증)
# ----------------------------------------
@bot.command(name="solve")
async def solve(ctx: commands.Context, *, url: str = None):
    if ctx.channel.id != VERIFY_CHANNEL_ID:
        await ctx.send("이 명령어는 인증 채널에서만 사용할 수 있습니다.")
        return

    if not url:
        await ctx.send(
            "문제 인증을 하려면 URL도 함께 적어주세요.\n"
            "예시: `!solve https://www.acmicpc.net/problem/1000`"
        )
        return

    if not url.startswith("http"):
        await ctx.send(
            "URL 형식이 올바르지 않습니다.\n"
            "예시: `!solve https://www.acmicpc.net/problem/1000`"
        )
        return

    user_id = ctx.author.id
    weekly_counts[user_id] = weekly_counts.get(user_id, 0) + 1

    # ✅ 업데이트 될 때마다 콘솔 로그
    now = now_kst_or_local()
    day = kst_weekday_name(now)
    print(f"[SOLVE] {now:%Y-%m-%d %H:%M:%S} ({day}) | {ctx.author.display_name} +1 → {weekly_counts[user_id]}회 | {url}")

    await ctx.send(
        f"{ctx.author.display_name}님, 인증 완료!\n"
        f"이번 주 누적: {weekly_counts[user_id]}회"
    )

# ----------------------------------------
# D. !week (이번 주 현황)
# ----------------------------------------
@bot.command(name="week")
async def week(ctx: commands.Context):
    if ctx.channel.id != SETTLE_CHANNEL_ID:
        await ctx.send("이 명령어는 정산 채널에서만 사용할 수 있습니다.")
        return

    members = [m for m in ctx.guild.members if not m.bot]
    if not members:
        await ctx.send("이 서버에 봇을 제외한 멤버가 없습니다.")
        return

    lines = ["이번 주 문제 풀이 현황 (서버 기준):"]
    for member in sorted(members, key=lambda m: m.display_name.lower()):
        count = weekly_counts.get(member.id, 0)
        lines.append(f"- {member.display_name}: {count}회")

    await ctx.send("\n".join(lines))

# ----------------------------------------
# E. 정산 로직
# ----------------------------------------
async def do_settle_for_guild(guild: discord.Guild, channel: discord.TextChannel, mention_members: bool):
    members = [m for m in guild.members if not m.bot]
    if not members:
        await channel.send("이 서버에 정산 대상 멤버(봇 제외)가 없습니다.")
        return

    target = 5
    penalty_per_miss = 1000

    payers = []
    receivers = []
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
            "기준 이상 인증자가 없어 벌금 분배 대상이 없습니다.\n"
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
async def settle(ctx: commands.Context):
    if ctx.channel.id != SETTLE_CHANNEL_ID:
        await ctx.send("이 명령어는 정산 채널에서만 사용할 수 있습니다.")
        return

    await do_settle_for_guild(ctx.guild, ctx.channel, mention_members=True)

# ----------------------------------------
# F. !resetweek (수동 초기화, 관리자 전용)
# ----------------------------------------
@bot.command(name="resetweek")
@commands.has_permissions(administrator=True)
async def reset_week(ctx: commands.Context):
    global weekly_counts
    weekly_counts = {}
    await ctx.send("이번 주 기록을 초기화했습니다.")
    print_status_log("MANUAL RESET", ctx.guild)

# ----------------------------------------
# 추가: !members
# ----------------------------------------
@bot.command(name="members")
async def members(ctx: commands.Context):
    members = [m for m in ctx.guild.members if not m.bot]
    if not members:
        await ctx.send("이 서버에 봇을 제외한 멤버가 없습니다.")
        return

    lines = ["서버 전체 멤버 목록:"]
    members_sorted = sorted(members, key=lambda m: m.display_name.lower())

    for member in members_sorted:
        lines.append(f"- {member.display_name}")

    chunk = []
    for line in lines:
        chunk.append(line)
        if sum(len(s) for s in chunk) > 1900:
            await ctx.send("\n".join(chunk))
            chunk = []
    if chunk:
        await ctx.send("\n".join(chunk))

# ----------------------------------------
# !help
# ----------------------------------------
@bot.command(name="help")
async def help_command(ctx: commands.Context):
    msg = build_help_message_for_channel(ctx.channel.id)
    await ctx.send(msg)


