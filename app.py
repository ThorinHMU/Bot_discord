import time
from discord.ext import commands, tasks
import discord
import requests
import json
import datetime
import mysql.connector
from config import sql_mc, TOKEN
import threading
import unidecode
import asyncio

instens = discord.Intents().all()
prexife = "t."
bot = commands.Bot(command_prefix=prexife, intents=instens, help_command=None)
bot_running = None
att_mess = {}
liste_log_option = ["message_edit", "verif_censure"]
sleep = threading.Event()
role_cache = None


class Button:
    def __init__(self, label, color, function):
        self.label = label
        self.color = color
        self.function = function


class Selecteur:
    def __init__(self, label, minim, maxi, option, function):
        self.label = label
        self.min = minim
        self.max = maxi
        self.option = option
        self.function = function


class SelecteurOption:
    def __init__(self, label, description, value):
        self.label = label
        self.description = description
        self.value = value


class Log:
    def __init__(self, guild, title, color, user, name, field: list, desc=""):
        self.guild: discord.Guild = guild
        self.title = title
        self.desc = desc
        self.color = color
        self.user: discord.Member = user
        self.name = name
        self.field = field

    def embed(self):
        embed = discord.Embed(title=self.title, type="rich", colour=self.color, description=self.desc)
        if self.user:
            embed.set_author(name=self.user.name, icon_url=self.user.avatar.url if self.user.avatar else
                             self.user.default_avatar.url)
        for i in self.field:
            embed.add_field(name=i["name"], value=i["values"], inline=i["inline"] if i.get("inline") else False)
        return embed

    async def send(self):
        with open("servers.json", "r") as file:
            file = json.load(file)
        guild_id = str(self.guild.id.__str__())
        serveur_info = file[guild_id]
        is_commande = self.name in [i.name for i in bot.commands]
        log_activate = await verif_serv_in_serveur_file([guild_id, "log_option", self.name], False)
        channel_log = serveur_info.get("channel_log_id")
        if log_activate and channel_log:
            if is_commande:
                await self.guild.get_channel(serveur_info["channel_log_id"]).send(embed=self.embed())
            else:
                await self.guild.get_channel(serveur_info["channel_log_id"]).send(embed=self.embed())


class View(discord.ui.View):
    def __init__(self, ctx, list_button):
        super().__init__()
        for i in list_button:
            if isinstance(i, Button):
                button: discord.ui.Button = discord.ui.Button(label=i.label, style=i.color)
                button.callback = lambda inter, btn=i: btn.function(inter) if inter.user == ctx.author \
                    else inter.response.defer()
                self.add_item(button)
            elif isinstance(i, Selecteur):
                select: discord.ui.Select = discord.ui.Select(placeholder=i.label,
                                                              min_values=i.min, max_values=i.max,
                                                              options=[discord.SelectOption(
                                                                  label=j.label,
                                                                  description=j.description,
                                                                  value=j.value) for j in i.option])
                select.callback = lambda inter, fi=i, slc=select: (
                    fi.function(inter, slc.values)) if inter.user == ctx.author \
                    else inter.response.defer()
                self.add_item(select)


async def verif_censure(message: discord.Message):

    mot_trouve = None

    # charge les donnés des serv
    servers_file = open("servers.json", "r")
    servers_file = json.load(servers_file)
    if not servers_file[str(message.guild.id)].get("censure"):
        servers_file[str(message.guild.id)]["censure"] = []
        servers_file_edit = open("servers.json", "w")
        json.dump(servers_file, servers_file_edit, indent=1)
        servers_file_edit.close()

    # verifie si le serveur est enregistré
    if str(message.guild.id) not in list(servers_file.keys()):
        return False

    # itaire sur la liste des mot censuré du serv + vérifi si un mot interdit est dans le message
    for mot_censure in servers_file[str(message.guild.id)]["censure"]:
        message_content = message.content.lower()
        message_content = "".join([unidecode.unidecode(i) if i.isalpha() else i for i in message_content])

        liste_indexe = [i for i in range(len(message_content)) if message_content[i].isalpha()]
        contract_mess = "".join([message_content[i] for i in liste_indexe])
        start = 0
        for i in range(contract_mess.count(mot_censure.replace(" ", ""))):
            index = contract_mess.index(mot_censure.replace(" ", ""), start)
            lettre = liste_indexe[index]
            lettre_2 = liste_indexe[index + len(mot_censure.replace(" ", "")) - 1]
            start = index + len(mot_censure.replace(" ", "")) - 1
            mot_av = message_content[lettre - 1] if lettre != 0 else "_"
            mot_ap = message_content[lettre_2 + 1] if lettre_2 + 1 < len(message_content) else "_"
            if not mot_ap.isalnum() and not mot_av.isalnum():
                mot_trouve = mot_censure
                break

    # si un mot est censure le message est suprimé est un log envoyé
    if mot_trouve:
        await message.delete()
        await (Log(guild=message.guild,
                   title="Censure !",
                   color=discord.Color(0xFF0000),
                   user=message.author,
                   name="verif_censure",
                   field=[{"name": "Channel", "values": message.channel.name},
                          {"name": "Message", "values": message.content, "inline": True},
                          {"name": "Mot Censuré", "values": mot_trouve, "inline": True}]).send())


async def verif_serv_in_serveur_file(path, value=None):
    server_file = open("servers.json", "r")
    server_file = json.load(server_file)
    source = server_file
    for j in path:
        if j not in source.keys():
            if j != path[-1] or (value is not None):
                source[j] = value if j == path[-1] else {}
            with open("servers.json", "w") as server_file_edit:
                json.dump(server_file, server_file_edit, indent=1)
        source = source.get(j)
    return source


@bot.event
async def on_message(ctx: discord.Message):
    if not isinstance(ctx.channel, discord.DMChannel):

        await verif_serv_in_serveur_file([str(ctx.guild.id)], {})
        global att_mess
        if att_mess:
            if att_mess["channel"] == ctx.channel and att_mess["user"] == ctx.author:
                if att_mess["type"] in ["supre", "add_mot", "role_color"]:
                    await att_mess["function"](ctx)
            await bot.process_commands(ctx)
            return
        if ctx.author != bot.user:
            await verif_censure(message=ctx)
            with open("messages.json", "r") as file:
                file = json.load(file)
            file[str(ctx.id)] = ctx.content
            with open("messages.json", "w") as file_edit:
                json.dump(file, file_edit)
    await bot.process_commands(ctx)


@bot.event
async def on_raw_message_edit(ctx: discord.RawMessageUpdateEvent):

    msg = await bot.get_guild(ctx.guild_id).get_channel(ctx.channel_id).fetch_message(ctx.message_id)
    if isinstance(msg.channel, discord.DMChannel):
        return
    if msg.author == bot.user:
        return
    guild_id = str(msg.guild.id)
    channel_id = str(msg.channel.id)

    with open("messages.json", "r") as file:
        file = json.load(file)
    if ctx.cached_message:
        ancien_message = ctx.cached_message.content
    else:
        ancien_message = file.get(str(msg.id)) if file.get(str(msg.id)) else "Message Inconnu"
    with open("messages.json", "w") as file_edit:
        file[str(msg.id)] = msg.content
        json.dump(file, file_edit)
    await verif_serv_in_serveur_file([guild_id, "log_option", "message_edit"], False)

    with open("servers.json", "r") as file:
        file = json.load(file)
        log_activate = file.get(guild_id).get("log_option").get("message_edit")
    if log_activate:
        await Log(msg.guild, "Message Modifié", discord.Color(0xFDDB00),
                  msg.author, "message_edit", [
                      {"name": "Ancien message", "values": f"{ancien_message}"},
                      {"name": "Nouveau message", "values": f"{msg.content}"},
                      {"name": "Lien", "values": f"https://discord.com/channels/"
                                                 f"{guild_id}/{channel_id}/{msg.id}"}]).send()
    if msg.author != bot.user:
        await verif_censure(msg)


@bot.event
async def on_guild_role_create(role: discord.Role):
    description = (f"Nom: {role.name}\n"
                   f"Mentionnable: {role.mentionable}\n"
                   f"Affiché a part: {role.hoist}\n"
                   f"Couleur HTML: {role.color}"
                   f"   Permissions:\n"
                   f"-{'\n -'.join([i[0] for i in role.permissions if i[1]])}")
    log = [i async for i in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create)]
    if role.id == role_cache:
        return
    await Log(role.guild, "Role crée", discord.Color(0x54FD00), log[0].user, "creer_role",
              field=[{"name": "Source", "values": "discord"}], desc=description).send()


@bot.event
async def on_guild_role_update(_, role: discord.Role):
    log = [i async for i in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update)]
    if not log[0].target == role:
        return

    description = (f"Nom: {role.name}\n"
                   f"Mentionnable: {role.mentionable}\n"
                   f"Affiché a part: {role.hoist}\n"
                   f"Couleur HTML: {role.colour}\n"
                   f"   Permissions:\n"
                   f"-{'\n -'.join([i[0] for i in role.permissions if i[1]])}")
    await Log(role.guild, "Role Modifié", discord.Color(0xFDDB00), log[0].user, "creer_role",
              field=[{"name": "Source", "values": "discord"}], desc=description).send()


# met a jour le nom du role entré
async def update_role_name(ctx: discord.Message, old_ctx, args_role, inter):
    global att_mess
    att_mess = {}
    args_role.update({"name": ctx.content})
    await menu_role(old_ctx, args_role, inter)
    await ctx.delete()


# demande d'écrire le nom du role
async def requete_role_name(inter: discord.Interaction, ctx: commands.Context, args_role):
    if inter.user != ctx.author:
        await inter.response.defer()
        return
    embed = inter.message.embeds[0]
    embed.add_field(name="Action: ", value="Entrez le nom du rôle", inline=False)
    await inter.response.edit_message(embed=embed, view=View(ctx,
                                                             [Button("Annuler",
                                                                     discord.ButtonStyle.red,
                                                                     lambda finter: menu_role(ctx,
                                                                                              args_role,
                                                                                              finter))]))
    global att_mess
    att_mess["channel"] = ctx.channel
    att_mess["user"] = ctx.author
    att_mess["type"] = "role_color"
    att_mess["function"] = lambda ctx_new: update_role_name(ctx_new, ctx, args_role, inter)


async def update_role_perms_slc(value, inter: discord.Interaction, role_perm_slc):
    role_perm_slc[inter.data.get("custom_id")] = value
    await inter.response.defer()


async def update_role_perms(inter, ctx, args_perms, role_perm_slc: dict):
    args_perms["permissions"] = discord.Permissions(0)
    for i in role_perm_slc.values():
        args_perms["permissions"] = discord.Permissions(args_perms.get("permissions").value + sum([int(j) for j in i]))
    await menu_role(ctx, args_perms, inter)


async def requete_role_perms(inter: discord.Interaction, ctx: commands.Context, args_role):
    if inter.user != ctx.author:
        await inter.response.defer()
        return
    menu_slc = 15
    liste_perms = []
    for i in range(len(list(discord.Permissions.all())) // menu_slc +
                   (1 if len(list(discord.Permissions.all())) % menu_slc else 0)):
        liste_perms.append([(j[0], eval(f"discord.Permissions.{j[0]}.flag"))
                            for j in list(discord.Permissions.all())[menu_slc * i:menu_slc * i + menu_slc]])

    embed = inter.message.embeds[0]
    embed.add_field(name="Action: ", value="Choisissez les perms du role", inline=False)

    role_perm_slc = {}
    await inter.response.edit_message(embed=embed, view=View(ctx,
                                                             [
                                                                 Selecteur(
                                                                     "Permissions",
                                                                     1,
                                                                     len(i),
                                                                     [SelecteurOption(
                                                                         j[0],
                                                                         "",
                                                                         str(j[1])) for j in i],
                                                                     lambda finter, value:
                                                                     update_role_perms_slc(value, finter,
                                                                                           role_perm_slc))
                                                                 for i in liste_perms] + [
                                                                 Button("Valider",
                                                                        discord.ButtonStyle.green,
                                                                        lambda finter:
                                                                        update_role_perms(finter, ctx,
                                                                                          args_role, role_perm_slc)),
                                                                 Button("Annuler",
                                                                        discord.ButtonStyle.secondary,
                                                                        lambda finter:
                                                                        menu_role(ctx, args_role, finter))]))


async def update_role_display(value, ctx, args_role, inter):
    args_role.update({"hoist": value})
    await menu_role(ctx, args_role, inter)


async def requete_display_role(inter: discord.Interaction, ctx: commands.Context, args_role):
    if inter.user != ctx.author:
        await inter.response.defer()
        return
    embed = inter.message.embeds[0]
    embed.add_field(name="Action: ", value="Afficher ou nom le role a part", inline=False)
    active = Button("Activer", discord.ButtonStyle.green, lambda finter: update_role_display(True,
                                                                                             ctx,
                                                                                             args_role,
                                                                                             finter))
    disabled = Button("Desactiver", discord.ButtonStyle.red, lambda finter: update_role_display(False,
                                                                                                ctx,
                                                                                                args_role,
                                                                                                finter))
    button_list = []
    if not args_role.get("hoist"):
        button_list.append(active)
    if args_role.get("hoist") is not False:
        button_list.append(disabled)
    button_list.append(Button("Annuler", discord.ButtonStyle.secondary, lambda finter: menu_role(ctx,
                                                                                                 args_role,
                                                                                                 finter)))

    await inter.response.edit_message(embed=embed,
                                      view=View(ctx,
                                                button_list))


async def update_role_mentionnable(value, ctx, args_role, inter):
    args_role.update({"mentionable": value})
    await menu_role(ctx, args_role, inter)


async def requete_mentionnable_role(inter: discord.Interaction, ctx: commands.Context, args_role):
    if inter.user != ctx.author:
        await inter.response.defer()
        return
    embed = inter.message.embeds[0]
    embed.add_field(name="Action: ", value="Role Mentionable ", inline=False)
    active = Button("Activer", discord.ButtonStyle.green, lambda finter: update_role_mentionnable(True,
                                                                                                  ctx,
                                                                                                  args_role,
                                                                                                  finter))
    disabled = Button("Desactiver", discord.ButtonStyle.red, lambda finter: update_role_mentionnable(False,
                                                                                                     ctx,
                                                                                                     args_role,
                                                                                                     finter))
    button_list = []
    if not args_role.get("mentionable"):
        button_list.append(active)
    if args_role.get("mentionable") is not False:
        button_list.append(disabled)
    button_list.append(Button("Annuler", discord.ButtonStyle.secondary, lambda finter: menu_role(ctx,
                                                                                                 args_role,
                                                                                                 finter)))

    await inter.response.edit_message(embed=embed,
                                      view=View(ctx,
                                                button_list))


# met a jour la couleur du role
async def update_role_color(ctx: discord.Message, old_ctx, args_role, inter):
    global att_mess
    att_mess = {}
    args_role.update({"color": eval(f"0x{ctx.content.lstrip("#")}")})
    await menu_role(old_ctx, args_role, inter)
    await ctx.delete()


# demande d'écrire la couleur du role au format html ex: FFFFFF, #FFFFFF
async def requete_role_color(inter: discord.Interaction, ctx: commands.Context, args_role):

    if inter.user != ctx.author:
        await inter.response.defer()
        return
    embed = inter.message.embeds[0]
    embed.add_field(name="Action: ", value="Entrez une couleur au format Hex\nhttps://g.co/kgs/Kym4F5D", inline=False)
    await inter.response.edit_message(embed=embed, view=View(ctx,
                                                             [Button("Annuler",
                                                                     discord.ButtonStyle.red,
                                                                     lambda finter: menu_role(ctx,
                                                                                              args_role,
                                                                                              finter))]))
    global att_mess
    att_mess["channel"] = ctx.channel
    att_mess["user"] = ctx.author
    att_mess["type"] = "role_color"
    att_mess["function"] = lambda ctx_new: update_role_color(ctx_new, ctx, args_role, inter)


async def valide_cree_role(inter: discord.Interaction, ctx: commands.Context, args_role):
    global role_cache

    role = await ctx.guild.create_role(**args_role)
    role_cache = role.id

    await inter.response.edit_message(view=None, embed=discord.Embed(title=f"Rôle {role.name} crée avec succés",
                                                                     color=discord.Color(0x54FD00)))

    liste_perms = []
    liste_perms_final = [[], []]
    max_car = 0
    if args_role.get("permissions"):
        for i in list(args_role.get("permissions")):
            if i[1]:
                liste_perms.append(i[0])
                if len(i[0]) > max_car and liste_perms.index(i[0]) % 2 + 1:
                    max_car = len(i[0])
    for i in liste_perms:
        liste_perms_final[liste_perms.index(i) % 2].append(i)

    descr = f"**᲻᲻᲻᲻᲻᲻᲻᲻᲻᲻** __**{args_role.get('name')}**__\n"\
            f"{f'Couleur HTML: {hex(args_role.get('color'))}\n'
                if args_role.get('color') else ''}"\
            f"{f'Role Mentionnable: '
               f'{'Oui' if args_role.get('mentionable') else "Non"}\n'
                if args_role.get('mentionable') is not None else ''}"\
            f"{f'Role Affiché a part: '
               f'{'Oui' if args_role.get('hoist') else "Non"}\n'
                if args_role.get('hoist') is not None else ''}"\
            f"{f'Permissions:\n\n' if liste_perms else ''}"

    await Log(ctx.guild, "Role crée", discord.Color(0x54FD00), ctx.author, "creer_role",
              [{"name": "", "values": "\n".join(liste_perms_final[0]), "inline": True},
               {"name": "", "values": "\n".join(liste_perms_final[1]), "inline": True}],
              descr).send()


async def menu_role(ctx, args_role, inter=None):
    if inter:
        assert isinstance(inter, discord.Interaction)

    liste_perms = []
    liste_perms_final = [[], []]
    max_car = 0
    if args_role.get("permissions"):
        for i in list(args_role.get("permissions")):
            if i[1]:
                liste_perms.append(i[0])
                if len(i[0]) > max_car and liste_perms.index(i[0]) % 2 + 1:
                    max_car = len(i[0])
    for i in liste_perms:
        liste_perms_final[liste_perms.index(i) % 2].append(i)

    embed = discord.Embed(title="Création Du role",
                          description=f"1️⃣ - Changer le Nom\n"
                                      f"2️⃣ - Permissions\n"
                                      f"3️⃣ - Affiché a part des autres roles\n"
                                      f"4️⃣ - Mentionnable\n"
                                      f"5️⃣ - Couleur\n"
                                      f"\n"
                                      f"Role:\n\n"
                                      f"**᲻᲻᲻᲻᲻᲻᲻᲻᲻᲻** __**{args_role.get('name')}**__\n"
                                      f"{f'Couleur HTML: {hex(args_role.get('color'))}\n'
                                         if args_role.get('color') else ''}"
                                      f"{f'Role Mentionnable: '
                                         f'{'Oui' if args_role.get('mentionable') else "Non"}\n'
                                         if args_role.get('mentionable') is not None else ''}"
                                      f"{f'Role Affiché a part: '
                                         f'{'Oui' if args_role.get('hoist')else "Non"}\n'
                                         if args_role.get('hoist') is not None else ''}"    
                                      f"{f'Permissions:\n\n'if liste_perms else ''}",
                          color=args_role.get('color') if args_role.get('color') else 0x99AAB5)
    embed.add_field(name="", value="\n".join(liste_perms_final[0]), inline=True)
    embed.add_field(name="", value="\n".join(liste_perms_final[1]), inline=True)
    view = View(ctx,
                [Button("1️⃣",
                        discord.ButtonStyle.green,
                        lambda finter: requete_role_name(finter, ctx, args_role)),
                 Button("2️⃣",
                        discord.ButtonStyle.green,
                        lambda finter: requete_role_perms(finter, ctx, args_role)),
                 Button("3️⃣",
                        discord.ButtonStyle.green,
                        lambda finter: requete_display_role(finter, ctx, args_role)),
                 Button("4️⃣",
                        discord.ButtonStyle.green,
                        lambda finter: requete_mentionnable_role(finter, ctx, args_role)),
                 Button("5️⃣",
                        discord.ButtonStyle.green,
                        lambda finter: requete_role_color(finter, ctx, args_role)),
                 Button("Valider",
                        discord.ButtonStyle.green,
                        lambda finter: valide_cree_role(finter, ctx, args_role))])
    if not inter:
        await ctx.send(embed=embed, view=view)
    else:
        if inter.response.is_done():
            await inter.edit_original_response(embed=embed, view=view)
        else:
            await inter.response.edit_message(embed=embed, view=view)


@bot.command()
async def creer_role(ctx: commands.Context, nom_role):
    if isinstance(ctx.channel, discord.DMChannel):
        return
    await ctx.message.delete()
    args_role = {"name": nom_role}
    await menu_role(ctx, args_role)

    await Log(ctx.guild,
              "Commande",
              discord.Color(0x0000FF),
              None,
              "creer_role",
              [{"name": f"Channel", "values": ctx.channel.name, "inline": True},
               {"name": "user", "values": ctx.author.name, "inline": True},
               {"name": "commande", "values": f"{prexife}creer_role"}]).send()


# demande le mot a supprimer/ajouter
async def request_chosen_word(inter: discord.Interaction, embed, ctx, name, value, type_mess, func):
    if inter.user != ctx.author:
        await inter.response.defer()
        return
    global att_mess
    embed.add_field(name=name, value=value)
    await inter.response.edit_message(embed=embed,
                                      view=View(ctx, [
                                          Button("Annuler", discord.ButtonStyle.grey,
                                                 lambda inter_2: reset_embed_censure(inter_2, ctx))]))
    att_mess["channel"] = inter.channel
    att_mess["user"] = ctx.author
    att_mess["type"] = type_mess
    att_mess["function"] = lambda ctx_new: func(ctx_old=inter, ctx=ctx_new, ctx_best=ctx,
                                                func="add" if type_mess == "add_mot" else 'remove')


# retourne a l'embed de la liste des mots
async def reset_embed_censure(inter, ctx):
    if inter.user != ctx.author:
        await inter.response.defer()
        return
    global att_mess

    server_file = open("servers.json", "r")
    server_file = json.load(server_file)

    embed = discord.Embed(
        title='Mot Interdit',
        description=" / ".join(server_file[str(ctx.guild.id)]["censure"]))
    await inter.response.edit_message(embed=embed, view=View(ctx, list_button=[
        Button("Supprimer", discord.ButtonStyle.red,
               lambda finter: request_chosen_word(finter, embed, ctx,
                                                  name="Supprimer", value="Ecrivez le mot à supprimer",
                                                  type_mess="supre", func=update_word_censure)),
        Button("Ajouter", discord.ButtonStyle.green,
               lambda finter: request_chosen_word(finter, embed, ctx,
                                                  name="Ajouter", value="Ecrivez le mot à rajouter",
                                                  type_mess="add_mot", func=update_word_censure)),
        Button("Finit", discord.ButtonStyle.secondary,
               lambda inter_2: inter_2.response.edit_message(view=None))]))
    att_mess = {}


# supprime/ajoute le mot une fois choisit
async def update_word_censure(ctx_old, ctx, ctx_best, func: str):
    global att_mess
    assert isinstance(ctx_best, commands.Context)
    server_file = open("servers.json", "r")
    server_file = json.load(server_file)
    mot_aj = []
    for mot in ctx.content.split(", "):
        if mot not in server_file[str(ctx.guild.id)]["censure"] and func == "add":
            server_file[str(ctx.guild.id)]["censure"].append(mot)
            mot_aj.append(unidecode.unidecode(mot))
        elif mot in server_file[str(ctx.guild.id)]["censure"] and func == "remove":
            server_file[str(ctx.guild.id)]["censure"].remove(mot)
            mot_aj.append(mot)
    server_file_edit = open("servers.json", "w")
    json.dump(server_file, server_file_edit, indent=1)
    server_file_edit.close()
    if func == "add":
        embed_liste = ["Mot(s) Ajouté(s):", "Auncun Mot Ajouté:", "Ce(s) mot figure deja dans la liste"]
    else:
        embed_liste = ["Mot Supprimé:", "Auncun Mot Supprimé:", "ce mot ne figure pas dans la liste"]
    if mot_aj:
        embed = discord.Embed(title=embed_liste[0], description=mot_aj)
    else:
        embed = discord.Embed(title=embed_liste[1], description=embed_liste[2])
    await ctx.delete()
    att_mess = {}
    date = ctx_best.message.created_at
    await ctx_old.message.edit(embed=embed, view=View(ctx_best, [
        Button("OK", discord.ButtonStyle.success, lambda inter: reset_embed_censure(inter, ctx_best))]))
    await Log(guild=ctx_best.guild,
              title=f"Mot censuré {'Rajouté' if func == 'add' else 'Supprimé'}",
              color=discord.Color(0x54FD00) if func == "add" else discord.Color(0xFD0000),
              user=ctx_best.author, name="censure",
              field=[
                  {"name": "Channel", "values": ctx_best.channel},
                  {"name": "Le", "values": f"{date.day}/{date.month}/{date.year}", "inline": True},
                  {"name": "a", "values": f"{date.hour}:{date.minute}:{date.second}", "inline": True},
                  {"name": embed_liste[0], "values": mot_aj}]).send()


@bot.command()
async def censure(ctx: discord.ext.commands.Context):
    if isinstance(ctx.channel, discord.DMChannel):
        return

    await ctx.message.delete()
    servers_file = open("servers.json", "r")
    servers_file = json.load(servers_file)
    if not servers_file[str(ctx.guild.id)].get("censure"):
        servers_file[str(ctx.guild.id)]["censure"] = []
        servers_file_edit = open("servers.json", "w")
        json.dump(servers_file, servers_file_edit, indent=1)
        servers_file_edit.close()

    liste_mot_censure = servers_file[str(ctx.guild.id)]["censure"]
    embed = discord.Embed(title="Mot Interdit", description=" / ".join(liste_mot_censure))
    await ctx.channel.send(embed=embed, view=View(ctx, [
        Button("Supprimer", discord.ButtonStyle.red,
               lambda inter: request_chosen_word(inter, embed, ctx,
                                                 name="Supprimer", value="Ecrivez le mot à supprimer",
                                                 type_mess="supre", func=update_word_censure)),
        Button("Ajouter", discord.ButtonStyle.green,
               lambda inter: request_chosen_word(inter, embed, ctx,
                                                 name="Ajouter", value="Ecrivez le mot à rajouter",
                                                 type_mess="add_mot", func=update_word_censure)),
        Button("Finit", discord.ButtonStyle.secondary,
               lambda inter_2: inter_2.response.edit_message(view=None))]))

    await Log(title=f"Commande exécuté",
              color=discord.Color(0x0000FF),
              guild=ctx.guild,
              user=None,
              name="censure",
              field=[{"name": "Channel", "values": ctx.channel.name, "inline": True},
                     {"name": "User", "values": ctx.author.name, "inline": True},
                     {"name": "commande", "values": f"{prexife}censure"}]).send()


async def set_log_salon_2(inter: discord.Interaction, values):
    server_file = open("servers.json", "r")
    server_file = json.load(server_file)
    server_file[str(inter.guild.id)]["channel_log_id"] = int(values[0]) if values else ""
    server_file_edit = open("servers.json", "w")
    json.dump(server_file, server_file_edit, indent=1)
    server_file_edit.close()
    date = datetime.datetime.now()
    await inter.response.edit_message(
        content=f"Channel choisit {inter.guild.get_channel(int(values[0])) if values[0] else 'Aucun'}",
        view=None)
    await (Log(guild=inter.guild,
               title="Salon de log Définit",
               color=discord.Color(0xFDDB00),
               user=inter.user,
               name="set_log_salon",
               field=[
                  {"name": "Le", "values": f"{date.day}/{date.month}/{date.year}", "inline": True},
                  {"name": "à", "values": f"{date.hour}:{date.minute}:{date.second}", "inline": True},
                  {"name": "Salon Log:", "values": inter.guild.get_channel(int(values[0])) if values else 'Aucun'}])
           .send())


@bot.command()
async def set_log_salon(ctx: commands.Context):
    if isinstance(ctx.channel, discord.DMChannel):
        return
    await ctx.message.delete()
    server_file = open("servers.json", "r")
    server_file = json.load(server_file)
    channel_log = server_file[str(ctx.guild.id)].get("channel_log_id")
    await ctx.send(
        "Choisit un channel pour les logs",
        view=View(ctx,
                  list_button=[
                      Selecteur("Channel", 1, 1,
                                [SelecteurOption("Aucun",
                                                 'selection actuel' if not channel_log else "", 0)] +
                                [SelecteurOption(i.name,
                                                 'selection actuel' if channel_log == i.id else "",
                                                 i.id) for i in
                                 sorted([i for i in ctx.guild.channels if type(i) is discord.TextChannel and
                                         i.permissions_for(ctx.author).read_messages],
                                        key=lambda x: x.category.position if x.category else -1)],
                                lambda inter, values: set_log_salon_2(inter, values))]))

    await Log(ctx.guild, "Commande", discord.Color(0x0000FF),
              None, "set_log_salon", [
                  {"name": "Channel", "values": ctx.channel.name, "inline": True},
                  {"name": "user", "values": ctx.author.name, "inline": True},
                  {"name": "commande", "values": f"{prexife}set_log_salon"}]).send()


async def reset_embed_log_option(inter: discord.Interaction, ctx):
    embed = discord.Embed(title="Log Options")
    liste_log_option_serv = []
    for i in liste_log_option:
        await verif_serv_in_serveur_file([str(ctx.guild.id), "log_option", i], False)
        with open("servers.json", "r") as file:
            file = json.load(file)
            liste_log_option_serv.append([i, file.get(str(ctx.guild.id)).get('log_option').get(i)])
    embed.description = "\n".join([f"{i[0]}: {i[1]}" for i in liste_log_option_serv])
    await inter.response.edit_message(
        embed=embed,
        view=View(

            ctx, [
                Selecteur("options", 1, 1,
                          [SelecteurOption(j[0], j[1], str([j[0], j[1]])) for j in liste_log_option_serv],
                          lambda finter, value: log_option_2(finter, value, ctx))]))


@bot.command()
async def clear(ctx: commands.Context, nbr: str):
    await ctx.message.delete()
    if not nbr.isdigit():
        return
    if not 100 > int(nbr) > 0:
        return
    messages_supirme = [(f"▶️ De: {i.author} "
                         f"Le: {i.created_at.day}/{i.created_at.month}/{i.created_at.year} "
                         f"A: {i.created_at.hour}:{i.created_at.minute}:{i.created_at.second} ◀️\n\n "
                         f"{i.content}") async
                        for i in ctx.channel.history(limit=int(nbr))][::-1]
    await ctx.channel.purge(limit=int(nbr))
    if isinstance(ctx.channel, discord.DMChannel):
        return
    await Log(ctx.guild, "Clear", discord.Color(0x731010),
              ctx.author, "clear", [
                  {"name": "Channel", "values": ctx.channel.name},
                  {"name": "Nombre de messages supprimés", "values": nbr}],
              ("\n"+"-"*40+"\n").join(messages_supirme)).send()


async def set_log_option(inter, option, value, ctx: commands.Context):
    with open("servers.json", "r") as file:
        file = json.load(file)
    file[str(ctx.guild.id)]["log_option"][option] = value
    with open("servers.json", "w") as file_edit:
        json.dump(file, file_edit, indent=1)
    await reset_embed_log_option(inter, ctx)
    await Log(ctx.guild, "Log Option", discord.Color.yellow(), ctx.author, "set_log_option",
              [
            {"name": "channel", "values": ctx.channel.name},
            {"name": "option", "values": f"log de {option} {'Activé' if value else 'Désativé'}"}]).send()


async def log_option_2(inter: discord.Interaction, value, ctx):
    value = eval(value[0])
    embed = discord.Embed(title="Log Option")
    embed.add_field(name="Option Select:", value=value[0])
    await inter.response.edit_message(embed=embed,
                                      view=View(ctx,
                                                [
                                                    Button("Acitiver" if not value[1] else "Désactiver",
                                                           discord.ButtonStyle.green,
                                                           lambda finter: set_log_option(
                                                               finter,
                                                               value[0],
                                                               True if not value[1] else False,
                                                               ctx)),
                                                    Button("Annuler",
                                                           discord.ButtonStyle.red,
                                                           lambda finter: reset_embed_log_option(finter, ctx))]))


@bot.command()
async def log_option(ctx: commands.Context):
    if isinstance(ctx.channel, discord.DMChannel):
        return
    embed = discord.Embed(title="Log Options")
    liste_log_option_serv = []
    for i in liste_log_option:
        await verif_serv_in_serveur_file([str(ctx.guild.id), "log_option", i], False)
        with open("servers.json", "r") as file:
            file = json.load(file)
            liste_log_option_serv.append([i, file.get(str(ctx.guild.id)).get('log_option').get(i)])
    embed.description = "\n".join([f"{i[0]}: {i[1]}" for i in liste_log_option_serv])
    await ctx.send(view=View(
        ctx,
        [
            Selecteur("options", 1, 1, [
                SelecteurOption(j[0], j[1], str([j[0], j[1]]))
                for j in liste_log_option_serv],
                      lambda inter, value: log_option_2(inter, value, ctx))]),
        embed=embed)

    await Log(ctx.guild, f"Commande exécuté", discord.Color(0x0000FF),
              None, "log_option", [
         {"name": "channel", "values": ctx.channel.name, "inline": True},
         {"name": "User", "values": ctx.author.name, "inline": True},
         {"name": f"commande", "values": f"{prexife}log_option"}]).send()


async def update_statu_discord(values):
    try:
        statue = "✅ En ligne" if values[2] else "❌ Hors ligne"
        guild = bot.get_guild(925007224131174431)
        channel = guild.get_channel(1122257610855436398)

        with open("file.json", "r") as file:
            file = json.load(file)
            message_id = int(file["message"]["id"])
            message = await channel.fetch_message(message_id)
        embed = discord.Embed(title="Unknow Survival", description=statue, color=discord.Color.green())
        embed.add_field(name="Heure", value=datetime.datetime.fromtimestamp(values[1]), inline=False)
        embed.add_field(name="Nombres de joueurs", value=f"{str(len(eval(values[3])))}/20")
        embed.add_field(name="Joueurs", value=", ".join(eval(values[3])) if eval(values[3]) else "❌")
        if channel.last_message_id == message_id:
            await message.edit(embed=embed)
        else:
            message = await channel.send(embed=embed)
            file["message"]["id"] = message.id
            print(message.id, file)
            with open("file.json", "w") as file_edit:
                json.dump(file, file_edit)
    except Exception as erreur:
        print(erreur)


def sql(data_base, mode="GET", **kwargs):
    cursor = None
    connection = None
    try:

        # Établir la connexion
        connection = mysql.connector.connect(
            host=data_base.host,
            port=data_base.port,
            user=data_base.user,
            password=data_base.password,
            database=data_base.database
        )
        # Créer un curseur pour exécuter des requêtes SQL
        cursor = connection.cursor()
        if mode == "SET":
            # Exemple d'insertion d'une ligne dans une table
            table_name = kwargs["table_name"]
            columns = kwargs["columns"]
            values = kwargs["values"]
            print(values)

            # Créer la requête d'insertion
            query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(['%s' for _ in values])})"

            # Exécuter la requête
            cursor.execute(query, values)

            # Valider la transaction
            connection.commit()
            print("Ligne ajoutée avec succès!")

        elif mode == "GET":
            table_name = kwargs["table_name"]
            selecteur = kwargs.get("selecteur") if kwargs.get("selecteur") else "*"

            # Créer la requête de séléction
            query = f"SELECT {selecteur} FROM {table_name}"

            cursor.execute(query)
            return cursor.fetchall()

    except mysql.connector.Error as err:
        print(f"Erreur MySQL : {err}")
    except Exception as err:
        print(err)

    finally:
        # Fermer le curseur et la connexion
        if 'cursor' in locals() and cursor is not None:
            cursor.close()

        if 'connection' in locals() and connection.is_connected():
            connection.close()
            print("Connexion MySQL fermée")


def stat_serv():
    global bot_running
    while bot_running:
        try:
            date = datetime.datetime.now()

            file = open("file.json", "r")
            file = json.load(file)
            req = requests.request("GET",
                                   url="https://minecraft-api.com/api/ping/game10-fr.hosterfy.com/60075/json",
                                   timeout=15)
            if "Failed" in req.text:
                new_statue = ["offline", "0/?", ""]
                liste_joueur = []
            else:
                liste_joueur = [i["name"] for i in req.json()["players"]["sample"]] if req.json()["players"][
                    "online"] else []
                liste_joueur.sort()
                new_statue = [f"online",
                              f"{len(liste_joueur)}/{req.json()['players']['max']}",
                              ", ".join(liste_joueur)]
            if new_statue != [file["stat_serv"]["stat"], file["stat_serv"]["nbr_players"],
                              file["stat_serv"]["list_players"]]:

                ids = len(sql(sql_mc, table_name="stat"))
                values = [ids, date.timestamp().__int__(), int(new_statue[0] == "online"), str(liste_joueur)]
                sql(sql_mc, table_name="stat", mode="SET", columns=["id", "time", "online", "players"],
                    values=[ids, date.timestamp().__int__(), int(new_statue[0] == "online"), str(liste_joueur)])

                file_edit = open("file.json", "w")
                file["stat_serv"] = {"stat": new_statue[0], "nbr_players": new_statue[1], "list_players": new_statue[2]}
                json.dump(file, file_edit)
                file_edit.close()
                asyncio.run_coroutine_threadsafe(update_statu_discord(values), bot.loop)
        except Exception as er:
            print(er)
        sleep.wait(20)


@bot.event
async def on_ready():
    global bot_running, liste_log_option

    bot_running = True
    liste_log_option += [i.name for i in bot.commands]
    print("pret")
    print(datetime.datetime.now())
    threading.Thread(target=stat_serv).start()


def stop():
    global bot_running, sleep
    bot_running = False
    sleep.set()
    print("Bot arrété")


bot.run(TOKEN)
stop()
