#!/usr/bin/env python3

"""
Web interface for editing Life is Feudal: Your Own fight skill attributes
Copyright (c) 2016 Conrad Lampe
Released under MIT license

Dependencies:
  * cherrypy
  * PyMySQL
"""

MYSQL_INFO = {
    'USER': 'root',
    'PASS': '',
    'HOST': 'localhost',
    'DB': 'lif_1'
}
SKILLCAP = 600
ATTRIBUTECAP = 150

LISTEN_HOST = '0.0.0.0'
LISTEN_PORT = 8099

import cherrypy
import pymysql
import os.path


class InvalidInput(Exception):
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return str(self.message)


class DBConnection(cherrypy.Tool):
    def __init__(self, host, user, pwd, db):
        super().__init__('before_handler', self.connect, priority=90)
        self.server_info = {
            'host': host,
            'user': user,
            'password': pwd,
            'db': db
        }

    def _setup(self):
        super()._setup()
        cherrypy.request.hooks.attach('on_end_request',
                                      self.close_connection,
                                      priority=10)

    def connect(self):
        cherrypy.request.db = pymysql.connect(
            client_flag=pymysql.constants.CLIENT.FOUND_ROWS,
            **self.server_info
        )

    def close_connection(self):
        cherrypy.request.db.close()


class ModifyCharacterSkills(object):
    exposed = True
    _cp_config = {'tools.db.on': True}

    @cherrypy.tools.json_out()
    def POST(self, firstname, lastname):
        character = Character(firstname, lastname)
        return {
            'skills': character.get_skill_list().toSerializable(),
            'attributes': character.get_attributes().toSerializable()
        }


    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def PUT(self):
        try:
            data = cherrypy.request.json
            firstname = data['firstname']
            lastname = data['lastname']
            skills = data['skills']
            attributes = data['attributes']
            character = Character(firstname, lastname)
            new_attributes = CharacterAttributes(**attributes)
            new_skills = CharacterSkillList(skills)
            character.set_attributes(new_attributes)
            character.set_skill_list(new_skills)
            character.commit()
        except InvalidInput as e:
            exception = cherrypy.HTTPError("422 " + str(e))
            exception.set_response()
            return { "error": { "code": 422, "message": str(e) } }
        return {"success": True}


class Character(object):
    def __init__(self, firstname, lastname):
        self.id = self._get_id(firstname, lastname)
        if self.id is None:
            raise cherrypy.HTTPError("403 Forbidden")
        self._attributes = None
        self._skill_list = None

    def _get_id(self, firstname, lastname):
        sql = """SELECT ID FROM `character` AS c
                    WHERE
                        LOWER(Name) = LOWER(%s)
                        AND LOWER(LastName) = LOWER(%s)
                        AND
                            (SELECT COUNT(*) FROM `character` AS c2
                                WHERE
                                    c.AccountID = c2.AccountID
                                    AND LOWER(c2.LastName) = 'pvp')
                            > 0"""
        cursor = cherrypy.request.db.cursor()
        cursor.execute(sql, (firstname, lastname))
        ret = cursor.fetchone()
        cursor.close()
        return ret

    def get_skill_list(self):
        if self._skill_list is None:
            self._skill_list = CharacterSkillList.get_for_character(self.id)
        return self._skill_list

    def get_attributes(self):
        if self._attributes is None:
            self._attributes = CharacterAttributes.get_for_character(self.id)
        return self._attributes

    def set_attributes(self, attributes):
        self._attributes = attributes

    def set_skill_list(self, skills):
        self._skill_list = skills
        self.verify_skills()

    def verify_skills(self):
        result = self.get_skill_list().validate(self.get_attributes()['intellect'])
        if result is not True:
            raise InvalidInput(result)

    def commit(self):
        if self._attributes is not None:
            self._attributes.commit(self.id)
        if self._skill_list is not None:
            self._skill_list.commit(self.id)


class CharacterAttributes(dict):
    modifier = 1000000
    attribute_names = ['agility', 'constitution', 'intellect', 'strength', 'willpower']

    def __init__(self, agility, constitution, intellect, strength, willpower):
        self['agility'] = agility
        self['constitution'] = constitution
        self['intellect'] = intellect
        self['strength'] = strength
        self['willpower'] = willpower

        if sum(self.values()) > 150*CharacterAttributes.modifier:
            raise InvalidInput("Attribute sum must be <= 150")
        elif len(list(filter(lambda x: x < 10*CharacterAttributes.modifier,
                             self.values()))):
            raise InvalidInput("Each attribute must be at least 10")
        elif len(list(filter(lambda x: x > 100*CharacterAttributes.modifier,
                             self.values()))):
            raise InvalidInput("Each attribute must be at most 100")

    @staticmethod
    def get_for_character(id):
        sql = """SELECT Agility, Constitution, Intellect, Strength, Willpower
                FROM `character`
                WHERE ID = %s"""
        cursor = cherrypy.request.db.cursor()
        cursor.execute(sql, (id,))
        ret = CharacterAttributes(*cursor.fetchone())
        cursor.close()
        return ret

    def commit(self, charid):
        sql = """UPDATE `character` SET
                    Agility = %s,
                    Constitution = %s,
                    Intellect = %s,
                    Strength = %s,
                    Willpower = %s
                WHERE ID = %s
                """
        cursor = cherrypy.request.db.cursor()
        cursor.execute(sql, (self['agility'], self['constitution'],
                             self['intellect'], self['strength'],
                             self['willpower'], charid))
        cherrypy.request.db.commit()
        cursor.close()

    def toSerializable(self):
        return self


class SkillList(object):
    skills = None

    def __init__(self):
        if SkillList.skills is None:
            SkillList.skills = self._skill_list_to_dict(self._get_skill_list())

    def _get_skill_list(self):
        sql = """SELECT ID, Name, Parent FROM skill_type WHERE `Group` = 2"""
        cursor = cherrypy.request.db.cursor()
        cursor.execute(sql)
        ret = cursor.fetchall()
        cursor.close()
        return ret

    def _skill_list_to_dict(self, skill_list):
        skilldict = {}
        for s in skill_list:
            skilldict[s[0]] = Skill(*s)
        return skilldict


class Skill(object):
    def __init__(self, id, name, parentid):
        self.id = id
        self.name = name
        self.parentid = parentid


class CharacterSkill(Skill):
    def __init__(self, skill, value):
        super().__init__(skill.id, skill.name, skill.parentid)
        self.value = value

    def toSerializable(self):
        return {
            "id": self.id,
            "name": self.name,
            "parentid": self.parentid,
            "value": self.value
        }


class CharacterSkillList(SkillList):
    modifier = 10000000

    def __init__(self, new_values):
        super().__init__()
        self.character_skills = {}
        for skill in SkillList.skills.values():
            self.character_skills[skill.id] = CharacterSkill(skill,
                                                new_values[str(skill.id)])

    def validate(self, intellect):
        for skill in self.character_skills.values():
            if skill.parentid is None:
                continue
            if skill.value >= 30*CharacterSkillList.modifier and\
                    self.character_skills[skill.parentid].value\
                        < 60*CharacterSkillList.modifier:
                return "Invalid input for {}".format(skill.name)
            elif skill.value > 0 and\
                self.character_skills[skill.parentid].value\
                    < 30*CharacterSkillList.modifier:
                return "Invalid input for {}".format(skill.name)

        if sum(map(lambda x: x.value, self.character_skills.values()))\
                > (SKILLCAP*CharacterSkillList.modifier +\
                   (intellect - 10*CharacterAttributes.modifier)*10):
            return "Skill cap exceeded"

        return True

    @staticmethod
    def get_for_character(id):
        sql = """SELECT st.ID, s.SkillAmount
                    FROM skill_type AS st
                    LEFT OUTER JOIN skills AS s
                        ON st.ID = s.SkillTypeID
                        AND CharacterID = %s
                    WHERE st.`Group` = 2 GROUP BY ID"""
        cursor = cherrypy.request.db.cursor()
        cursor.execute(sql, (id,))
        values = {}
        for sid, amount in cursor.fetchall():
            values[str(sid)] = amount if amount is not None else 0
        cursor.close()
        return CharacterSkillList(values)

    def toSerializable(self):
        return list(map(lambda s: s.toSerializable(), self.character_skills.values()))

    def commit(self, charid):
        sql_up = """UPDATE skills SET SkillAmount = %s
                   WHERE SkillTypeID = %s AND CharacterID = %s
                """
        sql_ins = """INSERT INTO skills (CharacterID, SkillTypeID, SkillAmount)
                        VALUES (%s, %s, %s)
                    """
        cursor = cherrypy.request.db.cursor()
        for s in self.character_skills.values():
            affected_rows = cursor.execute(sql_up, (s.value, s.id, charid))
            if affected_rows < 1:
                cursor.execute(sql_ins, (charid, s.id, s.value))
        cherrypy.request.db.commit()
        cursor.close()


if __name__ == '__main__':
    cherrypy.config.update({'environment': 'production'})
    cherrypy.config.update({'server.socket_port': LISTEN_PORT})
    cherrypy.config.update({'server.socket_host': LISTEN_HOST})
    conf = {
        '/': {
            'tools.staticfile.on': True,
            'tools.staticfile.filename': os.path.join(os.path.dirname(
                os.path.realpath(__file__)), 'set_character_stats.html')
        },
        '/skills': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [('Content-Type', 'application/json')],
        },
    }
    app = lambda: None
    app.skills = ModifyCharacterSkills()

    cherrypy.tools.db = DBConnection(MYSQL_INFO['HOST'], MYSQL_INFO['USER'],
                                     MYSQL_INFO['PASS'], MYSQL_INFO['DB'])

    cherrypy.quickstart(app, '/', conf)
