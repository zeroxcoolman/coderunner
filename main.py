import discord
from discord import app_commands
import asyncio
import os
import shlex
import subprocess
import uuid
import traceback

# Bot token (use .env or Railway secret)
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Intents
intents = discord.Intents.default()
intents.message_content = True  # Needed to see message content
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
}

# Logs (last N runs)
MAX_LOGS = 10
RUN_LOGS = []

@tree.command(name="help", description="Show help info for the bot")
async def help_command(interaction: discord.Interaction):
    help_text = """
**Supported Commands:**

`/help` - Show this help message

`/eval -r [options]`
- `-l language` (c, python, rust) - optional if files attached
- `-c "code"`  (inline code to run)
- `-ln file1 file2 ...` (optional linked filenames)
- `-f "flags"` (optional compiler flags)
- `-fl` (will prompt for file upload - reply with @coderunner.bot and your file)

**Examples:**
- `/eval -r main.c` (auto detects C)
- `/eval -r -l c -ln main.c`
- `/eval -r -l python -c "print(123)"`
- `/eval -r -l rust -c "fn main() { println!(\"Hello\"); }"`
- `/eval -r -fl` (then reply with @coderunner.bot and your file)

**Security Notice:**
This bot executes code with basic protection (timeouts, temp dirs). Use with caution.
"""
    await interaction.response.send_message(help_text, ephemeral=True)

@tree.command(name="logs", description="Show last N eval runs")
async def logs_command(interaction: discord.Interaction):
    text = "**Last Runs:**\n"
    if not RUN_LOGS:
        text += "No runs yet."
    else:
        for log in reversed(RUN_LOGS[-MAX_LOGS:]):
            text += f"\n`{log}`"

    await interaction.response.send_message(text[:1900], ephemeral=True)

async def process_eval(interaction: discord.Interaction, args: list, attachments: list):
    language = None
    code = None
    linked_files = []
    compiler_flags = ""

    # Parse args
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
        # Save inline code if provided
        if code:
            if not language:
                await interaction.followup.send("Error: Language (-l) required when using inline code (-c).")
                return

            lang_info = LANGUAGES.get(language)
            if not lang_info:
                await interaction.followup.send(f"Unsupported language: {language}")
                return

            source_file = f"{TEMP_DIR}/{uuid.uuid4().hex}{lang_info['extension']}"
            with open(source_file, "w") as f:
                f.write(code)
            sources += source_file + " "

        # Save attachments if provided
        used_attachments = []
        for attachment in attachments:
            if (not linked_files) or (attachment.filename in linked_files):
                file_path = os.path.join(TEMP_DIR, attachment.filename)
                await attachment.save(file_path)
                sources += file_path + " "
                used_attachments.append(attachment.filename)

        # Auto detect language if not set and files uploaded
        if not language and used_attachments:
            ext = os.path.splitext(used_attachments[0])[1]
            for lang, info in LANGUAGES.items():
                if ext == info['extension']:
                    language = lang
                    break

            if not language:
                await interaction.followup.send("Could not auto-detect language from file extension.")
                return

        # Validate language
        lang_info = LANGUAGES.get(language)
        if not lang_info:
            await interaction.followup.send(f"Unsupported language: {language}")
            return

        # Compile if needed
        if "compile" in lang_info:
            compile_cmd = lang_info["compile"].format(sources=sources.strip(), output=output_name, flags=compiler_flags)
            compile_result = subprocess.run(compile_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)

            if compile_result.returncode != 0:
                output = f"**Compilation failed:**\n```{compile_result.stderr.decode()}```"
                await interaction.followup.send(output)
                RUN_LOGS.append(f"{language} compile failed")
                return

            run_cmd = lang_info["run"].format(output=output_name)
        else:
            run_cmd = lang_info["run"].format(sources=sources.strip())

        # Run program
        run_result = subprocess.run(run_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)

        output_text = ""
        if run_result.stdout:
            output_text += f"**Output:**\n```{run_result.stdout.decode()}```\n"
        if run_result.stderr:
            output_text += f"**Errors:**\n```{run_result.stderr.decode()}```"

        if not output_text:
            output_text = "No output."

        # Save to log
        RUN_LOGS.append(f"{language} run OK ({len(run_result.stdout)} bytes out)")
        if len(RUN_LOGS) > MAX_LOGS:
            RUN_LOGS.pop(0)

        # Send output
        if len(output_text) > 1800:
            output_file = f"{TEMP_DIR}/output.txt"
            with open(output_file, "w") as f:
                f.write(output_text)
            await interaction.followup.send(content="Output too long, sending as file:", file=discord.File(output_file))
        else:
            await interaction.followup.send(output_text)

    except subprocess.TimeoutExpired:
        await interaction.followup.send("Execution timed out.")
    except Exception as e:
        tb = traceback.format_exc()
        await interaction.followup.send(f"Error:\n```{tb}```")
    finally:
        # Cleanup temp files
        for f in os.listdir(TEMP_DIR):
            try:
                os.remove(os.path.join(TEMP_DIR, f))
            except Exception:
                pass

@tree.command(name="eval", description="Run code or files")
@app_commands.describe(flags="Command-line style flags, e.g. -l python -c 'print(123)'")
async def eval_command(interaction: discord.Interaction, flags: str):
    args = shlex.split(flags)
    
    if "-fl" in args:
        # Ask for file with specific instructions
        await interaction.response.send_message(
            "Please reply to this message with your file attached and mention @coderunner.bot in your message."
        )
        
        def check(m):
            return (
                m.author == interaction.user and
                client.user in m.mentions and
                bool(m.attachments) and
                m.channel == interaction.channel
            )
        
        try:
            msg = await client.wait_for('message', check=check, timeout=60.0)
            await interaction.followup.send("✅ File received! Processing...")
            await process_eval(interaction, args, msg.attachments)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out waiting for file. Please try again.", ephemeral=True)
    else:
        await interaction.response.defer(thinking=True)
        await process_eval(interaction, args, [])

@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user} (ID: {client.user.id})")
    print(f"Invite URL: https://discord.com/api/oauth2/authorize?client_id={client.user.id}&permissions=274878024704&scope=bot%20applications.commands")

client.run(TOKEN)
