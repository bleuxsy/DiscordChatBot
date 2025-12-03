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

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,  # 기본 help 명령어 비활성화
)
# 2. 인증 채널 ID (디스코드에서 복사한 숫자로 바꾸기)
VERIFY_CHANNEL_ID =  000000 # 여기에 실제 채널 ID 넣기
SETTLE_CHANNEL_ID = 000000
# 3. 이번 주 문제 카운트 저장용 (메모리용)
# {user_id: count}
weekly_counts = {}

#------------------------
from discord.ext.commands import CommandNotFound

@bot.event
async def on_command_error(ctx: commands.Context, error):
    # 1) 존재하지 않는 명령어일 때만 처리
    if isinstance(error, CommandNotFound):
        # 채널에 따라 안내 문구 다르게
        if ctx.channel.id == VERIFY_CHANNEL_ID:
            msg = (
                "❌ 존재하지 않는 명령어입니다.\n"
                "이 채널에서는 아래 명령어만 사용할 수 있어요:\n"
                "• `!solve <문제 URL>` - 문제 인증\n"
                "예시: `!solve https://www.acmicpc.net/problem/1000`"
            )
        elif ctx.channel.id == SETTLE_CHANNEL_ID:
            msg = (
                "❌ 존재하지 않는 명령어입니다.\n"
                "이 채널에서는 아래 명령어들을 사용할 수 있어요:\n"
                "• `!week` - 이번 주 문제 풀이 현황 보기\n"
                "• `!settle` - 이번 주 벌금 정산 "
            )
        else:
            msg = (
                "❌ 존재하지 않는 명령어입니다.\n"
                "사용 가능한 주요 명령어:\n"
                f"- 인증 채널(<#{VERIFY_CHANNEL_ID}>): `!solve <문제 URL>`\n"
                f"- 정산 채널(<#{SETTLE_CHANNEL_ID}>): `!week`, `!settle`"
            )

        await ctx.send(msg)
        return

    # 2) 그 외 에러는 기본 동작(로그로 보이게 그대로 터뜨리기)
    raise error

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
    channel = bot.get_channel(SETTLE_CHANNEL_ID)
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
@bot.event
async def on_member_join(member: discord.Member):
    """새 멤버가 서버에 들어왔을 때 자동으로 도움말 보내기"""

    guild = member.guild

    # 1) 디스코드 '일반 채널'(서버 설정에서 '시스템 메시지 채널') 우선 사용
    channel = guild.system_channel

    # 2) 만약 system_channel이 설정 안 돼 있으면,
    #    인증 채널 또는 정산 채널 중 하나로 fallback
    if channel is None:
        channel = guild.get_channel(VERIFY_CHANNEL_ID) or guild.get_channel(SETTLE_CHANNEL_ID)

    if channel is None:
        # 그래도 없으면 포기
        print(f"on_member_join: 적절한 채널을 찾지 못해 {member}에게 도움말을 보내지 못했습니다.")
        return

    # 이 채널 기준 help 메시지 만들어서
    help_msg = build_help_message_for_channel(channel.id)

    # 새 멤버 멘션 + 도움말 같이 보내기
    await channel.send(
        f"{member.mention}님, 서버에 오신 것을 환영합니다! 🎉\n\n"
        f"{help_msg}"
    )
def build_help_message_for_channel(channel_id: int) -> str:
    """채널 종류에 따라 help 메시지를 만들어주는 함수"""

    if channel_id == VERIFY_CHANNEL_ID:
        # ✅ 인증 채널용 도움말
        return (
            "📘 **인증 채널 도움말**\n"
            "\n"
            "이 채널에서는 **백준 문제 인증**만 할 수 있어요.\n"
            "\n"
            "**사용 가능한 명령어**\n"
            " - `!solve <문제 URL>`\n"
            "  → 오늘 푼 문제를 인증합니다.\n"
            "  예시: `!solve https://www.acmicpc.net/problem/1000`\n"
            "\n"
            "`!solve` 만 치면 URL을 적어달라는 안내만 나오고, 인증은 되지 않습니다."
        )

    elif channel_id == SETTLE_CHANNEL_ID:
        # ✅ 정산 채널용 도움말
        return (
            "📗 **정산 채널 도움말**\n"
            "\n"
            "이 채널에서는 **이번 주 인증 현황 확인 및 벌금 정산**을 할 수 있어요.\n"
            "\n"
            "**사용 가능한 명령어**\n"
            " - `!week`\n"
            "  → 이번 주 서버 전체 멤버(봇 제외)의 인증 횟수를 보여줍니다.\n"
            "\n"
            " - `!settle` \n"
            "  → 이번 주 기준으로 목표 회수에 못 미친 사람들의 벌금을 계산하고,\n"
            "    기준 이상 인증한 사람들에게 N빵 금액을 계산해서 보여줍니다.\n"
            "\n"
            " - `!resetweek` *(관리자 전용)*\n"
            "  → 이번 주 인증 기록을 수동으로 초기화합니다.\n"
        )

    # 그 외 일반 채널에서 쓸 기본 도움말
    return (
        "📙 **방장봇 도움말**\n"
        "\n"
        "💰 **벌금 및 분배 규칙**\n"
        "- 주당 **목표 문제 수: 5회**\n"
        "- **미달 1회당 벌금: 1,000원**\n"
        "- 5회 이상 인증 시 수령자 자격 부여\n"
        "- 벌금 총액을 **수령자 수로 N분의 1**하여 지급\n"
        "  (예: 총 6,000원 / 수령자 3명 → 1인당 2,000원)\n"
        "\n"
        "📝 **명령어 사용 안내**\n"
        "아래 채널에서 각각의 기능을 사용할 수 있어요.\n"
        "\n"
        f"📌 인증 채널(<#{VERIFY_CHANNEL_ID}>)\n"
        "- `!solve <문제 URL>` : 백준 문제 인증\n"
        "  예시: `!solve https://www.acmicpc.net/problem/1000`\n"
        "\n"
        f"📌 정산 채널(<#{SETTLE_CHANNEL_ID}>)\n"
        "- `!week` : 이번 주 인증 현황 보기\n"
        "- `!settle` : 이번 주 벌금 정산\n"
        "- `!resetweek` : 이번 주 기록 초기화 *(관리자 전용)*\n"
        "\n"
        "⏰ **자동 정산 및 초기화 시간 안내**\n"
        "- 매주 일요일 **23:50** → 자동 정산\n"
        "- 매주 일요일 **23:59** → 자동 초기화\n"
        "  (월요일부터 새로운 주차로 카운트 시작)\n"
        "\n"
        "⚠️ **주의사항**\n"
        "- 봇은 로컬 환경에서 실행되고 있어, **가끔 오프라인이 될 수 있습니다.**\n"
        "- 동작하지 않을 때는 관리자에게 알려주세요!\n"
        "- **재실행 시 인증 기록은 자동 복원**되니 걱정하지 않으셔도 됩니다 \n"
        "- 문의 사항이나 오류 발견 시 언제든지 말씀해주세요!\n"

    )
@bot.event
async def on_message(message: discord.Message):
    # 봇 자신 메시지는 무시
    if message.author.bot:
        return

    # "!" 단독 입력 → 도움말 자동 표시
    if message.content.strip() == "!":
        help_msg = build_help_message_for_channel(message.channel.id)
        await message.channel.send(help_msg)
        return

    await bot.process_commands(message)  # 명령어 정상 처리
# ----------------------------------------
# C. 명령어: !solve (인증)
# ----------------------------------------
@bot.command(name="solve")
async def solve(ctx: commands.Context, *, url: str = None):
    """
    사용 예시:
    !solve https://www.acmicpc.net/problem/1000
    """

    # 1) 인증 채널에서만 받기
    if ctx.channel.id != VERIFY_CHANNEL_ID:
        await ctx.send("이 명령어는 인증 채널에서만 사용할 수 있습니다.")
        return

    # 2) URL 안 적고 !solve만 쳤을 때
    if not url:
        await ctx.send(
            "문제 인증을 하려면 URL도 함께 적어주세요.\n"
            "예시: `!solve https://www.acmicpc.net/problem/1000`"
        )
        return  # ✅ 여기서 바로 종료 → 카운트 X

    # 3) URL 형식 검증
    if not url.startswith("http"):
        await ctx.send(
            "URL 형식이 올바르지 않습니다.\n"
            "예시: `!solve https://www.acmicpc.net/problem/1000`"
        )
        return

    # 필요하면 백준 전용으로 제한:
    # if "acmicpc.net" not in url and "boj.kr" not in url:
    #     await ctx.send("백준 문제 링크만 인증 가능합니다.")
    #     return

    # 4) 여기까지 왔으면 정상 URL → 카운트 증가
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
    # 정산 채널에서만 사용 가능
    if ctx.channel.id != SETTLE_CHANNEL_ID:
        await ctx.send("이 명령어는 정산 채널에서만 사용할 수 있습니다.")
        return

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
async def settle(ctx: commands.Context):
    # 정산 채널에서만 사용 가능
    if ctx.channel.id != SETTLE_CHANNEL_ID:
        await ctx.send("이 명령어는 정산 채널에서만 사용할 수 있습니다.")
        return

    channel = ctx.channel  # 어차피 정산 채널
    await do_settle_for_guild(ctx.guild, channel, mention_members=True)
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

    lines = ["📋 서버 전체 멤버 목록 :"]

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


#-----------------
@bot.command(name="help")
async def help_command(ctx: commands.Context):
    msg = build_help_message_for_channel(ctx.channel.id)
    await ctx.send(msg)

# 6. 봇 실행
TOKEN = "="
bot.run(TOKEN)
