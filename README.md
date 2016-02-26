# LiF:YO stats changer
This is a very simple web interface to change a character's attributes and combat skill levels.


## Setup
Required python libraries (can be installed through pip):
  * cherrypy
  * PyMySQL

in change_stats.py:
  * adjust mysql settings for LiF database
  * adjust skillcap/attribute cap to match your LiF server's config (default: 600/150)

in set_character_stats.html:
  * adjust skillcap/attribute cap to match your LiF server's config (default: 600/150)

default listening address and port is 0.0.0.0:8099


## Usage
For security reasons a character's stats can only be viewed/changed if the same account also has a character with the lastname "Pvp".

Here is a video explaining the usage (in German!): https://youtu.be/yH40w_kL6ig?t=195
