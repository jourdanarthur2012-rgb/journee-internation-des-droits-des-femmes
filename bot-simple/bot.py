import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import json
import os
from datetime import datetime, timedelta
import typing
import shutil
import csv
from io import StringIO

# Configuration
TOKEN = "MTQ3NDkwMjI0OTA5OTYyNDU4MA.G1Oopk.JAIBeCE_tTBkKshav5ig1bOr1S2D8Y6gNickL8"  # Remplacez par votre token
RAPPORT_CHANNEL_ID = 1472466655220207697  # ID du salon où envoyer les rapports
ROLE_A_PING_ID = 1307681227486003320  # ID du rôle à ping
ROLE_SERVICE_ID = 1472083735888400474  # ID du rôle à ajouter/retirer
LOG_CHANNEL_ID = 1481010285333708921  # ID du salon de logs

# Fichier pour stocker les données
DATA_FILE = "service_data.json"
BACKUP_FILE = "service_data_backup.json"

# Initialisation du bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

class ServiceBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.service_data = {}
        self.load_data()
    
    async def setup_hook(self):
        # Démarrer la tâche de vérification
        self.check_long_service.start()
        await self.tree.sync()
        print(f"Commandes synchronisées")
    
    def check_disk_space(self):
        """Vérifie l'espace disque disponible"""
        try:
            total, used, free = shutil.disk_usage("/")
            free_mb = free // (2**20)
            print(f"Espace disque libre: {free_mb} MB")
            return free_mb > 10
        except:
            return True
    
    def load_data(self):
        """Charge les données depuis le fichier JSON"""
        if os.path.exists(DATA_FILE):
            try:
                if os.path.getsize(DATA_FILE) == 0:
                    print("Fichier de données vide, création d'un nouveau")
                    self.service_data = {}
                    return
                
                with open(DATA_FILE, 'r') as f:
                    self.service_data = json.load(f)
                print(f"Données chargées pour {len(self.service_data)} utilisateurs")
            except json.JSONDecodeError:
                print("Fichier de données corrompu, tentative de restauration...")
                self.restore_from_backup()
            except Exception as e:
                print(f"Erreur lors du chargement: {e}")
                self.service_data = {}
    
    def save_data(self):
        """Sauvegarde les données dans le fichier JSON avec gestion d'erreur"""
        try:
            if not self.check_disk_space():
                print("ERREUR: Espace disque insuffisant pour la sauvegarde")
                return False
            
            temp_file = DATA_FILE + ".tmp"
            with open(temp_file, 'w') as f:
                json.dump(self.service_data, f, indent=4)
            
            if os.path.exists(DATA_FILE):
                os.replace(temp_file, DATA_FILE)
            else:
                os.rename(temp_file, DATA_FILE)
            
            self.create_backup()
            print(f"Données sauvegardées pour {len(self.service_data)} utilisateurs")
            return True
            
        except OSError as e:
            if e.errno == 28:
                print("ERREUR CRITIQUE: Plus d'espace disque disponible!")
            else:
                print(f"Erreur lors de la sauvegarde: {e}")
            return False
        except Exception as e:
            print(f"Erreur inattendue lors de la sauvegarde: {e}")
            return False
    
    def create_backup(self):
        """Crée une sauvegarde des données"""
        try:
            if os.path.exists(DATA_FILE):
                shutil.copy2(DATA_FILE, BACKUP_FILE)
                print("Backup créé avec succès")
        except:
            pass
    
    def restore_from_backup(self):
        """Restaure les données depuis la backup"""
        try:
            if os.path.exists(BACKUP_FILE):
                with open(BACKUP_FILE, 'r') as f:
                    self.service_data = json.load(f)
                print("Données restaurées depuis la backup")
            else:
                print("Aucune backup trouvée, création de nouvelles données")
                self.service_data = {}
        except:
            print("Impossible de restaurer la backup")
            self.service_data = {}
    
    @tasks.loop(minutes=5)
    async def check_long_service(self):
        """Vérifie les services de plus de 2h sans pause"""
        for user_id, data in self.service_data.items():
            if data.get("is_active", False) and not data.get("is_paused", False):
                start = datetime.fromisoformat(data["service_start"])
                duration = (datetime.now() - start).total_seconds()
                if duration > 7200 and not data.get("reminded_2h", False):  # 2 heures
                    user = self.get_user(int(user_id))
                    if user:
                        try:
                            await user.send("⚠️ **RAPPEL** : Vous êtes en service depuis **2 heures** ! Pensez à faire une pause.")
                            data["reminded_2h"] = True
                            self.save_data()
                        except:
                            pass
                elif duration > 14400 and not data.get("reminded_4h", False):  # 4 heures
                    user = self.get_user(int(user_id))
                    if user:
                        try:
                            await user.send("⚠️ **RAPPEL IMPORTANT** : Vous êtes en service depuis **4 heures** ! Une pause est fortement recommandée.")
                            data["reminded_4h"] = True
                            self.save_data()
                        except:
                            pass

bot = ServiceBot()

# Fonction de logging
async def log_action(action: str, user: discord.Member, details: str = "", color: discord.Color = discord.Color.blue()):
    """Envoie un log dans le salon dédié"""
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title=f"📋 {action}",
            description=f"**Utilisateur:** {user.mention}\n**Détails:** {details}",
            color=color,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"ID: {user.id}")
        await channel.send(embed=embed)

# Vue principale comme sur la capture d'écran
class MainServiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Démarrer son service", style=discord.ButtonStyle.success, custom_id="main_start", row=0, emoji="▶️")
    async def main_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_service_action(interaction, "start")
    
    @discord.ui.button(label="Prendre / Terminer sa pause", style=discord.ButtonStyle.secondary, custom_id="main_pause", row=0, emoji="⏸️")
    async def main_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_service_action(interaction, "pause")
    
    @discord.ui.button(label="Terminer son service", style=discord.ButtonStyle.danger, custom_id="main_stop", row=0, emoji="⏹️")
    async def main_stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_service_action(interaction, "stop")
    
    async def handle_service_action(self, interaction: discord.Interaction, action: str):
        user_id = str(interaction.user.id)
        user_data = bot.service_data.get(user_id, {})
        
        if action == "start":
            if user_data.get("is_active", False):
                await interaction.response.send_message("❌ Vous êtes déjà en service !", ephemeral=True)
                return
            
            # Démarrer le service
            service_role = interaction.guild.get_role(ROLE_SERVICE_ID)
            if service_role:
                try:
                    await interaction.user.add_roles(service_role)
                except Exception as e:
                    print(f"Erreur ajout rôle: {e}")
            
            current_time = datetime.now()
            bot.service_data[user_id] = {
                "username": str(interaction.user),
                "is_active": True,
                "is_paused": False,
                "service_start": current_time.isoformat(),
                "pause_start": None,
                "total_service_time": user_data.get("total_service_time", 0),
                "current_session_start": current_time.isoformat(),
                "additional_time": user_data.get("additional_time", 0),
                "reminded_2h": False,
                "reminded_4h": False,
                "stats": user_data.get("stats", {
                    "total_services": 0,
                    "total_time": 0,
                    "pause_count": 0,
                    "total_pause_time": 0
                })
            }
            bot.save_data()
            
            embed = discord.Embed(
                title="✅ Service démarré",
                description=f"{interaction.user.mention} a commencé son service à {current_time.strftime('%H:%M')}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await log_action("Service démarré", interaction.user, f"Début: {current_time.strftime('%H:%M')}", discord.Color.green())
            
            # Mettre à jour l'affichage principal
            await self.update_main_message(interaction)
        
        elif action == "pause":
            if not user_data.get("is_active", False):
                await interaction.response.send_message("❌ Vous n'êtes pas en service !", ephemeral=True)
                return
            
            current_time = datetime.now()
            
            if user_data.get("is_paused", False):
                # Reprendre
                pause_start = datetime.fromisoformat(user_data["pause_start"])
                pause_duration = (current_time - pause_start).total_seconds()
                
                user_data["total_service_time"] += pause_duration
                user_data["is_paused"] = False
                user_data["pause_start"] = None
                
                if "stats" not in user_data:
                    user_data["stats"] = {}
                user_data["stats"]["total_pause_time"] = user_data["stats"].get("total_pause_time", 0) + pause_duration
                
                embed = discord.Embed(
                    title="⏯️ Service repris",
                    description=f"{interaction.user.mention} a repris son service après {self.format_duration(pause_duration)} de pause",
                    color=discord.Color.blue()
                )
                log_text = f"Reprise après {self.format_duration(pause_duration)}"
                log_color = discord.Color.blue()
            else:
                # Pause
                user_data["is_paused"] = True
                user_data["pause_start"] = current_time.isoformat()
                
                if "stats" not in user_data:
                    user_data["stats"] = {}
                user_data["stats"]["pause_count"] = user_data["stats"].get("pause_count", 0) + 1
                
                embed = discord.Embed(
                    title="⏸️ Pause",
                    description=f"{interaction.user.mention} est en pause depuis {current_time.strftime('%H:%M')}",
                    color=discord.Color.orange()
                )
                log_text = f"Pause débutée"
                log_color = discord.Color.orange()
            
            bot.save_data()
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await log_action("Pause/Reprise", interaction.user, log_text, log_color)
            
            # Mettre à jour l'affichage principal
            await self.update_main_message(interaction)
        
        elif action == "stop":
            if not user_data.get("is_active", False):
                await interaction.response.send_message("❌ Vous n'êtes pas en service !", ephemeral=True)
                return
            
            # Retirer le rôle
            service_role = interaction.guild.get_role(ROLE_SERVICE_ID)
            if service_role and service_role in interaction.user.roles:
                try:
                    await interaction.user.remove_roles(service_role)
                except Exception as e:
                    print(f"Erreur retrait rôle: {e}")
            
            # Calcul du temps
            session_start = datetime.fromisoformat(user_data["current_session_start"])
            session_end = datetime.now()
            session_duration = (session_end - session_start).total_seconds()
            
            total_time = user_data.get("total_service_time", 0) + session_duration
            if user_data.get("additional_time", 0) > 0:
                total_time += user_data["additional_time"]
            
            # Stats
            if "stats" not in user_data:
                user_data["stats"] = {}
            
            user_data["stats"]["total_services"] = user_data["stats"].get("total_services", 0) + 1
            user_data["stats"]["total_time"] = user_data["stats"].get("total_time", 0) + total_time
            user_data["stats"]["last_service"] = session_end.isoformat()
            
            if user_data["stats"]["total_services"] > 0:
                user_data["stats"]["avg_service_time"] = user_data["stats"]["total_time"] / user_data["stats"]["total_services"]
            
            hours = int(total_time // 3600)
            minutes = int((total_time % 3600) // 60)
            seconds = int(total_time % 60)
            time_str = f"{hours}h {minutes}m {seconds}s"
            
            # Réinitialiser
            user_data["is_active"] = False
            user_data["is_paused"] = False
            user_data["service_start"] = None
            user_data["pause_start"] = None
            user_data["current_session_start"] = None
            user_data["total_service_time"] = 0
            user_data["additional_time"] = 0
            user_data["reminded_2h"] = False
            user_data["reminded_4h"] = False
            
            bot.save_data()
            
            await log_action("Service terminé", interaction.user, f"Durée: {time_str}", discord.Color.red())
            
            # Ouvrir le formulaire
            modal = RapportVacation(user_id, time_str, interaction.user)
            await interaction.response.send_modal(modal)
            
            # Mettre à jour l'affichage principal
            await self.update_main_message(interaction)
    
    async def update_main_message(self, interaction: discord.Interaction):
        """Met à jour le message principal avec la liste des membres en service"""
        channel = interaction.channel
        message = await channel.fetch_message(interaction.message.id)
        
        # Compter les membres en service
        members_in_service = []
        for user_id, data in bot.service_data.items():
            if data.get("is_active", False):
                member = interaction.guild.get_member(int(user_id))
                if member:
                    status = "⏸️" if data.get("is_paused") else "✅"
                    members_in_service.append(f"{status} {member.mention} - {self.format_duration((datetime.now() - datetime.fromisoformat(data['service_start'])).total_seconds())}")
        
        # Créer le nouvel embed
        embed = discord.Embed(
            title="🕒 Service",
            description=f"**APP**\n{datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n---",
            color=discord.Color.blue()
        )
        
        if members_in_service:
            embed.add_field(
                name=f"📋 Utilisateur(s) en service - ({len(members_in_service)})",
                value="\n".join(members_in_service),
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Utilisateur(s) en service - (0)",
                value="Aucun utilisateur n'est en service... :(",
                inline=False
            )
        
        embed.add_field(
            name="",
            value="⚠️ Si le BOT ne répond pas, cela peut signifier qu'il redémarre\n\n---",
            inline=False
        )
        
        embed.set_footer(text="(modifié)")
        
        await message.edit(embed=embed)
    
    def format_duration(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

# Formulaire de rapport
class RapportVacation(discord.ui.Modal, title="📋 RAPPORT DE VACATION"):
    def __init__(self, user_id: int, total_time: str, rapporteur: discord.Member):
        super().__init__()
        self.user_id = user_id
        self.total_time = total_time
        self.rapporteur = rapporteur
    
    # 5 composants comme avant
    identite = discord.ui.TextInput(
        label="👤 1. IDENTITÉ",
        placeholder="Nom | Prénom | Matricule (opt) | Grade (opt)",
        required=True,
        max_length=200
    )
    
    prise_vacation = discord.ui.TextInput(
        label="📅 2. PRISE DE VACATION",
        placeholder="Date (JJ/MM/AAAA) | Début (HH:MM) | Fin (HH:MM)",
        required=True,
        max_length=30
    )
    
    equipage = discord.ui.TextInput(
        label="🚔 3. ÉQUIPAGE",
        placeholder="Véhicule | Effectif | Conducteur | Chef bord | Équipier (opt)",
        required=True,
        max_length=200
    )
    
    patrouille = discord.ui.TextInput(
        label="📍 4. PATROUILLE",
        placeholder="Secteurs empruntés (description précise)",
        required=True,
        max_length=500,
        style=discord.TextStyle.paragraph
    )
    
    pj_signature = discord.ui.TextInput(
        label="⚖️ 5. PJ & SIGNATURE",
        placeholder="Arme (Oui/Non) | Signature",
        required=True,
        max_length=200
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parsing (simplifié pour la lisibilité)
            parts = self.identite.value.split('|')
            nom = parts[0].strip() if len(parts) > 0 else "Non spécifié"
            prenom = parts[1].strip() if len(parts) > 1 else "Non spécifié"
            
            # Validation rapide
            if len(self.prise_vacation.value.split('|')) < 3:
                await interaction.followup.send("❌ Format: Date | Début | Fin", ephemeral=True)
                return
            
            # Envoi du rapport
            channel = bot.get_channel(RAPPORT_CHANNEL_ID)
            role = interaction.guild.get_role(ROLE_A_PING_ID)
            
            if channel:
                embed = discord.Embed(
                    title="📋 RAPPORT DE VACATION",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="👤 Identité", value=f"{nom} {prenom}", inline=False)
                embed.add_field(name="⏱️ Durée", value=self.total_time, inline=True)
                embed.add_field(name="📝 Rapport par", value=self.rapporteur.mention, inline=True)
                
                mention = role.mention if role else "@role"
                await channel.send(content=f"{mention} Nouveau rapport !", embed=embed)
                
                await interaction.followup.send("✅ Rapport envoyé !", ephemeral=True)
                await log_action("Rapport soumis", self.rapporteur, f"Pour {nom} {prenom}", discord.Color.green())
            
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur: {str(e)}", ephemeral=True)

# Commande principale
@bot.tree.command(name="service", description="Affiche le panneau de service principal")
async def service(interaction: discord.Interaction):
    """Affiche le panneau principal comme sur la capture d'écran"""
    
    # Compter les membres en service
    members_in_service = []
    for user_id, data in bot.service_data.items():
        if data.get("is_active", False):
            member = interaction.guild.get_member(int(user_id))
            if member:
                status = "⏸️" if data.get("is_paused") else "✅"
                duration = (datetime.now() - datetime.fromisoformat(data['service_start'])).total_seconds()
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                members_in_service.append(f"{status} {member.mention} - {time_str}")
    
    # Créer l'embed exactement comme sur la capture
    embed = discord.Embed(
        title="🕒 Service",
        description=f"**APP**\n{datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n---",
        color=discord.Color.blue()
    )
    
    if members_in_service:
        embed.add_field(
            name=f"📋 Utilisateur(s) en service - ({len(members_in_service)})",
            value="\n".join(members_in_service),
            inline=False
        )
    else:
        embed.add_field(
            name="📋 Utilisateur(s) en service - (0)",
            value="Aucun utilisateur n'est en service... :(",
            inline=False
        )
    
    embed.add_field(
        name="",
        value="⚠️ Si le BOT ne répond pas, cela peut signifier qu'il redémarre\n\n---",
        inline=False
    )
    
    embed.set_footer(text="(modifié)")
    
    # Ajouter la vue avec les boutons
    view = MainServiceView()
    
    await interaction.response.send_message(embed=embed, view=view)

# Commande admin pour ajouter du temps
@bot.tree.command(name="add", description="Ajoute du temps à un membre (Admin)")
@app_commands.describe(membre="Le membre", temps="10m, 1h, 30s")
async def add(interaction: discord.Interaction, membre: discord.Member, temps: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin seulement !", ephemeral=True)
        return
    
    try:
        if temps.endswith('s'):
            seconds = int(temps[:-1])
        elif temps.endswith('m'):
            seconds = int(temps[:-1]) * 60
        elif temps.endswith('h'):
            seconds = int(temps[:-1]) * 3600
        else:
            seconds = int(temps)
    except:
        await interaction.response.send_message("❌ Format: 10m, 1h, 30s", ephemeral=True)
        return
    
    user_id = str(membre.id)
    if user_id not in bot.service_data:
        bot.service_data[user_id] = {"additional_time": seconds, "stats": {}}
    else:
        bot.service_data[user_id]["additional_time"] = bot.service_data[user_id].get("additional_time", 0) + seconds
    
    bot.save_data()
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
    
    embed = discord.Embed(
        title="✅ Temps ajouté",
        description=f"**{time_str}** pour {membre.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)
    await log_action("Temps ajouté", interaction.user, f"{time_str} pour {membre}", discord.Color.gold())

@bot.event
async def on_ready():
    print(f"{bot.user} connecté !")
    print(f"Salon rapports: {RAPPORT_CHANNEL_ID}")
    print(f"Salon logs: {LOG_CHANNEL_ID}")
    print("✅ Bot prêt !")

if __name__ == "__main__":
    bot.run(TOKEN)
