import discord
from discord import app_commands
import asyncio
import os
import shlex
import subprocess
import uuid
import traceback

# Bot token
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Intents
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Temp folder
TEMP_DIR = "temp_files"
os.makedirs(TEMP_DIR, exist_ok=True)

# Supported languages
LANGUAGES = {
    "c": {
        "compile": "gcc {sources} -o {output} {flags}",
        "run": "./{output}",
        "extension": ".c",
    },
    "python": {
        "run": "python3 {sources}",
        "extension": ".py",
    },
    "rust": {
        "compile": "rustc {sources} -o {output} {flags}",
        "run": "./{output}",
        "extension": ".rs",
    },
    "go": {
        "compile": "go build -o {output} {sources} {flags}",
        "run": "./{output}",
        "extension": ".go",
    },
    "bash": {
        "run": "bash {sources}",
        "extension": ".sh",
    },
     "cpp": {
        "compile": "g++ {sources} -o {output} {flags}",
        "run": "./{output}",
        "extension": ".cpp",
    },
    "php": {
        "run": "php {sources}",
        "extension": ".php",
    },
    "lua": {
        "run": "lua {sources}",
        "extension": ".lua",
    },
    "ruby": {
        "run": "ruby {sources}",
        "extension": ".rb",
    },
    "javascript": {
        "run": "node {sources}",
        "extension": ".js",
    },
}

MAX_LOGS = 10
RUN_LOGS = []

@tree.command(name="help", description="Show help info for the bot")
async def help_command(interaction: discord.Interaction):
    help_text = """
**Supported Commands:**

`/help` - Show this help message

`/eval -r [options]`
- `-l language` (c, python, rust, go, bash, cpp, lua, php, javascript, ruby, java coming soon!)
- `-c "code"` (inline code)
- `-f "flags"` (compiler flags)
- `-fl` (upload files in next message, you can also add multiple and they will be linked)

**Examples:**
- `/eval -r main.c` (auto-detects C)
- `/eval -r -l python -c "print('hello')"`
- `/eval -r -fl` (upload files after command)
"""
    await interaction.response.send_message(help_text, ephemeral=True)

@tree.command(name="logs", description="Show last N eval runs")
async def logs_command(interaction: discord.Interaction):
    text = "**Last Runs:**\n" + "\n".join(
        f"`{log}`" for log in reversed(RUN_LOGS[-MAX_LOGS:])
    ) if RUN_LOGS else "No runs yet."
    await interaction.response.send_message(text[:1900], ephemeral=True)

async def process_eval(interaction: discord.Interaction, args: list, attachments: list):
    language = None
    code = None
    linked_files = []
    compiler_flags = ""

    # Parse arguments
    i = 0
    while i < len(args):
        if args[i] == "-l":
            language = args[i + 1].lower()
            i += 2
        elif args[i] == "-c":
            code = args[i + 1]
            i += 2
        elif args[i] == "-ln":
            i += 1
            while i < len(args) and not args[i].startswith("-"):
                linked_files.append(args[i])
                i += 1
        elif args[i] == "-f":
            compiler_flags = args[i + 1]
            i += 2
        else:
            i += 1

    sources = ""
    output_name = f"{TEMP_DIR}/{uuid.uuid4().hex}"

    try:
        # Handle inline code
        if code:
            if not language:
                await interaction.followup.send("Error: Language (-l) required with -c")
                return
            if language not in LANGUAGES:
                await interaction.followup.send(f"Unsupported language: {language}")
                return

            ext = LANGUAGES[language]["extension"]
            source_file = f"{TEMP_DIR}/{uuid.uuid4().hex}{ext}"
            with open(source_file, "w") as f:
                f.write(code)
            sources += source_file + " "

        # Handle attachments
        used_attachments = []
        for attachment in attachments:
            if not linked_files or attachment.filename in linked_files:
                file_path = os.path.join(TEMP_DIR, attachment.filename)
                await attachment.save(file_path)
                sources += file_path + " "
                used_attachments.append(attachment.filename)

        # Auto-detect language from first file if not specified
        if not language and used_attachments:
            ext = os.path.splitext(used_attachments[0])[1]
            for lang, info in LANGUAGES.items():
                if ext == info["extension"]:
                    language = lang
                    break
            else:
                await interaction.followup.send("Could not auto-detect language")
                return

        # Validate language
        if language not in LANGUAGES:
            await interaction.followup.send(f"Unsupported language: {language}")
            return

        lang_info = LANGUAGES[language]

        # Compile if needed
        if "compile" in lang_info:
            compile_cmd = lang_info["compile"].format(
                sources=sources.strip(),
                output=output_name,
                flags=compiler_flags
            )
            compile_result = subprocess.run(
                compile_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10
            )

            if compile_result.returncode != 0:
                output = f"**Compilation failed:**\n```{compile_result.stderr.decode()}```"
                await interaction.followup.send(output)
                RUN_LOGS.append(f"{language} compile failed")
                return

            run_cmd = lang_info["run"].format(output=output_name)
        else:
            run_cmd = lang_info["run"].format(sources=sources.strip())

        # Execute
        run_result = subprocess.run(
            run_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10
        )

        # Format output
        output = []
        if run_result.stdout:
            output.append(f"**Output:**\n```{run_result.stdout.decode()}```")
        if run_result.stderr:
            output.append(f"**Errors:**\n```{run_result.stderr.decode()}```")
        output_text = "\n".join(output) or "No output"

        # Log and respond
        RUN_LOGS.append(f"{language} run ({len(used_attachments)} files)")
        if len(RUN_LOGS) > MAX_LOGS:
            RUN_LOGS.pop(0)

        if len(output_text) > 1800:
            with open(f"{TEMP_DIR}/output.txt", "w") as f:
                f.write(output_text)
            await interaction.followup.send(
                content="Output too long:",
                file=discord.File(f"{TEMP_DIR}/output.txt")
            )
        else:
            await interaction.followup.send(output_text)

    except subprocess.TimeoutExpired:
        await interaction.followup.send("⏰ Execution timed out")
    except Exception as e:
        await interaction.followup.send(f"❌ Error:\n```{traceback.format_exc()}```")
    finally:
        # Cleanup
        for f in os.listdir(TEMP_DIR):
            try:
                os.remove(os.path.join(TEMP_DIR, f))
            except:
                pass

@tree.command(name="eval", description="Run code or files")
@app_commands.describe(flags="Command flags (see /help)")
async def eval_command(interaction: discord.Interaction, flags: str):
    args = shlex.split(flags)
    
    if "-fl" in args:
        await interaction.response.send_message(
            "📤 Please reply with @coderunner.bot and your files attached"
        )
        
        def check(m):
            return (
                m.author == interaction.user and
                client.user in m.mentions and
                bool(m.attachments) and
                m.channel == interaction.channel
            )
        
        try:
            msg = await client.wait_for("message", check=check, timeout=60)
            await interaction.followup.send("🔍 Processing...")
            await process_eval(interaction, args, msg.attachments)
        except asyncio.TimeoutError:
            await interaction.followup.send("⌛ Timed out waiting for files")
    else:
        await interaction.response.defer(thinking=True)
        await process_eval(interaction, args, [])

@client.event
async def on_ready():
    await tree.sync()
    print(f"Ready as {client.user}")

client.run(TOKEN)
