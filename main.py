import os
import asyncio
import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput

# ----------------- قراءة التوكنات والإعدادات من Railway -----------------
MAIN_BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN")

HELPER_BOT_TOKENS = [
    os.getenv(f"HELPER_TOKEN_{i}") for i in range(1, 11)
    if os.getenv(f"HELPER_TOKEN_{i}")
]

JOIN_TO_CREATE_ID = int(os.getenv("JOIN_TO_CREATE_ID", "1546614862032150540"))
WAITING_ROOM_ID = int(os.getenv("WAITING_ROOM_ID", "1543680903853641821"))
CATEGORY_ID = int(os.getenv("CATEGORY_ID", "1546174974665039982"))
EMPTY_TIMEOUT = 3600  # مهلة خروج الجميع (ساعة)

main_intents = discord.Intents.default()
main_intents.voice_states = True
main_intents.guilds = True
main_intents.members = True

helper_intents = discord.Intents.default()
helper_intents.voice_states = True
helper_intents.guilds = True

main_bot = commands.Bot(command_prefix="!", intents=main_intents)

active_rooms = {}
available_helpers = []
room_counter = 0

# ----------------- نافذة تغيير اسم الروم -----------------
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

# ----------------- واجهة لوحة التحكم (Interface) -----------------
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

# ----------------- وظيفة حذف الروم والتوجيه الذكي للبوت المساعد -----------------
async def delete_temp_room(room_id):
    if room_id not in active_rooms:
        return
    
    data = active_rooms.pop(room_id)
    
    if data.get("timeout_task"):
        data["timeout_task"].cancel()

    room_channel = main_bot.get_channel(room_id)
    if not room_channel:
        try:
            room_channel = await main_bot.fetch_channel(room_id)
        except Exception:
            pass

    if data.get("interface_msg"):
        try:
            await data["interface_msg"].delete()
        except Exception:
            pass

    helper_bot = data.get("bot_client")
    
    # حذف القناة الصوتية المؤقتة أولاً
    if room_channel:
        try:
            await room_channel.delete()
        except Exception as e:
            print(f"❌ تعذر حذف القناة الصوتية: {e}")

    # إعادة توجيه البوت المساعد (إلى روم محتاج أو لروم الانتظار)
    if helper_bot:
        target_channel_id = None
        
        # البحث عن أي روم نشط لا يملك بوت مساعد
        for target_id, r_data in active_rooms.items():
            if r_data.get("bot_client") is None:
                target_channel_id = target_id
                r_data["bot_client"] = helper_bot
                print(f"🔄 نقل البوت المساعد [{helper_bot.user.name}] لخدمة الروم المؤقت (ID: {target_id})")
                break
        
        # إذا لم يوجد روم محتاج، توجيهه لروم الانتظار
        if not target_channel_id:
            target_channel_id = WAITING_ROOM_ID
            if helper_bot not in available_helpers:
                available_helpers.append(helper_bot)
            print(f"🏠 إرجاع البوت المساعد [{helper_bot.user.name}] لروم الانتظار.")

        try:
            waiting_or_target = helper_bot.get_channel(target_channel_id) or await helper_bot.fetch_channel(target_channel_id)
            for vc in helper_bot.voice_clients:
                if waiting_or_target:
                    await vc.move_to(waiting_or_target)
        except Exception as e:
            print(f"❌ خطأ أثناء إعادة توجيه البوت المساعد: {e}")

# ----------------- الأحداث والمراقبة -----------------
@main_bot.event
async def on_ready():
    print(f"🚀 تم تشغيل البوت الرئيسي بنجاح: {main_bot.user.name}")

@main_bot.event
async def on_voice_state_update(member, before, after):
    global room_counter

    # 1. عند دخول عضو لروم الانضمام الفوري
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

        assigned_helper = None
        if available_helpers:
            assigned_helper = available_helpers.pop(0)
            for vc in assigned_helper.voice_clients:
                try:
                    # النقل المباشر وتفعيل الزيف (Deafen)
                    await vc.move_to(new_channel)
                    if hasattr(vc, "guild") and vc.guild.me:
                        await vc.guild.me.edit(deafen=True)
                    print(f"🤖 تم نقل البوت المساعد [{assigned_helper.user.name}] للروم الجديد وتفعيل الزيف.")
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
            "bot_client": assigned_helper,
            "interface_msg": msg,
            "timeout_task": None
        }

    # 2. خروج الأعضاء وتفعيل المؤقت
    if before.channel and before.channel.id in active_rooms:
        room_id = before.channel.id
        channel = before.channel
        human_members = [m for m in channel.members if not m.bot]

        if len(human_members) == 0:
            async def delayed_deletion():
                try:
                    await asyncio.sleep(EMPTY_TIMEOUT)
                    await delete_temp_room(room_id)
                except asyncio.CancelledError:
                    pass

            task = asyncio.create_task(delayed_deletion())
            active_rooms[room_id]["timeout_task"] = task

    # 3. إلغاء الحذف عند عودة أي عضو
    if after.channel and after.channel.id in active_rooms:
        room_id = after.channel.id
        room_data = active_rooms[room_id]
        human_members = [m for m in after.channel.members if not m.bot]
        
        if len(human_members) > 0 and room_data.get("timeout_task"):
            room_data["timeout_task"].cancel()
            room_data["timeout_task"] = None

# ----------------- التشغيل للبوتات المساعدة -----------------
async def connect_helper_to_waiting_room(helper):
    await asyncio.sleep(5)
    try:
        channel = helper.get_channel(WAITING_ROOM_ID) or await helper.fetch_channel(WAITING_ROOM_ID)
        if channel and isinstance(channel, discord.VoiceChannel):
            if not helper.voice_clients:
                # تفعيل self_deaf عند الاتصال الأولي
                await channel.connect(reconnect=True, self_deaf=True)
                if helper not in available_helpers:
                    available_helpers.append(helper)
                print(f"🤖 البوت المساعد [{helper.user.name}] دخل روم الانتظار بنجاح (مع الزيف).")
    except Exception as e:
        print(f"⚠️ فشل البوت المساعد [{helper.user}] في دخول روم الانتظار: {e}")

async def start_helper_bot(token):
    helper = discord.Client(intents=helper_intents)

    @helper.event
    async def on_ready():
        asyncio.create_task(connect_helper_to_waiting_room(helper))

    try:
        await helper.start(token)
    except Exception as e:
        print(f"❌ فشل تشغيل أحد البوتات المساعدة: {e}")

async def main():
    if MAIN_BOT_TOKEN:
        asyncio.create_task(main_bot.start(MAIN_BOT_TOKEN))
    else:
        print("❌ لم يتم العثور على MAIN_BOT_TOKEN!")
        return

    for token in HELPER_BOT_TOKENS:
        if token:
            asyncio.create_task(start_helper_bot(token))

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
