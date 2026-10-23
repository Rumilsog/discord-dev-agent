import os
import asyncio
import discord
from google import genai
from google.genai import types

# A kulcsokat mostantól a felhő környezeti változóiból olvassa
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Gemini kliens inicializálása
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Discord intents beállítása
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

# Globális kontextus tároló a futó parancsokhoz
current_context = {"guild": None, "author": None}

# ==========================================
# ESZKÖZÖK (TOOLS), AMIT A BOT HASZNÁLHAT
# ==========================================
def create_channel(name: str, type: str = "text", private: bool = False) -> str:
    """Létrehoz egy új csatornát a Discord szerveren.
    
    Args:
        name: A csatorna neve (pl. "pre-light").
        type: A csatorna típusa ("text" vagy "voice").
        private: Ha True, csak a parancs kiadója és a bot láthatja, mások elől rejtve van.
    """
    guild = current_context.get("guild")
    author = current_context.get("author")
    
    if not guild:
        return "Hiba: Nincs aktív szerver kontextus."
    
    future = asyncio.run_coroutine_threadsafe(
        _async_create_channel(guild, author, name, type, private),
        client_bot.loop
    )
    return future.result(timeout=15)

async def _async_create_channel(guild, author, name, type, private):
    try:
        overwrites = {}
        if private:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False),
                author: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True)
            }
        
        if type.lower() == "voice":
            channel = await guild.create_voice_channel(name=name, overwrites=overwrites if private else {})
        else:
            channel = await guild.create_text_channel(name=name, overwrites=overwrites if private else {})
        
        visibility_text = "privát (csak ti ketten)" if private else "nyilvános"
        return f"Sikeresen létrehoztam a(z) '{name}' nevű {type} csatornát ({visibility_text}): {channel.mention}"
    except Exception as e:
        return f"Hiba történt a csatorna létrehozása közben: {e}"

SYSTEM_PROMPT = """
Te vagy a Discord Fejlesztő és Szerverépítész Agent (Discord Developer Agent). 
Teljeskörű adminisztrátori joggal bírsz a Discord szerveren. Ha a felhasználó arra kér, hogy hozz létre csatornát (pl. "Pre Light"), kategóriát, szerepkört, vagy módosíts bármit a szerveren, NE csak elmagyarázd, hanem HASZNÁLD A RENDELKEZÉSRE ÁLLÓ ESZKÖZÖKET (tool call) a végrehajtásukhoz!
Mindig magyarul válaszolj, gyakorlatiasan és határozottan.
"""

class DiscordDevAgent(discord.Client):
    async def on_ready(self):
        global client_bot
        client_bot = self
        print(f"Bejelentkezve mint Discord Fejlesztő Agent: {self.user} (ID: {self.user.id})")
        print("A Discord Developer Agent készen áll az önálló szerverépítésre!")

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.user.mentioned_in(message)

        if is_dm or is_mentioned:
            prompt = message.content.replace(f'<@!{self.user.id}>', '').replace(f'<@{self.user.id}>', '').strip()
            
            if not prompt:
                return

            current_context["guild"] = message.guild
            current_context["author"] = message.author

            async with message.channel.typing():
                response = None
                success = False
                
                for attempt in range(3):
                    try:
                        response = await asyncio.to_thread(
                            gemini_client.models.generate_content,
                            model='gemini-3.8-flash',
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                system_instruction=SYSTEM_PROMPT,
                                tools=[create_channel],
                                temperature=0.4,
                            )
                        )
                        success = True
                        break
                    except Exception as e:
                        error_str = str(e)
                        if "503" in error_str and attempt < 2:
                            await asyncio.sleep(2)
                            continue
                        elif attempt == 2:
                            await message.reply(f"A szerverek átmenetileg túlterheltek. Kérlek, próbáld meg újra később! (Hiba: `{e}`)")
                            return
                        else:
                            await message.reply(f"Hiba történt a kérés feldolgozása közben: `{e}`")
                            return

                if success and response:
                    reply_text = response.text if response.text else "Elvégeztem a műveletet!"
                    
                    if len(reply_text) > 2000:
                        chunks = [reply_text[i:i+1997] for i in range(0, len(reply_text), 1997)]
                        for chunk in chunks:
                            await message.channel.send(chunk)
                    else:
                        await message.reply(reply_text)

client = DiscordDevAgent(intents=intents)
client.run(DISCORD_BOT_TOKEN)