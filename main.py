import os
import asyncio
import re
import datetime
import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import yt_dlp

# ----------------- قراءة التوكنات والإعدادات من Railway -----------------
MAIN_BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN") or os.getenv("DISCORD_TOKEN")

HELPER_BOT_TOKENS = []
for i in range(1, 11):
    token = os.getenv(f"HELPER_TOKEN_{i}")
    if token:
        HELPER_BOT_TOKENS.append((i, token))

JOIN_TO_CREATE_ID = int(os.getenv("JOIN_TO_CREATE_ID", "1546614862032150540"))
WAITING_ROOM_ID = int(os.getenv("WAITING_ROOM_ID", "1543680903853641821"))
CATEGORY_ID = int(os.getenv("CATEGORY_ID", "1546174974665039982"))
ALLOWED_SPOTIFY_CHANNEL_ID = 1547347259770019880

# ----------------- إعدادات روم اللوج والرتبة والمسبات -----------------
MOD_LOG_CHANNEL_ID = 1545547297096601630  # الروم المخصص لإرسال الإمبد
MOD_ROLE_ID = 1543682652417167460        # الرتبة المراد منشنتها

EMPTY_TIMEOUT = 3600  # مهلة تفريغ الروم (ساعة)

BAD_WORDS = [
    "3alaq", "3lq", "3rs", "anus", "b0z", "b3b3s", "bzz", "d3ara", "discord.gg", "dyoth", "dywth",
    "fajer", "fajra", "gl5", "glk", "ibnmtanaka", "k0s", "k5m", "khneth", "khol", "khwl", "kos",
    "k*s", "ks", "ksmk", "kss", "l7ass", "l7s", "laboh", "labwa", "m3rs", "ms", "mss", "n!k",
    "n€k", "n1k", "n33k", "nik", "porn", "q7ba", "qahba", "qwad", "qwada", "sharmota", "shmota",
    "si7aq", "t!z", "t1z", "tm7n", "tyez", "tyez0", "tyezs", "ybnlq7ba", "ybnshrmota", "ykhneth",
    "z0b", "z1b", "zany", "zanya", "zb", "z*b", "zbb", "متناكة", "ابن متناكه", "ابنمتناكة", "ابنمتناكه",
    "احط زبي", "ارkب عليه", "اركب عليه", "اركبه عليه", "ازبار", "اضربك", "اطياز", "اظبار", "اغتصب",
    "افشخك", "اكساس", "انيك", "اير", "بتتناك", "بز", "بزاز", "بزه", "بعبص", "بعبصه", "بنيك", "بورن",
    "بينيك", "تتمحن", "تشعبط", "تمحن", "تمص", "جلخ", "حايضة", "حايضه", "حط زبي", "خنيث", "خول",
    "دعاره", "ديوث", "زاني", "زانية", "زب", "زبوب", "زبون", "زبي", "زنوه", "زواني", "سحاق", "شراميط",
    "شرموطة", "شرموطه", "شقلي بقلي", "طرابيشي", "طياز", "طيز", "طيزه", "طيزها", "طيزي", "طيوز", "ظوبر",
    "ظوبره", "عاهر", "عاهره", "عرص", "علق", "فاجر", "فاجرة", "فاجره", "قحاب", "قحبة", "قحبه", "قواد",
    "قواده", "كاشحة", "كس", "كس م", "كسم", "كسمك", "كسمه", "كسمها", "كسمهم", "كسميات", "كسه", "كسها",
    "كسين", "كسينك", "كسينمك", "لايجة", "لبوة", "لبوه", "متناك", "متناكة", "متناكه", "مساحقه", "مص",
    "مصه", "مطايز", "معرص", "مفتوحة", "مناكح", "مناكيح", "منكوحة", "منيوك", "نياكه", "نيك", "نيكة",
    "نيكه", "هايجة", "يبن الشرموطه", "يبن القحبه", "يبنالشرموطه", "يبنالقحبه", "يتشعبط", "يتناك",
    "يجلخ", "يخنيث", "يلعن ابوك", "يلعن امك", "يلعن دينك", "يمص", "ينك", "ينيك"
]

# ----------------- تجهيز التعبيرات النمطية الدقيقة لجميع الكلمات -----------------
COMPILED_PATTERNS = []
for word in BAD_WORDS:
    w_escaped = re.escape(word.lower())
    # نمط شامل يلزم وجود حدود للكلمة سواء بالعربية أو بالإنجليزية أو الرموز
    pattern_str = rf"(?:(?<=[\s\^\W_])|(?<=^)){w_escaped}(?=(?:[\s\$\W_]|$))"
    COMPILED_PATTERNS.append((word, re.compile(pattern_str, re.UNICODE)))

# ----------------- إعداد الـ Intents -----------------
main_intents = discord.Intents.default()
main_intents.message_content = True
main_intents.voice_states = True
main_intents.guilds = True
main_intents.members = True
main_intents.presences = True

helper_intents = discord.Intents.default()
helper_intents.voice_states = True
helper_intents.guilds = True

main_bot = commands.Bot(command_prefix="!", intents=main_intents)

active_rooms = {}
available_helpers = []
room_counter = 0

# ----------------- وظيفة تحميل الفيديو -----------------
URL_REGEX = r'(https?://(?:www\.)?(?:tiktok\.com|instagram\.com|instagr\.am|youtube\.com/shorts)/[^\s]+)'

def download_media(url):
    ydl_opts = {
        'format': 'mp4/bestvideo+bestaudio/best',
        'outtmpl': 'downloaded_video.%(ext)s',
        'max_filesize': 25 * 1024 * 1024,
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename

# ----------------- نافذة تغيير اسم الروم الصوتية -----------------
class RenameModal(Modal, title="تغيير اسم الروم"):
    new_name = TextInput(
        label="الاسم الجديد للروم",
        placeholder="أدخل الاسم الجديد هنا...",
        required=True,
        max_length=100
    )

    def __init__(self, room_id):
        super().__init__()
        self.room_id = room_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel = interaction.guild.get_channel(self.room_id) or await interaction.guild.fetch_channel(self.room_id)
            if channel:
                await channel.edit(name=self.new_name.value)
                await interaction.response.send_message(f"✅ تم تغيير اسم الروم إلى: **{self.new_name.value}**", ephemeral=True)
            else:
                await interaction.response.send_message("❌ لم يتم العثور على القناة الصوتية.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ تعذر تغيير الاسم: {e}", ephemeral=True)

# ----------------- واجهة لوحة التحكم للروم المؤقتة -----------------
class VoiceInterfaceView(View):
    def __init__(self, owner_id, room_id):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.room_id = room_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ وحدك فقط صاحب هذا الروم الصوتي يحق له استخدام اللوحة!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Name", emoji="✏️", style=discord.ButtonStyle.secondary, row=0)
    async def change_name(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RenameModal(self.room_id))

    @discord.ui.button(label="Limit", emoji="👥", style=discord.ButtonStyle.secondary, row=0)
    async def change_limit(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("يمكنك تحديد عدد الأعضاء المسموح بهم من إعدادات القناة الصوتية المباشرة.", ephemeral=True)

    @discord.ui.button(label="Privacy", emoji="🛡️", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_privacy(self, interaction: discord.Interaction, button: Button):
        try:
            channel = interaction.guild.get_channel(self.room_id) or await interaction.guild.fetch_channel(self.room_id)
            if channel:
                current_overwrite = channel.overwrites_for(interaction.guild.default_role)
                is_locked = current_overwrite.connect is False
                await channel.set_permissions(interaction.guild.default_role, connect=is_locked)
                status = "مفتوح 🔓" if is_locked else "مغلق 🔒"
                await interaction.response.send_message(f"تم تغيير حالة الروم إلى: {status}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ تعذر تغيير الخصوصية: {e}", ephemeral=True)

    @discord.ui.button(label="Delete", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def delete_room(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("جاري إغلاق الروم وإعادة توجيه البوت...", ephemeral=True)
        await delete_temp_room(self.room_id)

# ----------------- وظيفة حذف الروم وإعادة البوتات المساعدة -----------------
async def delete_temp_room(room_id, delete_channel_discord=True):
    if room_id not in active_rooms:
        return
    
    data = active_rooms.pop(room_id)
    
    if data.get("timeout_task"):
        data["timeout_task"].cancel()

    if data.get("interface_msg"):
        try:
            await data["interface_msg"].delete()
        except Exception:
            pass

    helper_item = data.get("bot_item")
    
    if delete_channel_discord:
        room_channel = main_bot.get_channel(room_id)
        if not room_channel:
            try:
                room_channel = await main_bot.fetch_channel(room_id)
            except Exception:
                pass
        if room_channel:
            try:
                await room_channel.delete()
                print(f"🗑️ تم حذف الروم الصوتي [{room_id}] بنجاح.")
            except Exception as e:
                print(f"❌ تعذر حذف القناة الصوتية: {e}")

    if helper_item:
        helper_idx, helper_bot = helper_item
        target_channel_id = None
        
        for target_id, r_data in active_rooms.items():
            if r_data.get("bot_item") is None:
                target_channel_id = target_id
                r_data["bot_item"] = helper_item
                print(f"🔄 نقل البوت المساعد رقم [{helper_idx}] لخدمة الروم (ID: {target_id})")
                break
        
        if not target_channel_id:
            target_channel_id = WAITING_ROOM_ID
            if helper_item not in available_helpers:
                available_helpers.append(helper_item)
                available_helpers.sort(key=lambda x: x[0])
            print(f"🏠 إرجاع البوت المساعد رقم [{helper_idx}] لروم الانتظار.")

        try:
            waiting_or_target = helper_bot.get_channel(target_channel_id) or await helper_bot.fetch_channel(target_channel_id)
            if waiting_or_target:
                for vc in helper_bot.voice_clients:
                    await vc.disconnect()
                await waiting_or_target.connect(reconnect=True, self_deaf=True, self_mute=True)
        except Exception as e:
            print(f"❌ خطأ أثناء إعادة توجيه البوت المساعد: {e}")

# ----------------- الأحداث والأوامر للبوت الرئيسي -----------------
@main_bot.event
async def on_ready():
    print(f"🚀 تم تشغيل البوت الرئيسي بنجاح: {main_bot.user.name}")

# فحص الرسائل: الفلترة بحدود الكلمة الدقيقة لكل الكلمات
@main_bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    content_lower = message.content.lower()

    # 1. نظام الحماية بالبحث عن كل الكلمات بحدود كلمة كاملة ومستقلة
    matched_word = None
    for raw_word, compiled_pat in COMPILED_PATTERNS:
        if compiled_pat.search(content_lower):
            matched_word = raw_word
            break

    if matched_word:
        try:
            # حذف الرسالة المخالفة
            await message.delete()
        except Exception:
            pass

        try:
            # إعطاء تايم أوت لمدة ساعة (60 دقيقة)
            duration = datetime.timedelta(hours=1)
            await message.author.timeout(duration, reason=f"استخدام كلمة محظورة: {matched_word}")
        except Exception as e:
            print(f"❌ تعذر إعطاء تايم أوت للعضو: {e}")

        # جلب روم اللوج المخصص (1545547297096601630)
        log_channel = message.guild.get_channel(MOD_LOG_CHANNEL_ID)
        if not log_channel:
            try:
                log_channel = await message.guild.fetch_channel(MOD_LOG_CHANNEL_ID)
            except Exception:
                log_channel = None

        if log_channel:
            embed = discord.Embed(
                title="تصرف",
                color=0xBFBFBF,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.set_author(name=f"مخالفة بواسطة: {message.author.display_name}", icon_url=message.author.display_avatar.url)
            embed.add_field(name="العضو المخالف:", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
            embed.add_field(name="الكلمة المحظورة:", value=f"`{matched_word}`", inline=False)
            embed.add_field(name="الروم:", value=message.channel.mention, inline=False)
            embed.add_field(name="الإجراء:", value="تم تطبيق تايم أوت لمدة ساعة تلقائياً.", inline=False)
            embed.set_thumbnail(url=message.author.display_avatar.url)

            # إرسال المنشن للرتبة 1543682652417167460 متبوعاً بالإمبد
            await log_channel.send(content=f"<@&{MOD_ROLE_ID}> تصرف", embed=embed)

        return

    # 2. فحص الروابط وتنزيل الميديا
    urls = re.findall(URL_REGEX, message.content)
    if urls:
        url = urls[0]
        status_msg = await message.channel.send("📥 **جاري تحميل الفيديو...**")
        try:
            loop = asyncio.get_event_loop()
            filename = await loop.run_in_executor(None, download_media, url)
            
            if os.path.exists(filename):
                await message.channel.send(
                    content=f"🎬 **تم التحميل بواسطة:** {message.author.mention}",
                    file=discord.File(filename)
                )
                await status_msg.delete()
                os.remove(filename)
        except Exception as e:
            await status_msg.edit(content=f"❌ **تعذر تحميل الفيديو:** قد يكون الحجم كبيراً جداً أو الحساب خاص.")

    await main_bot.process_commands(message)

# أمر Spotify
@main_bot.command(name="spotify", aliases=["sp", "SP"])
async def spotify_status(ctx, member: discord.Member = None):
    if ctx.channel.id != ALLOWED_SPOTIFY_CHANNEL_ID:
        await ctx.send(f"❌ هذا الأمر مسموح به فقط في الروم المخصص <#{ALLOWED_SPOTIFY_CHANNEL_ID}>")
        return

    target = member or ctx.author

    spotify_activity = None
    for activity in target.activities:
        if isinstance(activity, discord.Spotify):
            spotify_activity = activity
            break

    if spotify_activity:
        artists_names = ", ".join(spotify_activity.artists)

        embed = discord.Embed(
            title=spotify_activity.title,
            url=spotify_activity.track_url,
            description=f"👤 **الفنان:** {artists_names}\n💿 **الألبوم:** {spotify_activity.album}",
            color=0xBFBFBF
        )
        embed.set_author(name=f"استماع حالي لـ {target.display_name}", icon_url=target.display_avatar.url)
        embed.set_thumbnail(url=spotify_activity.album_cover_url)

        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ {target.mention} لا يستمع إلى Spotify حالياً.")

@main_bot.event
async def on_guild_channel_delete(channel):
    if channel.id in active_rooms:
        print(f"⚠️ تم حذف الروم [{channel.name}] يدوياً بواسطة الأدمن. جاري إعادة البوت المساعد...")
        await delete_temp_room(channel.id, delete_channel_discord=False)

@main_bot.event
async def on_voice_state_update(member, before, after):
    global room_counter

    if after.channel and after.channel.id == JOIN_TO_CREATE_ID:
        guild = member.guild
        category = guild.get_channel(CATEGORY_ID)
        if not category:
            try:
                category = await guild.fetch_channel(CATEGORY_ID)
            except Exception:
                category = None
        
        room_counter += 1
        room_name = f"🔊 | روم #{room_counter}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True),
            member: discord.PermissionOverwrite(manage_channels=True, move_members=True)
        }
        
        try:
            new_channel = await guild.create_voice_channel(
                name=room_name,
                category=category,
                overwrites=overwrites
            )
            await member.move_to(new_channel)
            print(f"✅ تم إنشاء الروم ({room_name}) ونقل العضو ({member.display_name})")
        except Exception as e:
            print(f"❌ خطأ أثناء إنشاء الروم أو نقل العضو: {e}")
            return

        assigned_helper_item = None
        
        if available_helpers:
            assigned_helper_item = available_helpers.pop(0)
            h_idx, assigned_helper = assigned_helper_item

            try:
                for vc in assigned_helper.voice_clients:
                    await vc.disconnect()
                
                helper_target_channel = assigned_helper.get_channel(new_channel.id) or await assigned_helper.fetch_channel(new_channel.id)
                if helper_target_channel:
                    await helper_target_channel.connect(reconnect=True, self_deaf=True, self_mute=True)
                    print(f"🤖 دخل البوت المساعد رقم [{h_idx}] للروم الجديد.")
            except Exception as e:
                print(f"❌ تعذر نقل البوت المساعد للروم الجديد: {e}")

        try:
            embed = discord.Embed(
                title="TempVoice Interface",
                description="يمكنك إدارة خيارات وصلاحيات قناتك الصوتية عبر اللوحة أدناه.\nاضغط على **✏️ Name** لتغيير اسم الروم.",
                color=discord.Color.from_rgb(230, 50, 75)
            )
            view = VoiceInterfaceView(owner_id=member.id, room_id=new_channel.id)
            msg = await new_channel.send(embed=embed, view=view)
        except Exception as e:
            msg = None

        active_rooms[new_channel.id] = {
            "owner_id": member.id,
            "bot_item": assigned_helper_item,
            "interface_msg": msg,
            "timeout_task": None
        }

    for r_id in list(active_rooms.keys()):
        v_channel = main_bot.get_channel(r_id)
        if not v_channel:
            continue

        human_count = len([m for m in v_channel.members if not m.bot])
        r_data = active_rooms[r_id]

        if human_count == 0:
            if r_data.get("timeout_task") is None:
                async def delayed_deletion(target_room_id):
                    try:
                        print(f"⏳ بدأ مؤقت الحذف للروم [{target_room_id}] مدته {EMPTY_TIMEOUT} ثانية...")
                        await asyncio.sleep(EMPTY_TIMEOUT)
                        print(f"⏰ انتهت مهلة الساعة للروم [{target_room_id}]، جاري الحذف...")
                        await delete_temp_room(target_room_id)
                    except asyncio.CancelledError:
                        print(f"🛑 تم إيقاف مؤقت حذف الروم [{target_room_id}] لدخول شخص حقيقي.")

                task = asyncio.create_task(delayed_deletion(r_id))
                r_data["timeout_task"] = task

        else:
            if r_data.get("timeout_task") is not None:
                r_data["timeout_task"].cancel()
                r_data["timeout_task"] = None

# ----------------- تشغيل البوتات بترتيب تسلسلي -----------------
async def start_single_helper(index, token):
    helper = discord.Client(intents=helper_intents)
    ready_event = asyncio.Event()

    @helper.event
    async def on_ready():
        ready_event.set()

    asyncio.create_task(helper.start(token))
    await ready_event.wait()
    
    try:
        channel = helper.get_channel(WAITING_ROOM_ID) or await helper.fetch_channel(WAITING_ROOM_ID)
        if channel and isinstance(channel, discord.VoiceChannel):
            await channel.connect(reconnect=True, self_deaf=True, self_mute=True)
            available_helpers.append((index, helper))
            available_helpers.sort(key=lambda x: x[0])
            print(f"✅ البوت المساعد رقم [{index}] دخل روم الانتظار بالترتيب الصحيح.")
    except Exception as e:
        print(f"⚠️ تعذر إدخال البوت [{index}] لروم الانتظار: {e}")

async def main():
    if MAIN_BOT_TOKEN:
        asyncio.create_task(main_bot.start(MAIN_BOT_TOKEN))
    else:
        print("❌ لم يتم العثور على توكن البوت الرئيسي (MAIN_BOT_TOKEN / DISCORD_TOKEN)!")
        return

    print("⏳ جاري بدء تشغيل البوتات المساعدة بالترتيب المتسلسل...")
    for index, token in HELPER_BOT_TOKENS:
        await start_single_helper(index, token)
        await asyncio.sleep(1.5)

    print("🚀 اكتمل تشغيل وربط جميع البوتات بنجاح!")

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
