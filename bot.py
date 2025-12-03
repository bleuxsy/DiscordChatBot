
# # bot.py
# import os
# import ssl
# import certifi
#
# # certifi에서 제공하는 CA 인증서를 전역 SSL 기본값으로 설정
# os.environ["SSL_CERT_FILE"] = certifi.where()
# os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
#
# import discord
# from discord.ext import commands
#
#
#
# # 1. 디스코드 Intents 설정 (메시지 내용 읽기 허용)
# intents = discord.Intents.default()
# intents.message_content = True
# intents.messages = True
#
# bot = commands.Bot(command_prefix="!", intents=intents)
#
# # 2. 인증 채널 ID (디스코드에서 복사한 숫자로 바꾸기)
# VERIFY_CHANNEL_ID = 1445356309871464498  # 여기에 실제 채널 ID 넣기
#
# # 3. 이번 주 문제 카운트 저장용 (간단 버전: 메모리)
# weekly_counts = {}  # {user_id: count}
#
# @bot.event
# async def on_ready():
#     print(f"Logged in as {bot.user}")
#
# # @bot.event
# # async def on_message(message: discord.Message):
# #     # 봇 자신의 메시지는 무시
# #     if message.author.bot:
# #         return
# #
# #     # 특정 채널에서만 카운트
# #     if message.channel.id == VERIFY_CHANNEL_ID:
# #         user_id = message.author.id
# #         weekly_counts[user_id] = weekly_counts.get(user_id, 0) + 1
# #         # 간단 피드백 (원하면 지워도 됨)
# #         await message.channel.send(
# #             f"{message.author.display_name} 이번 주 누적: {weekly_counts[user_id]}회"
# #         )
# #
# #     # on_message를 쓰면 명령어 인식이 막히므로 이거 필요
# #     await bot.process_commands(message)
#
# @bot.command(name="solve")
# async def solve(ctx: commands.Context, *, url: str):
#     """
#     사용 예시:
#     !solve https://www.acmicpc.net/problem/1000
#     """
#
#     # 1) 인증 채널에서만 받기 (다른 채널이면 안내만)
#     if ctx.channel.id != VERIFY_CHANNEL_ID:
#         await ctx.send("이 명령어는 인증 채널에서만 사용할 수 있습니다.")
#         return
#
#     # 2) URL 검증 (대충이라도 필터링)
#     if not url.startswith("http"):
#         await ctx.send("URL 형식이 올바르지 않습니다. 예: !solve https://www.acmicpc.net/problem/1000")
#         return
#
#     # 필요하면 백준 전용 체크도 가능:
#     # if "acmicpc.net" not in url and "boj.kr" not in url:
#     #     await ctx.send("백준 문제 링크만 인증 가능합니다.")
#     #     return
#
#     user_id = ctx.author.id
#     weekly_counts[user_id] = weekly_counts.get(user_id, 0) + 1
#
#     await ctx.send(
#         f"{ctx.author.display_name}님, 인증 완료!\n"
#         f"이번 주 누적: {weekly_counts[user_id]}회"
#     )
# # 4. 이번 주 랭킹 확인 명령어
# @bot.command(name="week")
# async def week(ctx: commands.Context):
#     if not weekly_counts:
#         await ctx.send("이번 주 기록이 아직 없습니다.")
#         return
#
#     lines = ["이번 주 문제 풀이 현황:"]
#     # user_id -> 멘션 + 카운트
#     for user_id, count in weekly_counts.items():
#         user = ctx.guild.get_member(user_id)
#         name = user.display_name if user else f"<@{user_id}>"
#         lines.append(f"- {name}: {count}회")
#
#     await ctx.send("\n".join(lines))
#
#
# #정산
# @bot.command(name="settle")
# @commands.has_permissions(administrator=True)  # 관리자만 실행 가능하게
# async def settle(ctx: commands.Context):
#     if not weekly_counts:
#         await ctx.send("이번 주 기록이 아직 없습니다.")
#         return
#
#     target = 5        # 주당 목표 문제 수
#     penalty_per_miss = 1000  # 1회 미인증당 벌금
#
#     payers = []       # 벌금 내는 사람들 ([(user, amount), ...])
#     receivers = []    # N빵 받는 사람들 ([user, ...])
#     total_penalty = 0
#
#     # 1) 유저별로 벌금/수령자 분류
#     for user_id, count in weekly_counts.items():
#         member = ctx.guild.get_member(user_id)
#         name = member.display_name if member else f"<@{user_id}>"
#
#         if count >= target:
#             receivers.append(name)
#         else:
#             miss = target - count
#             amount = miss * penalty_per_miss
#             total_penalty += amount
#             payers.append((name, amount, count))
#
#     # 2) 수령자 없을 때 처리
#     if total_penalty == 0:
#         await ctx.send("이번 주에는 벌금이 없습니다. 모두 수고하셨습니다!")
#         return
#
#     if not receivers:
#         await ctx.send(
#             f"이번 주에 5회 이상 인증한 사람이 없어 벌금을 분배할 대상이 없습니다.\n"
#             f"총 벌금: {total_penalty}원"
#         )
#         return
#
#     # 3) 1인당 받을 금액 계산 (정수로 내림 처리)
#     per_person = total_penalty // len(receivers)
#
#     # 4) 메세지 구성
#     lines = []
#     lines.append("이번 주 정산 결과:")
#     lines.append("")
#     lines.append(f"- 기준 문제 수: 주당 {target}회")
#     lines.append(f"- 1회 미달 벌금: {penalty_per_miss}원")
#     lines.append(f"- 총 벌금: {total_penalty}원")
#     lines.append("")
#
#     if payers:
#         lines.append("벌금 내야 하는 사람:")
#         for name, amount, count in payers:
#             lines.append(f"  • {name}: {count}회 인증 → {amount}원")
#     else:
#         lines.append("벌금 내야 하는 사람: 없음")
#     lines.append("")
#
#     lines.append("5회 이상 인증 완료한 사람:")
#     for name in receivers:
#         lines.append(f"  • {name}")
#     lines.append("")
#     lines.append(f"1인당 받을 금액: {per_person}원")
#
#     await ctx.send("\n".join(lines))
#
#
# bot.py
import os
import asyncio
import datetime
import certifi

# certifi에서 제공하는 CA 인증서를 전역 SSL 기본값으로 설정
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    ZoneInfo = None  # 혹시 안 되면 시스템 로컬 시간 기준으로 처리할 수도 있음

import discord
from discord.ext import commands, tasks

# 1. 디스코드 Intents 설정 (메시지 내용 읽기 허용)
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 2. 인증 채널 ID (디스코드에서 복사한 숫자로 바꾸기)
VERIFY_CHANNEL_ID =   # 여기에 실제 채널 ID 넣기

# 3. 이번 주 문제 카운트 저장용 (간단 버전: 메모리)
# {user_id: count}
weekly_counts = {}


# ---------------------------
#  A. 봇 준비 & 자동 리셋 태스크
# ---------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    if not weekly_auto_reset.is_running():
        weekly_auto_reset.start()
        print("weekly_auto_reset task started")


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

    # 타임존 설정 (가능하면 Asia/Seoul, 아니면 시스템 로컬 타임)
    if ZoneInfo is not None:
        tz = ZoneInfo("Asia/Seoul")
        now = datetime.datetime.now(tz)
    else:
        now = datetime.datetime.now()
        tz = None

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


# ---------------------------
#  B. 명령어: !solve (인증)
# ---------------------------
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



    user_id = ctx.author.id
    weekly_counts[user_id] = weekly_counts.get(user_id, 0) + 1

    await ctx.send(
        f"{ctx.author.display_name}님, 인증 완료!\n"
        f"이번 주 누적: {weekly_counts[user_id]}회"
    )


# ---------------------------
#  C. 명령어: !week (이번 주 현황)
# ---------------------------
@bot.command(name="week")
async def week(ctx: commands.Context):
    if not weekly_counts:
        await ctx.send("이번 주 기록이 아직 없습니다.")
        return

    lines = ["이번 주 문제 풀이 현황:"]
    for user_id, count in weekly_counts.items():
        user = ctx.guild.get_member(user_id)
        name = user.display_name if user else f"<@{user_id}>"
        lines.append(f"- {name}: {count}회")

    await ctx.send("\n".join(lines))


# ---------------------------
#  D. 명령어: !settle (정산)
# ---------------------------
@bot.command(name="settle")
@commands.has_permissions(administrator=True)  # 관리자만 실행
async def settle(ctx: commands.Context):
    if not weekly_counts:
        await ctx.send("이번 주 기록이 아직 없습니다.")
        return

    target = 5               # 주당 목표 문제 수
    penalty_per_miss = 1000  # 1회 미인증당 벌금

    payers = []       # [(name, amount, count), ...]
    receivers = []    # [name, ...]
    total_penalty = 0

    # 1) 유저별로 벌금/수령자 분류
    for user_id, count in weekly_counts.items():
        member = ctx.guild.get_member(user_id)
        name = member.display_name if member else f"<@{user_id}>"

        if count >= target:
            receivers.append(name)
        else:
            miss = target - count
            amount = miss * penalty_per_miss
            total_penalty += amount
            payers.append((name, amount, count))

    # 2) 벌금이 아예 없는 경우
    if total_penalty == 0:
        await ctx.send("이번 주에는 벌금이 없습니다. 모두 수고하셨습니다!")
        return

    # 3) 수령자가 없는 경우
    if not receivers:
        await ctx.send(
            f"이번 주에 5회 이상 인증한 사람이 없어 벌금을 분배할 대상이 없습니다.\n"
            f"총 벌금: {total_penalty}원"
        )
        return

    # 4) 1인당 받을 금액 (정수 내림)
    per_person = total_penalty // len(receivers)

    lines = []
    lines.append("이번 주 정산 결과:")
    lines.append("")
    lines.append(f"- 기준 문제 수: 주당 {target}회")
    lines.append(f"- 1회 미달 벌금: {penalty_per_miss}원")
    lines.append(f"- 총 벌금: {total_penalty}원")
    lines.append("")

    if payers:
        lines.append("벌금 내야 하는 사람:")
        for name, amount, count in payers:
            lines.append(f"  • {name}: {count}회 인증 → {amount}원")
    else:
        lines.append("벌금 내야 하는 사람: 없음")
    lines.append("")

    lines.append("5회 이상 인증 완료한 사람:")
    for name in receivers:
        lines.append(f"  • {name}")
    lines.append("")
    lines.append(f"1인당 받을 금액: {per_person}원")

    await ctx.send("\n".join(lines))


# ---------------------------
#  E. 명령어: !resetweek (수동 초기화)
# ---------------------------
@bot.command(name="resetweek")
@commands.has_permissions(administrator=True)
async def reset_week(ctx: commands.Context):
    global weekly_counts
    weekly_counts = {}
    await ctx.send("이번 주 기록을 초기화했습니다.")


# ---------------------------
#  F. 봇 실행
# ---------------------------
# 토큰은 환경변수로 관리하는 걸 강력 추천




# 6. 봇 실행
TOKEN = ""
bot.run(TOKEN)
