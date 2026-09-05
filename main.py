import os
import asyncio
import discord
from discord.ext import commands
from discord.ui import Button, View

# ----------------- قراءة التوكنات والإعدادات من Railway -----------------
MAIN_BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN")

# جلب توكنات البوتات العشرة المساعدة من المتغيرات البيئية
HELPER_BOT_TOKENS = [
    os.getenv(f"HELPER_TOKEN_{i}") for i in range(1, 11)
    if os.getenv(f"HELPER_TOKEN_{i}")
]

JOIN_TO_CREATE_ID = int(os.getenv("JOIN_TO_CREATE_ID", "1543680903853641819"))
WAITING_ROOM_ID = int(os.getenv("WAITING_ROOM_ID", "1543680903853641821"))
CATEGORY_ID = int(os.getenv("CATEGORY_ID", "1543680903853641819"))
EMPTY_TIMEOUT = 3600  # مهلة خروج الجميع (ساعة كاملة = 3600 ثانية)

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.members = True

main_bot = commands.Bot(command_prefix="!", intents=intents)

active_rooms = {}
available_helpers = []

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
        await interaction.response.send_message("لتغيير اسم الروم استخدم خيارات القناة الصوتي.", ephemeral=True)

    @discord.ui.button(label="Limit", emoji="👥", style=discord.ButtonStyle.secondary, row=0)
    async def change_limit(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("تحديد عدد الأعضاء بالروم.", ephemeral=True)

    @discord.ui.button(label="Privacy", emoji="🛡️", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_privacy(self, interaction: discord.Interaction, button: Button):
        channel = interaction.guild.get_channel(self.room_id)
        if channel:
            current_overwrite = channel.overwrites_for(interaction.guild.default_role)
            is_locked = current_overwrite.connect is False
            await channel.set_permissions(interaction.guild.default_role, connect=is_locked)
            status = "مغلق 🔒" if not is_locked else "مفتوح 🔓"
            await interaction.response.send_message(f"تم تغيير حالة الروم إلى: {status}", ephemeral=True)

    @discord.ui.button(label="Delete", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def delete_room(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("جاري إغلاق الروم وإعادة البوت لروم الانتظار...", ephemeral=True)
        await delete_temp_room(self.room_id)

# ----------------- وظيفة حذف الروم وإرجاع البوت -----------------
async def delete_temp_room(room_id):
    if room_id not in active_rooms:
        return
    
    data = active_rooms.pop(room_id)
    room_channel = main_bot.get_channel(room_id)
    
    if data.get("interface_msg"):
        try:
            await data["interface_msg"].delete()
        except Exception:
            pass

    helper_bot = data.get("bot_client")
    if helper_bot:
        waiting_channel = helper_bot.get_channel(WAITING_ROOM_ID)
        for vc in helper_bot.voice_clients:
            if vc.channel.id == room_id:
                if waiting_channel:
                    await vc.move_to(waiting_channel)
                else:
                    await vc.disconnect()
        available_helpers.append(helper_bot)

    if room_channel:
        try:
            await room_channel.delete()
        except Exception:
            pass

# ----------------- الأحداث والمراقبة -----------------
@main_bot.event
async def on_voice_state_update(member, before, after):
    # دخول عضو لروم الانضمام الفوري
    if after.channel and after.channel.id == JOIN_TO_CREATE_ID:
        guild = member.guild
        category = guild.get_channel(CATEGORY_ID)
        
        if not available_helpers:
            await member.move_to(None)
            return

        assigned_helper = available_helpers.pop(0)

        room_name = f"🔊 | {member.display_name}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True),
            member: discord.PermissionOverwrite(manage_channels=True, move_members=True)
        }
        
        new_channel = await guild.create_voice_channel(
            name=room_name,
            category=category,
            overwrites=overwrites
        )

        await member.move_to(new_channel)

        for vc in assigned_helper.voice_clients:
            if vc.channel.id == WAITING_ROOM_ID:
                await vc.move_to(new_channel)

        embed = discord.Embed(
            title="TempVoice Interface",
            description="يمكنك إدارة خيارات وصلاحيات قناتك الصوتية عبر اللوحة أدناه.",
            color=discord.Color.from_rgb(230, 50, 75)
        )
        view = VoiceInterfaceView(owner_id=member.id, room_id=new_channel.id)
        msg = await new_channel.send(embed=embed, view=view)

        active_rooms[new_channel.id] = {
            "owner_id": member.id,
            "bot_client": assigned_helper,
            "interface_msg": msg,
            "timeout_task": None
        }

    # بدء عد مهلة الساعة عند خروج الجميع
    if before.channel and before.channel.id in active_rooms:
        room_id = before.channel.id
        channel = before.channel
        human_members = [m for m in channel.members if not m.bot]

        if len(human_members) == 0:
            async def delayed_deletion():
                await asyncio.sleep(EMPTY_TIMEOUT)
                await delete_temp_room(room_id)

            task = asyncio.create_task(delayed_deletion())
            active_rooms[room_id]["timeout_task"] = task

    # إلغاء الحذف فور رجوع أي شخص قبل انتهاء الساعة
    if after.channel and after.channel.id in active_rooms:
        room_id = after.channel.id
        room_data = active_rooms[room_id]
        if room_data.get("timeout_task"):
            room_data["timeout_task"].cancel()
            room_data["timeout_task"] = None

# ----------------- التشغيل على Railway -----------------
async def main():
    for token in HELPER_BOT_TOKENS:
        helper = discord.Client(intents=intents)
        
        @helper.event
        async def on_ready(h=helper):
            channel = h.get_channel(WAITING_ROOM_ID)
            if channel and isinstance(channel, discord.VoiceChannel):
                try:
                    await channel.connect(self_deaf=True)
                    available_helpers.append(h)
                    print(f"تم إدخال البوت [{h.user.name}] لروم الانتظار.")
                except Exception as e:
                    print(f"خطأ في دخول البوت: {e}")

        asyncio.create_task(helper.start(token))

    await main_bot.start(MAIN_BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
